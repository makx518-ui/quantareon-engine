"""
transit_activations.py — Машинный расчёт всех значимых транзитных событий года.

Считает день-за-днём по эфемериде:
1) Точные аспекты транзитных планет к натальным и солярным точкам (орбис <2°)
2) Прохождения транзитных планет через куспиды натальных/солярных домов
3) Точные даты ингрессий (смены знаков) медленных планет
4) Точные даты ретроградных разворотов (стационарность)

Возвращает структурированный JSON для передачи в промпт.
Модель НЕ ищет события сама — получает готовый список с датами.

Транзитные планеты:
  - Медленные: Юпитер, Сатурн, Уран, Нептун, Плутон, Сев.Узел, Хирон
  - Дополнительно Марс (циклы 2 года, важен для активаций)

Натальные/солярные точки (для аспектов):
  - 10 планет + Хирон + 4 угла (ASC/MC/IC/DESC) + Сев.Узел

Орбисы:
  - Соединение, оппозиция, квадрат: 2.0°
  - Трин, секстиль: 1.5°

Точность: до дня.
Дома: Placidus (как в Kerykeion по умолчанию).
"""

import calendar
from datetime import date, datetime, timedelta
from kerykeion import AstrologicalSubjectFactory


# ============================================================
# КОНСТАНТЫ
# ============================================================

# Транзитные планеты (что движется по эфемериде)
TRANSIT_PLANETS = {
    'mars': 'Марс',
    'jupiter': 'Юпитер',
    'saturn': 'Сатурн',
    'uranus': 'Уран',
    'neptune': 'Нептун',
    'pluto': 'Плутон',
    'true_north_lunar_node': 'Сев.Узел',
    'chiron': 'Хирон',
}

# Натальные/солярные точки (планеты и угловые точки)
NATAL_PLANETS = {
    'sun': 'Солнце',
    'moon': 'Луна',
    'mercury': 'Меркурий',
    'venus': 'Венера',
    'mars': 'Марс',
    'jupiter': 'Юпитер',
    'saturn': 'Сатурн',
    'uranus': 'Уран',
    'neptune': 'Нептун',
    'pluto': 'Плутон',
    'chiron': 'Хирон',
    'true_north_lunar_node': 'Сев.Узел',
}

# Аспекты: angle, орбис, тип
ASPECTS = [
    ('соединение', 0, 3.0, 'CONJ'),
    ('оппозиция', 180, 3.0, 'OPP'),
    ('квадрат', 90, 3.0, 'SQ'),
    ('трин', 120, 2.5, 'TR'),
    ('секстиль', 60, 2.5, 'SX'),
]

SIGNS_RU = ['Овен', 'Телец', 'Близнецы', 'Рак', 'Лев', 'Дева',
            'Весы', 'Скорпион', 'Стрелец', 'Козерог', 'Водолей', 'Рыбы']

MONTHS_RU = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
             'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _angular_distance(a, b):
    """Минимальное угловое расстояние между двумя точками на 360° круге."""
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def _aspect_orb(deg1, deg2, target_angle):
    """Орбис для конкретного аспекта (соединение=0, квадрат=90 и т.д.)."""
    diff = _angular_distance(deg1, deg2)
    return abs(diff - target_angle)


def _sign_from_deg(abs_pos):
    """Знак зодиака по абсолютной долготе."""
    return SIGNS_RU[int(abs_pos // 30) % 12]


def _deg_in_sign(abs_pos):
    """Градус в знаке (0-30)."""
    return abs_pos % 30


def _format_date(d):
    """Дата в формате '12 августа'."""
    return f"{d.day} {MONTHS_RU[d.month]}"


def _format_date_full(d):
    """Дата в формате '12 августа 2026'."""
    return f"{d.day} {MONTHS_RU[d.month]} {d.year}"


def _get_transit_subject(d, lat=0, lng=0, tz='UTC'):
    """Расчёт эфемериды на полдень указанного дня."""
    return AstrologicalSubjectFactory.from_birth_data(
        f'T{d.year}{d.month}{d.day}', d.year, d.month, d.day, 12, 0,
        lng=lng, lat=lat, tz_str=tz, online=False
    )


def _extract_planet_positions(subject):
    """Извлечь позиции всех транзитных планет в момент."""
    result = {}
    for key in TRANSIT_PLANETS.keys():
        try:
            obj = getattr(subject, key)
            result[key] = {
                'abs_pos': obj.abs_pos,
                'retrograde': obj.retrograde,
                'sign': _sign_from_deg(obj.abs_pos),
                'deg_in_sign': _deg_in_sign(obj.abs_pos),
            }
        except Exception:
            pass
    return result


def _extract_target_points(subject, label='natal'):
    """Извлечь все точки карты для проверки аспектов: планеты + углы.

    Используем только ASC и MC (IC и DESC — их зеркала на 180°, аспекты к ним
    автоматически выводятся из аспектов к ASC/MC и создают дубликаты).
    """
    points = {}
    # Планеты
    for key, name in NATAL_PLANETS.items():
        try:
            obj = getattr(subject, key)
            points[name] = obj.abs_pos
        except Exception:
            pass
    # Углы — только ASC и MC (IC и DESC автоматически зеркалятся)
    try:
        points['ASC'] = subject.first_house.abs_pos
        points['MC'] = subject.tenth_house.abs_pos
    except Exception:
        pass
    return points


def _extract_house_cusps(subject):
    """12 куспидов домов."""
    cusps = []
    house_names = ['first_house', 'second_house', 'third_house', 'fourth_house',
                   'fifth_house', 'sixth_house', 'seventh_house', 'eighth_house',
                   'ninth_house', 'tenth_house', 'eleventh_house', 'twelfth_house']
    for hn in house_names:
        try:
            cusps.append(getattr(subject, hn).abs_pos)
        except Exception:
            cusps.append(0.0)
    return cusps


def _which_house(abs_pos, cusps):
    """В каком доме (1-12) лежит точка."""
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        # Учитываем переход через 0°
        if start <= end:
            if start <= abs_pos < end:
                return i + 1
        else:
            if abs_pos >= start or abs_pos < end:
                return i + 1
    return 1


# ============================================================
# РАСЧЁТ ЭФЕМЕРИДЫ НА ГОД
# ============================================================

def _build_ephemeris(start_date, end_date, step_days=1):
    """Построить эфемериду — список (дата, позиции планет) с шагом step_days.
    Использует кэш на диске (год → pickle). Для мультигодовых диапазонов
    склеивает кэши нескольких лет."""
    try:
        from astro.ephemeris_cache import get_cached_subjects

        # Определяем какие годы покрывает диапазон
        s_date = start_date if isinstance(start_date, date) else start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date if isinstance(end_date, date) else end_date.date() if isinstance(end_date, datetime) else end_date

        all_subjects = []
        for year in range(s_date.year, e_date.year + 1):
            subjects = get_cached_subjects(year, lat=0, lng=0, tz_str='UTC')
            all_subjects.extend(subjects)

        eph = []
        for subj in all_subjects:
            d = date(subj.year, subj.month, subj.day)
            if s_date <= d <= e_date:
                if step_days == 1 or (d - s_date).days % step_days == 0:
                    positions = _extract_planet_positions(subj)
                    eph.append({'date': d, 'positions': positions})
        return eph
    except Exception:
        # Fallback to one-by-one if cache fails
        eph = []
        d = start_date
        while d <= end_date:
            subj = _get_transit_subject(d)
            positions = _extract_planet_positions(subj)
            eph.append({'date': d, 'positions': positions})
            d += timedelta(days=step_days)
        return eph


# ============================================================
# БЛОК А: ТРАНЗИТНЫЕ АСПЕКТЫ К НАТАЛЬНЫМ/СОЛЯРНЫМ ТОЧКАМ
# ============================================================

def _find_aspect_events(ephemeris, target_points, target_label='natal'):
    """Найти все события точных аспектов транзитных планет к точкам.

    Алгоритм: для каждой пары (транзитная планета × точка × аспект):
    - Идём по эфемериде день за днём
    - Считаем орбис на каждый день
    - Находим ВСЕ локальные минимумы орбиса (точки где орбис меньше чем у соседей)
    - Если локальный минимум <= max_orb — это событие
    - Окно: даты входа и выхода из орбиса

    Ретрограды дают несколько локальных минимумов через одну точку.
    """
    events = []

    for tp_key, tp_name in TRANSIT_PLANETS.items():
        for target_name, target_deg in target_points.items():
            # Пропускаем "аспект к самой себе" если транзитная и натальная одного имени
            # (например транзитный Сатурн к натальному Сатурну — это сатурн-возврат, важно, оставляем)
            for asp_name, asp_angle, asp_max_orb, asp_code in ASPECTS:
                # Список орбисов по дням
                orbs = []
                for day_data in ephemeris:
                    pos = day_data['positions'].get(tp_key)
                    if not pos:
                        orbs.append(None)
                        continue
                    orb = _aspect_orb(pos['abs_pos'], target_deg, asp_angle)
                    orbs.append(orb)

                # Находим локальные минимумы
                minima = _find_local_minima(orbs)

                for min_idx, min_orb in minima:
                    if min_orb > asp_max_orb:
                        continue

                    exact_date = ephemeris[min_idx]['date']

                    # Окно: ищем влево и вправо от min_idx где орбис <= asp_max_orb
                    start_idx = min_idx
                    while start_idx > 0 and orbs[start_idx - 1] is not None and orbs[start_idx - 1] <= asp_max_orb:
                        start_idx -= 1
                    end_idx = min_idx
                    while end_idx < len(orbs) - 1 and orbs[end_idx + 1] is not None and orbs[end_idx + 1] <= asp_max_orb:
                        end_idx += 1

                    strength = 'ТОЧНОЕ' if min_orb < 0.3 else ('ПОЧТИ ТОЧНОЕ' if min_orb < 1.0 else 'В ОРБИСЕ')

                    # Ретроградность транзитной планеты в момент точного аспекта
                    retro = ephemeris[min_idx]['positions'][tp_key].get('retrograde', False)

                    events.append({
                        'transit_planet': tp_name,
                        'target': target_name,
                        'target_label': target_label,
                        'target_position_sign': _sign_from_deg(target_deg),
                        'target_position_deg': round(_deg_in_sign(target_deg), 1),
                        'aspect': asp_name,
                        'aspect_code': asp_code,
                        'exact_date': exact_date,
                        'window_start': ephemeris[start_idx]['date'],
                        'window_end': ephemeris[end_idx]['date'],
                        'orb': round(min_orb, 2),
                        'strength': strength,
                        'transit_retrograde': retro,
                    })

    return events


def _find_local_minima(values, min_separation_rise=0.5):
    """Найти локальные минимумы в списке значений. Возвращает [(index, value), ...].

    Локальный минимум считается «выраженным» только если между ним и предыдущим
    минимумом орбис поднимался хотя бы на min_separation_rise градусов.
    Это отсекает дубликаты в длинных «топчущихся» проходах (например Сев.Узел),
    но сохраняет валидные ретроградные проходы Урана/Сатурна.
    """
    minima = []
    n = len(values)
    if n < 2:
        return minima

    # Шаг 1: находим все потенциальные локальные минимумы
    raw_minima = []
    for i in range(n):
        v = values[i]
        if v is None:
            continue

        left = values[i - 1] if i > 0 else None
        right = values[i + 1] if i < n - 1 else None

        if left is None and right is not None and v <= right:
            raw_minima.append((i, v))
            continue
        if right is None and left is not None and v <= left:
            raw_minima.append((i, v))
            continue
        if left is not None and right is not None:
            if v <= left and v <= right and (v < left or v < right):
                raw_minima.append((i, v))

    if not raw_minima:
        return minima

    # Шаг 2: фильтруем — между двумя минимумами должен быть подъём
    # Берём первый, потом каждый следующий только если между ним и предыдущим
    # был пик с подъёмом не меньше min_separation_rise
    minima.append(raw_minima[0])
    for idx in range(1, len(raw_minima)):
        prev_min_i, prev_min_v = minima[-1]
        cur_min_i, cur_min_v = raw_minima[idx]
        # Ищем максимум орбиса между prev_min_i и cur_min_i
        between_max = max(
            (values[k] for k in range(prev_min_i + 1, cur_min_i) if values[k] is not None),
            default=None
        )
        if between_max is None:
            continue
        rise_from_prev = between_max - prev_min_v
        rise_to_cur = between_max - cur_min_v
        # Подъём должен быть значимым с обеих сторон
        if rise_from_prev >= min_separation_rise and rise_to_cur >= min_separation_rise:
            minima.append(raw_minima[idx])
        else:
            # Это часть того же длинного прохода — заменяем предыдущий минимум на более точный
            if cur_min_v < prev_min_v:
                minima[-1] = (cur_min_i, cur_min_v)

    return minima


# ============================================================
# БЛОК Б: ИНГРЕССИИ ПО ДОМАМ (натальным и солярным)
# ============================================================

def _find_house_ingresses(ephemeris, house_cusps, house_label='natal'):
    """Найти точные даты входа транзитных планет в каждый дом.

    Алгоритм: для каждой транзитной планеты идём по эфемериде,
    отмечаем смену дома. Учитываем ретрограды (3 прохода возможны).
    """
    ingresses = []

    for tp_key, tp_name in TRANSIT_PLANETS.items():
        # Последовательность домов по дням
        houses_by_day = []
        for day_data in ephemeris:
            pos = day_data['positions'].get(tp_key)
            if not pos:
                houses_by_day.append(None)
                continue
            h = _which_house(pos['abs_pos'], house_cusps)
            houses_by_day.append(h)

        # Находим смены
        prev_h = None
        for i, h in enumerate(houses_by_day):
            if h is None:
                continue
            if prev_h is None:
                prev_h = h
                continue
            if h != prev_h:
                # Смена дома: вход в h, выход из prev_h
                ingresses.append({
                    'transit_planet': tp_name,
                    'house_system': house_label,
                    'from_house': prev_h,
                    'to_house': h,
                    'date': ephemeris[i]['date'],
                    'retrograde': ephemeris[i]['positions'][tp_key].get('retrograde', False),
                })
                prev_h = h

    return ingresses


# ============================================================
# БЛОК В: ИНГРЕССИИ ПО ЗНАКАМ (смены знаков)
# ============================================================

def _find_sign_ingresses(ephemeris):
    """Точные даты смены знаков для медленных планет."""
    ingresses = []

    for tp_key, tp_name in TRANSIT_PLANETS.items():
        prev_sign = None
        for day_data in ephemeris:
            pos = day_data['positions'].get(tp_key)
            if not pos:
                continue
            sign = pos['sign']
            if prev_sign is None:
                prev_sign = sign
                continue
            if sign != prev_sign:
                ingresses.append({
                    'planet': tp_name,
                    'from_sign': prev_sign,
                    'to_sign': sign,
                    'date': day_data['date'],
                    'retrograde': pos['retrograde'],
                })
                prev_sign = sign

    return ingresses


# ============================================================
# БЛОК Г: СТАЦИОНАРНОСТЬ (ретроградные развороты)
# ============================================================

def _find_stations(ephemeris):
    """Точные даты смены direct↔retrograde для медленных планет."""
    stations = []

    for tp_key, tp_name in TRANSIT_PLANETS.items():
        # Узлы всегда ретроградные (mean) или почти всегда (true) — пропускаем
        if tp_key == 'true_north_lunar_node':
            continue

        prev_retro = None
        for day_data in ephemeris:
            pos = day_data['positions'].get(tp_key)
            if not pos:
                continue
            retro = pos['retrograde']
            if prev_retro is None:
                prev_retro = retro
                continue
            if retro != prev_retro:
                station_type = 'retrograde' if retro else 'direct'
                stations.append({
                    'planet': tp_name,
                    'type': station_type,
                    'date': day_data['date'],
                    'sign': pos['sign'],
                    'deg_in_sign': round(pos['deg_in_sign'], 1),
                })
                prev_retro = retro

    return stations


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def _find_mundane_aspects(ephemeris):
    """Аспекты МЕЖДУ транзитными медленными планетами (мировой фон года).

    Большие конфигурации неба (Уран трин Плутон, Нептун секстиль к обоим и т.п.) —
    одинаковы для всех людей, влияют на эпоху целиком. Считаем попарно по году:
    для каждого складывающегося аспекта — пик (мин. орб), окно и направление.
    """
    from itertools import combinations
    MUNDANE = ['jupiter', 'saturn', 'uranus', 'neptune', 'pluto', 'chiron']
    results = []
    for k1, k2 in combinations(MUNDANE, 2):
        track = []  # (date, aspect_name, orb)
        for day in ephemeris:
            p1 = day['positions'].get(k1)
            p2 = day['positions'].get(k2)
            if not p1 or not p2:
                continue
            diff = abs(p1['abs_pos'] - p2['abs_pos']) % 360
            if diff > 180:
                diff = 360 - diff
            for nm, ang, orb_max, code in ASPECTS:
                orb = abs(diff - ang)
                if orb <= orb_max:
                    track.append((day['date'], nm, round(orb, 2)))
                    break
        if not track:
            continue
        # доминирующий аспект года = тот, что держится дольше всего
        from collections import Counter
        dom = Counter(t[1] for t in track).most_common(1)[0][0]
        same = [t for t in track if t[1] == dom]
        peak = min(same, key=lambda x: x[2])
        results.append({
            'p1': TRANSIT_PLANETS.get(k1, k1),
            'p2': TRANSIT_PLANETS.get(k2, k2),
            'aspect': dom,
            'peak_orb': peak[2],
            'peak_date': peak[0],
            'window_start': same[0][0],
            'window_end': same[-1][0],
            'exact_in_year': peak[2] < 0.5,
            'applying': same[0][2] > same[-1][2],  # орб сужается = складывается
        })
    results.sort(key=lambda e: e['peak_orb'])
    return results


def _find_world_personal_bridges(aspects_natal, aspects_solar):
    """ТОЧКА СБОРКИ: где мировая конфигурация (медленные планеты эпохи) падает на ОДНУ
    точку карты — несколько планет Урана/Нептуна/Плутона/Сатурна аспектируют её разом.

    Это самое важное в году: где небо эпохи касается лично человека. Особенно сильно,
    если точка — угол (МС/АСЦ) или светило: личная судьба включается в сдвиг поколения.
    """
    WORLD = {'Уран', 'Нептун', 'Плутон', 'Сатурн'}
    bridges = []
    for label, aspects in (('натал', aspects_natal), ('соляр', aspects_solar)):
        by_target = {}
        for ev in aspects:
            if ev['transit_planet'] in WORLD:
                by_target.setdefault(ev['target'], []).append(ev)
        for target, evs in by_target.items():
            planets = {e['transit_planet'] for e in evs}
            if len(planets) >= 2:  # 2+ мировых планеты на одной точке = узел
                evs_sorted = sorted(evs, key=lambda e: e['exact_date'])
                bridges.append({
                    'target': target,
                    'target_label': label,
                    'planets': sorted(planets),
                    'is_angle': target in ('MC', 'ASC', 'IC', 'DESC'),
                    'is_luminary': target in ('Солнце', 'Луна'),
                    'aspects': [{'planet': e['transit_planet'], 'aspect': e['aspect'],
                                 'date': e['exact_date'], 'orb': e['orb']} for e in evs_sorted],
                    'first_date': evs_sorted[0]['exact_date'],
                    'last_date': evs_sorted[-1]['exact_date'],
                })
    # сначала углы и светила, потом по числу планет
    bridges.sort(key=lambda b: (not (b['is_angle'] or b['is_luminary']), -len(b['planets'])))
    return bridges


def calculate_transit_activations(natal_subject, solar_subject, solar_year):
    """Главная функция — расчёт ВСЕХ транзитных событий солярного года.

    Параметры:
        natal_subject: AstrologicalSubject (натал)
        solar_subject: AstrologicalSubject (соляр на год)
        solar_year: int — год соляра (например 2026)

    Возвращает dict:
        {
            'period': {'start': '2026-01-30', 'end': '2027-01-30'},
            'exact_aspects_natal': [...],   # аспекты к натальной карте
            'exact_aspects_solar': [...],   # аспекты к солярной карте
            'house_ingresses_natal': [...], # вход в натальные дома
            'house_ingresses_solar': [...], # вход в солярные дома
            'sign_ingresses': [...],        # смены знаков медленных планет
            'stations': [...],              # ретроградные развороты
        }
    """
    # Период: от даты соляра до следующего соляра (примерно год)
    # Берём из solar_subject — он точно содержит дату возврата
    # Этап 5.3: расширяем окно на ±30 дней чтобы поймать ингрессии медленных
    # планет которые происходят рядом с датой соляра (например Нептун, который
    # переходит в Овен за 3 дня до соляра 30.01.2026)
    try:
        solar_date = date(solar_subject.year, solar_subject.month, solar_subject.day)
    except Exception:
        solar_date = date(solar_year, 1, 1)

    start_date = solar_date - timedelta(days=30)  # -30 дней до соляра
    end_date = solar_date + timedelta(days=395)   # +365 (год) +30 дней после

    # Шаг 1: эфемерида на весь год с шагом 1 день
    ephemeris = _build_ephemeris(start_date, end_date, step_days=1)

    # Шаг 2: натальные точки и солярные точки
    natal_points = _extract_target_points(natal_subject, label='natal')
    solar_points = _extract_target_points(solar_subject, label='solar')

    # Шаг 3: куспиды домов
    natal_cusps = _extract_house_cusps(natal_subject)
    solar_cusps = _extract_house_cusps(solar_subject)

    # Шаг 4: считаем все события
    aspects_natal = _find_aspect_events(ephemeris, natal_points, target_label='natal')
    aspects_solar = _find_aspect_events(ephemeris, solar_points, target_label='solar')
    ingresses_natal = _find_house_ingresses(ephemeris, natal_cusps, house_label='natal')
    ingresses_solar = _find_house_ingresses(ephemeris, solar_cusps, house_label='solar')
    sign_ingresses = _find_sign_ingresses(ephemeris)
    stations = _find_stations(ephemeris)
    mundane_aspects = _find_mundane_aspects(ephemeris)
    world_personal_bridges = _find_world_personal_bridges(aspects_natal, aspects_solar)

    # Шаг 5: сортируем по дате
    aspects_natal.sort(key=lambda e: e['exact_date'])
    aspects_solar.sort(key=lambda e: e['exact_date'])
    ingresses_natal.sort(key=lambda e: e['date'])
    ingresses_solar.sort(key=lambda e: e['date'])
    sign_ingresses.sort(key=lambda e: e['date'])
    stations.sort(key=lambda e: e['date'])

    return {
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        },
        'exact_aspects_natal': aspects_natal,
        'exact_aspects_solar': aspects_solar,
        'house_ingresses_natal': ingresses_natal,
        'house_ingresses_solar': ingresses_solar,
        'sign_ingresses': sign_ingresses,
        'stations': stations,
        'mundane_aspects': mundane_aspects,
        'world_personal_bridges': world_personal_bridges,
    }


# ============================================================
# ФОРМАТИРОВАНИЕ ДЛЯ ПРОМПТА
# ============================================================

# ============================================================
# ФИЛЬТРАЦИЯ И РАНЖИРОВАНИЕ ПО ВАЖНОСТИ
# ============================================================

SLOW_PLANETS_RU = {'Юпитер', 'Сатурн', 'Уран', 'Нептун', 'Плутон', 'Хирон', 'Сев.Узел'}
ANGLE_POINTS_RU = {'ASC', 'MC', 'IC', 'DESC'}
LUMINARIES_RU = {'Солнце', 'Луна'}


def _classify_aspect_event(ev):
    """Классифицирует событие аспекта по 3-уровневой шкале важности.

    Возвращает: 'critical' | 'significant' | 'mars_trigger' | 'skip'
    """
    tp = ev['transit_planet']
    target = ev['target']
    orb = ev['orb']

    if tp == 'Марс':
        if orb < 1.0:
            return 'mars_trigger'
        return 'skip'

    if tp in SLOW_PLANETS_RU:
        # КРИТИЧЕСКИЕ (раскрывать подробно — это конфигурации года):
        # (а) орбис <1.5° к углам или светилам — мощные конфигурации года
        # (б) орбис <1.0° к ЛЮБОЙ точке — точный аспект к натальной планете
        if orb < 1.5 and (target in ANGLE_POINTS_RU or target in LUMINARIES_RU):
            return 'critical'
        if orb < 1.0:
            return 'critical'
        # ЗНАЧИМЫЕ: остальное <3.0° — нарастание и спад медленного транзита,
        # а не только точка пика (для Плутона/Нептуна это месяцы жизни года)
        if orb < 3.0:
            return 'significant'
        return 'skip'

    return 'skip'


def _hint_for_target(target):
    """Подсказка модели — в какую секцию относить событие."""
    if target == 'MC' or target == 'IC':
        return 'КАРЬЕРА / основание жизни'
    if target == 'ASC' or target == 'DESC':
        return 'ЛИЧНОСТЬ / партнёрство'
    if target in ('Венера', 'Марс'):
        return 'ЛЮБОВЬ или ФИНАНСЫ'
    if target in ('Юпитер', 'Сатурн'):
        return 'КАРЬЕРА / ФИНАНСЫ'
    if target == 'Луна':
        return 'ЭМОЦИИ / ЗДОРОВЬЕ'
    if target == 'Солнце':
        return 'ТЕМА ГОДА'
    if target == 'Меркурий':
        return 'МЫШЛЕНИЕ / КОММУНИКАЦИЯ'
    if target == 'Нептун':
        return 'ДУХОВНОСТЬ / ИЛЛЮЗИИ'
    if target == 'Плутон':
        return 'ТРАНСФОРМАЦИЯ / ВЛАСТЬ'
    if target == 'Уран':
        return 'ПЕРЕМЕНЫ / СВОБОДА'
    if target == 'Хирон':
        return 'РАНА / ИСЦЕЛЕНИЕ'
    if target == 'Сев.Узел':
        return 'ОСЬ ЭВОЛЮЦИИ'
    return 'СИНТЕЗ'


def filter_and_rank_activations(activations):
    """Разделяет все события на 3 уровня важности."""
    result = {
        'critical_natal': [],
        'critical_solar': [],
        'significant_natal': [],
        'significant_solar': [],
        'mars_triggers_natal': {},
        'mars_triggers_solar': {},
        'sign_ingresses': activations.get('sign_ingresses', []),
        'stations': activations.get('stations', []),
        'house_ingresses_natal': activations.get('house_ingresses_natal', []),
        'house_ingresses_solar': activations.get('house_ingresses_solar', []),
        'mundane_aspects': activations.get('mundane_aspects', []),
        'world_personal_bridges': activations.get('world_personal_bridges', []),
    }

    for ev in activations.get('exact_aspects_natal', []):
        cls = _classify_aspect_event(ev)
        if cls == 'critical':
            result['critical_natal'].append(ev)
        elif cls == 'significant':
            result['significant_natal'].append(ev)
        elif cls == 'mars_trigger':
            month_key = ev['exact_date'].month
            result['mars_triggers_natal'].setdefault(month_key, []).append(ev)

    for ev in activations.get('exact_aspects_solar', []):
        cls = _classify_aspect_event(ev)
        if cls == 'critical':
            result['critical_solar'].append(ev)
        elif cls == 'significant':
            result['significant_solar'].append(ev)
        elif cls == 'mars_trigger':
            month_key = ev['exact_date'].month
            result['mars_triggers_solar'].setdefault(month_key, []).append(ev)

    result['critical_natal'].sort(key=lambda e: (e['orb'], e['exact_date']))
    result['critical_solar'].sort(key=lambda e: (e['orb'], e['exact_date']))
    result['significant_natal'].sort(key=lambda e: e['exact_date'])
    result['significant_solar'].sort(key=lambda e: e['exact_date'])

    return result


_MONTHS_NOM = ['', 'ЯНВАРЬ', 'ФЕВРАЛЬ', 'МАРТ', 'АПРЕЛЬ', 'МАЙ', 'ИЮНЬ', 'ИЮЛЬ',
               'АВГУСТ', 'СЕНТЯБРЬ', 'ОКТЯБРЬ', 'НОЯБРЬ', 'ДЕКАБРЬ']


def _format_monthly_calendar(ranked):
    """Помесячная лента года: все складывающиеся аспекты и переломы в хронологии.

    Не заменяет уровни важности (они идут ниже для приоритета), а даёт Сонету
    год как непрерывную ленту январь→декабрь — чтобы динамика читалась по месяцам,
    а сильные складывающиеся аспекты не терялись в общем списке.
    """
    events = []  # (date, text)

    def _aspline(ev, kind, is_crit):
        retro = " ℞" if ev.get('transit_retrograde') else ""
        win = ""
        if ev['window_start'] != ev['window_end']:
            win = f" [окно {_format_date(ev['window_start'])}–{_format_date(ev['window_end'])}]"
        star = "⭐ " if is_crit else ""
        _grad = ""
        try:
            from astro.solar_prompt_builder import _degree_meaning as _dm_t
            _g = _dm_t(ev.get('target_position_sign'), ev.get('target_position_deg'))
            if _g:
                _grad = f" [ГРАДУС {kind}-{ev['target']}: {_g}]"
        except Exception:
            pass
        return (ev['exact_date'],
                f"  • {star}{_format_date(ev['exact_date'])}: транзитный {ev['transit_planet']}{retro} "
                f"{ev['aspect']} {kind}-{ev['target']} ({ev['target_position_sign']} "
                f"{ev['target_position_deg']}°) — орб {ev['orb']}°, {ev['strength']}{win}{_grad}")

    for ev in ranked.get('critical_natal', []):
        events.append(_aspline(ev, 'натал', True))
    for ev in ranked.get('critical_solar', []):
        events.append(_aspline(ev, 'соляр', True))
    for ing in ranked.get('sign_ingresses', []):
        retro = " ℞" if ing.get('retrograde') else ""
        events.append((ing['date'],
                       f"  • ⭐ {_format_date(ing['date'])}: {ing['planet']}{retro} переходит из "
                       f"{ing['from_sign']} в {ing['to_sign']} — СМЕНА ТЕМЫ (переломный момент)"))
    for st in ranked.get('stations', []):
        events.append((st['date'],
                       f"  • {_format_date(st['date'])}: {st['planet']} разворот "
                       f"({st.get('sign', '')} {st.get('deg_in_sign', '')}°)"))

    if not events:
        return []

    events.sort(key=lambda x: x[0])
    out = ["═" * 70,
           "📅 ДИНАМИКА ГОДА ПО МЕСЯЦАМ — складывающиеся аспекты в хронологии",
           "═" * 70,
           "Год как лента: для каждого месяца — какие аспекты становятся точными, что нарастает.",
           "Разворачивай год ПОСЛЕДОВАТЕЛЬНО по этим месяцам, не пропуская событий: именно здесь",
           "живёт событийная фактура года. Сильные складывающиеся аспекты обязательно трактуй.",
           ""]
    cur = None
    for d, text in events:
        key = (d.year, d.month)
        if key != cur:
            cur = key
            out.append(f"▸ {_MONTHS_NOM[d.month]} {d.year}")
        out.append(text)
    out.append("")
    return out


def format_activations_for_prompt(activations, lang='ru'):
    """Форматирует результат calculate_transit_activations в текст для промпта.

    Трёхуровневая структура:
    Уровень 1 — КРИТИЧЕСКИЕ события (подробно, с окном и hint).
    Уровень 2 — ЗНАЧИМЫЕ события (одна строка).
    Уровень 3 — ТРИГГЕРЫ МАРСА (помесячная сводка).
    """
    if lang != 'ru':
        return _format_en(activations)

    ranked = filter_and_rank_activations(activations)

    lines = []
    lines.append("=" * 70)
    lines.append("🎯 ТРАНЗИТНЫЕ СОБЫТИЯ ГОДА — МАШИННЫЙ РАСЧЁТ ПО ЭФЕМЕРИДЕ")
    lines.append("=" * 70)
    lines.append("Каждое событие ниже — РЕАЛЬНЫЙ астрономический факт с точной датой.")
    lines.append("Используй ЭТИ данные. НЕ ВЫДУМЫВАЙ дополнительных аспектов или дат.")
    lines.append("Главные события помечены ⭐ — их раскрывай подробно. Остальные — фон динамики года.")
    lines.append("")

    # СУДЬБОНОСНЫЕ ВЕХИ — переходы знаков и развороты медленных планет (выделены отдельно,
    # чтобы не растворялись в ленте: смена знака внешней планеты = веха на годы, не фон).
    _ings = ranked.get('sign_ingresses', [])
    _stations = [st for st in ranked.get('stations', [])
                 if st.get('planet') in ('Уран', 'Нептун', 'Плутон', 'Сатурн')]
    if _ings or _stations:
        lines.append("─" * 70)
        lines.append("🔑 СУДЬБОНОСНЫЕ ВЕХИ ГОДА — переходы знаков и развороты медленных планет")
        lines.append("─" * 70)
        lines.append("Это КРУПНЫЕ события — смена больших циклов, а НЕ фон. Каждую веху опиши")
        lines.append("ОБЯЗАТЕЛЬНО и подробно, с точной датой: что меняется в большой теме жизни,")
        lines.append("из чего в что переходит планета-персонаж. НЕ обобщай, НЕ пропускай.")
        lines.append("")
        for ing in _ings:
            retro = " (ретроградно)" if ing.get('retrograde') else ""
            lines.append(f"  ★ {_format_date(ing['date'])}: {ing['planet']} переходит "
                         f"из знака {ing['from_sign']} в знак {ing['to_sign']}{retro} — "
                         f"смена большого цикла этой планеты.")
        for st in _stations:
            lines.append(f"  ◆ {_format_date(st['date'])}: {st['planet']} разворот "
                         f"({st.get('sign','')} {st.get('deg_in_sign','')}°) — "
                         f"смена направления, поворот темы планеты.")
        lines.append("")

    # Помесячная лента года — ЕДИНСТВЕННАЯ структура (без дублирующих уровней)
    lines.extend(_format_monthly_calendar(ranked))

    # УРОВЕНЬ 3: ТРИГГЕРЫ МАРСА — ПОМЕСЯЧНАЯ СВОДКА
    mars_natal = ranked['mars_triggers_natal']
    mars_solar = ranked['mars_triggers_solar']
    if mars_natal or mars_solar:
        lines.append("─" * 70)
        lines.append("⚡ УРОВЕНЬ 3 — ТРИГГЕРЫ МАРСА (активаторы по месяцам, используй для динамики)")
        lines.append("─" * 70)
        all_months = sorted(set(list(mars_natal.keys()) + list(mars_solar.keys())))
        month_labels = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        for m in all_months:
            month_label = month_labels[m]
            natal_evs = mars_natal.get(m, [])
            solar_evs = mars_solar.get(m, [])
            parts_natal = [f"{ev['aspect']} натал-{ev['target']} ({ev['exact_date'].day}-го)" for ev in natal_evs]
            parts_solar = [f"{ev['aspect']} соляр-{ev['target']} ({ev['exact_date'].day}-го)" for ev in solar_evs]
            line = f"  {month_label}:"
            if parts_natal:
                line += " натал: " + ", ".join(parts_natal) + "."
            if parts_solar:
                line += " соляр: " + ", ".join(parts_solar) + "."
            lines.append(line)
        lines.append("")

    lines.append("=" * 70)
    crit = len(ranked['critical_natal']) + len(ranked['critical_solar'])
    sig = len(ranked['significant_natal']) + len(ranked['significant_solar'])
    mars_total = sum(len(v) for v in mars_natal.values()) + sum(len(v) for v in mars_solar.values())
    lines.append(f"ИТОГО: {crit} критических, {sig} значимых, {mars_total} триггеров Марса")
    lines.append("=" * 70)

    return "\n".join(lines)


def _format_en(activations):
    """English version — full formatting parallel to the Russian one."""
    ranked = filter_and_rank_activations(activations)

    # Перевод имён планет, целей и подсказок RU → EN
    PLANET_EN = {
        'Солнце': 'Sun', 'Луна': 'Moon', 'Меркурий': 'Mercury', 'Венера': 'Venus',
        'Марс': 'Mars', 'Юпитер': 'Jupiter', 'Сатурн': 'Saturn', 'Уран': 'Uranus',
        'Нептун': 'Neptune', 'Плутон': 'Pluto', 'Хирон': 'Chiron',
        'Сев.Узел': 'North Node',
        'ASC': 'ASC', 'MC': 'MC', 'IC': 'IC', 'DESC': 'DESC',
    }
    SIGN_EN = {
        'Овен': 'Aries', 'Телец': 'Taurus', 'Близнецы': 'Gemini', 'Рак': 'Cancer',
        'Лев': 'Leo', 'Дева': 'Virgo', 'Весы': 'Libra', 'Скорпион': 'Scorpio',
        'Стрелец': 'Sagittarius', 'Козерог': 'Capricorn', 'Водолей': 'Aquarius', 'Рыбы': 'Pisces',
    }
    ASPECT_EN = {
        'соединение': 'conjunction', 'оппозиция': 'opposition', 'квадрат': 'square',
        'трин': 'trine', 'секстиль': 'sextile',
    }
    HINT_EN = {
        'КАРЬЕРА / основание жизни': 'CAREER / life foundation',
        'ЛИЧНОСТЬ / партнёрство': 'IDENTITY / partnership',
        'ЛЮБОВЬ или ФИНАНСЫ': 'LOVE or FINANCE',
        'КАРЬЕРА / ФИНАНСЫ': 'CAREER / FINANCE',
        'ЭМОЦИИ / ЗДОРОВЬЕ': 'EMOTIONS / HEALTH',
        'ТЕМА ГОДА': 'YEAR THEME',
        'МЫШЛЕНИЕ / КОММУНИКАЦИЯ': 'THINKING / COMMUNICATION',
        'ДУХОВНОСТЬ / ИЛЛЮЗИИ': 'SPIRITUALITY / ILLUSIONS',
        'ТРАНСФОРМАЦИЯ / ВЛАСТЬ': 'TRANSFORMATION / POWER',
        'ПЕРЕМЕНЫ / СВОБОДА': 'CHANGE / FREEDOM',
        'РАНА / ИСЦЕЛЕНИЕ': 'WOUND / HEALING',
        'ОСЬ ЭВОЛЮЦИИ': 'EVOLUTIONARY AXIS',
        'СИНТЕЗ': 'SYNTHESIS',
    }
    STRENGTH_EN = {
        'ТОЧНОЕ': 'EXACT', 'ПОЧТИ ТОЧНОЕ': 'NEAR-EXACT', 'В ОРБИСЕ': 'IN ORB',
    }
    MONTHS_EN = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December']

    def _date_en(d):
        return f"{MONTHS_EN[d.month]} {d.day}"

    def _date_full_en(d):
        return f"{MONTHS_EN[d.month]} {d.day}, {d.year}"

    def _planet(name):
        return PLANET_EN.get(name, name)

    def _sign(name):
        return SIGN_EN.get(name, name)

    def _aspect(name):
        return ASPECT_EN.get(name, name)

    def _hint(name):
        return HINT_EN.get(name, name)

    def _strength(name):
        return STRENGTH_EN.get(name, name)

    lines = []
    lines.append("=" * 70)
    lines.append("🎯 TRANSIT EVENTS OF THE YEAR — MACHINE-COMPUTED FROM EPHEMERIS")
    lines.append("=" * 70)
    lines.append("Every event below is a REAL astronomical fact with an exact date.")
    lines.append("Use THIS data. DO NOT invent additional aspects or dates.")
    lines.append("Major turning points first, then the month-by-month timeline of every aspect.")
    lines.append("")

    # SIGN INGRESSES (slow only)
    slow_ingresses = [i for i in ranked['sign_ingresses'] if i['planet'] != 'Марс']
    if slow_ingresses:
        lines.append("─" * 70)
        lines.append("🔄 SIGN INGRESSES OF SLOW PLANETS — TURNING POINTS OF THE YEAR")
        lines.append("─" * 70)
        lines.append("A slow planet changing sign is a WORLD event — the end of one multi-year era and")
        lines.append("the start of another (Uranus Taurus→Gemini: from matter/money/land to connection/")
        lines.append("information/word/technology). NEVER reduce to one line. Unfold: what this shift")
        lines.append("means for the WORLD, and — if the new sign holds a natal angle or planet — the")
        lines.append("ingress carries the planet TOWARD that personal point (check the keystone/aspects).")
        for ing in slow_ingresses:
            retro_mark = " ℞" if ing['retrograde'] else ""
            lines.append(f"  • {_date_full_en(ing['date'])}: {_planet(ing['planet'])} moves from {_sign(ing['from_sign'])} to {_sign(ing['to_sign'])}{retro_mark}")
        lines.append("")

    # STATIONS
    if ranked['stations']:
        lines.append("─" * 70)
        lines.append("⏸ RETROGRADE STATIONS — TURNING POINTS")
        lines.append("─" * 70)
        for st in ranked['stations']:
            type_en = "goes retrograde ℞" if st['type'] == 'retrograde' else "goes direct D"
            lines.append(f"  • {_date_full_en(st['date'])}: {_planet(st['planet'])} {type_en} ({_sign(st['sign'])} {st['deg_in_sign']}°)")
        lines.append("")

    # WORLD / MUNDANE CONFIGURATIONS — aspects BETWEEN transiting slow planets (the era's backdrop)
    mundane = ranked.get('mundane_aspects', [])
    if mundane:
        lines.append("\u2550" * 70)
        lines.append("\U0001F30D WORLD CONFIGURATIONS \u2014 great aspects BETWEEN slow planets (the backdrop of the era)")
        lines.append("\u2550" * 70)
        lines.append("These configurations are the same for everyone alive now \u2014 the weather of the age,")
        lines.append("not personal. They unfold over years (toward ~2030) and shape the world situationally")
        lines.append("and through events. Describe the major ones as the LARGER FRAME the personal year sits")
        lines.append("inside \u2014 then show how this backdrop touches THIS person through their own chart.")
        lines.append("")
        for mu in mundane:
            state = "applying (tightening)" if mu['applying'] else "separating (loosening)"
            exact = "EXACT this year" if mu['exact_in_year'] else f"closest orb {mu['peak_orb']}\u00b0, building toward exact in coming years"
            lines.append(
                f"  \U0001F30D {_planet(mu['p1'])} {_aspect(mu['aspect'])} {_planet(mu['p2'])} \u2014 "
                f"{exact}, {state}; closest around {_date_full_en(mu['peak_date'])}, "
                f"in orb {_date_en(mu['window_start'])}\u2013{_date_en(mu['window_end'])}."
            )
        lines.append("")

    # WORLD ↔ PERSONAL BRIDGE — where the era's configuration lands on ONE point of THIS chart
    bridges = ranked.get('world_personal_bridges', [])
    if bridges:
        lines.append("\u2550" * 70)
        lines.append("\U0001F305 WHERE THE WORLD CONFIGURATION TOUCHES YOU PERSONALLY \u2014 the year's keystone")
        lines.append("\u2550" * 70)
        lines.append("This is the MOST IMPORTANT thing in the year: several slow planets of the era's")
        lines.append("great configuration strike ONE point of the personal chart at once. Here the weather")
        lines.append("of the age becomes personal fate. Treat each as a SINGLE grand event (not separate")
        lines.append("aspects), unfold it most deeply of all \u2014 especially on an angle or luminary.")
        lines.append("")
        for br in bridges:
            tag = "ANGLE (vocation/identity axis)" if br['is_angle'] else ("LUMINARY (core self)" if br['is_luminary'] else "natal point")
            parts = ", ".join(
                f"{_planet(a['planet'])} {_aspect(a['aspect'])} ({_date_en(a['date'])}, orb {a['orb']}\u00b0)"
                for a in br['aspects'])
            lines.append(
                f"  \U0001F305 The era's planets converge on {br['target_label']}-{_planet(br['target'])} "
                f"[{tag}]: {parts}. The world's great shift includes THIS point of the chart \u2014 "
                f"personal destiny woven into the configuration of the age."
            )
        lines.append("")

    # MONTH-BY-MONTH TIMELINE — all aspect events in chronological flow (the year's dynamics).
    # Replaces the by-importance grouping so the year reads as a living sequence, nothing dropped.
    _timeline = []
    for ev in ranked['critical_natal']:
        _timeline.append((ev['exact_date'], ev, 'natal', True))
    for ev in ranked['critical_solar']:
        _timeline.append((ev['exact_date'], ev, 'solar', True))
    for ev in ranked['significant_natal']:
        _timeline.append((ev['exact_date'], ev, 'natal', False))
    for ev in ranked['significant_solar']:
        _timeline.append((ev['exact_date'], ev, 'solar', False))
    if _timeline:
        _timeline.sort(key=lambda x: x[0])
        lines.append("\u2550" * 70)
        lines.append("\U0001F4C5 MONTH-BY-MONTH DYNAMICS \u2014 every aspect of the year in chronological flow")
        lines.append("\u2550" * 70)
        lines.append("This is the living fabric of the year. Walk through it month by month, in order,")
        lines.append("missing NO event. \u2b50 = major (unfold deeply, with its window); the others are the")
        lines.append("texture of the year's rise and fall \u2014 weave them into the narrative, do not drop them.")
        lines.append("")
        _cur = None
        for d, ev, kind, is_crit in _timeline:
            key = (d.year, d.month)
            if key != _cur:
                _cur = key
                lines.append(f"\u25b8 {MONTHS_EN[d.month]} {d.year}")
            star = "\u2b50 " if is_crit else "\u2022 "
            retro_mark = " \u211e" if ev['transit_retrograde'] else ""
            window = ""
            if is_crit and ev['window_start'] != ev['window_end']:
                window = f" [in orb {_date_en(ev['window_start'])}\u2013{_date_en(ev['window_end'])}]"
            hint = f"  \u2192 {_hint(_hint_for_target(ev['target']))}" if is_crit else ""
            lines.append(
                f"  {star}{_date_en(ev['exact_date'])}: {_planet(ev['transit_planet'])}{retro_mark} "
                f"{_aspect(ev['aspect'])} {kind}-{_planet(ev['target'])} "
                f"({_sign(ev['target_position_sign'])} {ev['target_position_deg']}\u00b0, orb {ev['orb']}\u00b0){window}{hint}"
            )
        lines.append("")

    # NATAL HOUSE INGRESSES (slow only)
    slow_ing_natal = [i for i in ranked['house_ingresses_natal'] if i['transit_planet'] != 'Марс']
    if slow_ing_natal:
        lines.append("─" * 70)
        lines.append("🏠 SLOW PLANETS ENTERING NATAL HOUSES (activation of life spheres)")
        lines.append("─" * 70)
        for ing in slow_ing_natal:
            retro_mark = " ℞" if ing['retrograde'] else ""
            lines.append(
                f"  • {_date_full_en(ing['date'])}: {_planet(ing['transit_planet'])}{retro_mark} "
                f"enters natal house {ing['to_house']} (leaving house {ing['from_house']})"
            )
        lines.append("")

    # SOLAR HOUSE INGRESSES (slow only)
    slow_ing_solar = [i for i in ranked['house_ingresses_solar'] if i['transit_planet'] != 'Марс']
    if slow_ing_solar:
        lines.append("─" * 70)
        lines.append("🏠 SLOW PLANETS ENTERING SOLAR HOUSES (yearly theme dynamics)")
        lines.append("─" * 70)
        for ing in slow_ing_solar:
            retro_mark = " ℞" if ing['retrograde'] else ""
            lines.append(
                f"  • {_date_full_en(ing['date'])}: {_planet(ing['transit_planet'])}{retro_mark} "
                f"enters solar house {ing['to_house']} (leaving house {ing['from_house']})"
            )
        lines.append("")

    # LEVEL 3: MARS TRIGGERS (monthly summary)
    mars_natal = ranked['mars_triggers_natal']
    mars_solar = ranked['mars_triggers_solar']
    if mars_natal or mars_solar:
        lines.append("─" * 70)
        lines.append("⚡ LEVEL 3 — MARS TRIGGERS (activators by month, use for dynamics)")
        lines.append("─" * 70)
        all_months = sorted(set(list(mars_natal.keys()) + list(mars_solar.keys())))
        for m in all_months:
            month_label = MONTHS_EN[m]
            natal_evs = mars_natal.get(m, [])
            solar_evs = mars_solar.get(m, [])
            parts_natal = [f"{_aspect(ev['aspect'])} natal-{_planet(ev['target'])} ({ev['exact_date'].day}th)" for ev in natal_evs]
            parts_solar = [f"{_aspect(ev['aspect'])} solar-{_planet(ev['target'])} ({ev['exact_date'].day}th)" for ev in solar_evs]
            line = f"  {month_label}:"
            if parts_natal:
                line += " natal: " + ", ".join(parts_natal) + "."
            if parts_solar:
                line += " solar: " + ", ".join(parts_solar) + "."
            lines.append(line)
        lines.append("")

    lines.append("=" * 70)
    crit = len(ranked['critical_natal']) + len(ranked['critical_solar'])
    sig = len(ranked['significant_natal']) + len(ranked['significant_solar'])
    mars_total = sum(len(v) for v in mars_natal.values()) + sum(len(v) for v in mars_solar.values())
    lines.append(f"TOTAL: {crit} critical, {sig} significant, {mars_total} Mars triggers")
    lines.append("=" * 70)

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# МНОГОЛЕТНИЕ ТРАНЗИТЫ МЕДЛЕННЫХ ПЛАНЕТ
# ════════════════════════════════════════════════════════════════════
"""
Многолетние транзиты Плутона, Нептуна, Урана, Сатурна к натальным
светилам (Солнце, Луна), углам (ASC, MC, IC, DSC) и натальному узлу.

Это «фоновые» транзиты, действующие 2-7 лет вокруг соляра, которые
формируют большой контекст жизни. В отличие от годовых активаций
(они уже считаются `calculate_transit_activations`), эти транзиты
показывают многолетние циклы.

Орбисы:
- Орбис "входа в окно" — 3° (когда транзит начинает действовать)
- Орбис "пика" — 1° (когда транзит на пике силы)
"""

LT_WINDOW_ORB = 3.0
LT_PEAK_ORB = 1.0
LT_EXACT_ORB = 0.1

LT_HORIZON_BEFORE = 1
LT_HORIZON_AFTER = {
    'Pluto': 7,
    'Neptune': 5,
    'Uranus': 3,
    'Saturn': 2,
}

LT_TRANSITING_PLANETS = ['Pluto', 'Neptune', 'Uranus', 'Saturn']
LT_TARGET_PLANETS = ['Sun', 'Moon']
LT_TARGET_ANGLES = ['ASC', 'MC', 'IC', 'DSC']

LT_MAJOR_ASPECTS = [
    ('соединение', 0),
    ('оппозиция', 180),
    ('квадрат', 90),
    ('трин', 120),
    ('секстиль', 60),
]

LT_PLANET_RU = {
    'Pluto': 'Плутон',
    'Neptune': 'Нептун',
    'Uranus': 'Уран',
    'Saturn': 'Сатурн',
    'Sun': 'Солнце',
    'Moon': 'Луна',
}

# Маппинг русских имён натальных таргетов → английские стандартные ключи
# (натальная карта от astro_engine использует русские имена)
_RU_TO_EN_TARGET = {
    'Солнце': 'Sun',
    'Луна': 'Moon',
    'Меркурий': 'Mercury',
    'Венера': 'Venus',
    'Марс': 'Mars',
    'Юпитер': 'Jupiter',
    'Сатурн': 'Saturn',
    'Уран': 'Uranus',
    'Нептун': 'Neptune',
    'Плутон': 'Pluto',
    'Хирон': 'Chiron',
    'Сев.Узел': 'NorthNode',
    'ASC': 'ASC',
    'MC': 'MC',
    'IC': 'IC',
    'DSC': 'DSC',
}


def calculate_long_term_transits(natal_subject, solar_subject):
    """
    Считает многолетние транзиты медленных планет к натальным точкам.

    Возвращает dict:
        {'transits': [...], 'horizon_years': {...},
         'years_scanned': (start, end), 'solar_year': int}
    """
    natal_targets = _extract_target_points(natal_subject, label='natal')

    # natal_targets — это dict {name: pos}. Узел уже там как "Сев.Узел"
    # благодаря NATAL_PLANETS в astro_engine. Дополнительно ничего не добавляем.

    solar_year = solar_subject.year
    lat = solar_subject.lat
    lng = solar_subject.lng
    tz = solar_subject.tz_str

    all_transits = []

    for tp_name in LT_TRANSITING_PLANETS:
        years_ahead = LT_HORIZON_AFTER.get(tp_name, 2)
        start_date = datetime(solar_year - LT_HORIZON_BEFORE, 1, 1)
        end_date = datetime(solar_year + years_ahead, 12, 31)

        ephemeris = _build_long_term_ephemeris(
            start_date, end_date, step_days=7, lat=lat, lng=lng, tz=tz,
            planet_name=tp_name
        )
        if not ephemeris:
            continue

        for tname, tpos in natal_targets.items():
            # natal_targets содержит русские имена: Солнце, Луна, Сев.Узел и т.д.
            # Маппим к английским для проверки
            tname_en = _RU_TO_EN_TARGET.get(tname, tname)
            if tname_en not in LT_TARGET_PLANETS + LT_TARGET_ANGLES + ['NorthNode']:
                continue

            for asp_name, asp_angle in LT_MAJOR_ASPECTS:
                events = _find_long_term_aspect_events(
                    ephemeris, tpos, asp_angle, asp_name,
                    tp_name, tname_en, lat, lng, tz
                )
                all_transits.extend(events)

    all_transits.sort(key=lambda x: x['first_contact_date'] or '9999')

    return {
        'transits': all_transits,
        'horizon_years': LT_HORIZON_AFTER,
        'years_scanned': (solar_year - LT_HORIZON_BEFORE,
                          solar_year + max(LT_HORIZON_AFTER.values())),
        'solar_year': solar_year,
    }


def _build_long_term_ephemeris(start_date, end_date, step_days, lat, lng, tz,
                                planet_name):
    """Эфемерида одной планеты на длинный промежуток."""
    try:
        from kerykeion import EphemerisDataFactory
        factory = EphemerisDataFactory(
            start_datetime=start_date,
            end_datetime=end_date,
            step_type='days',
            step=step_days,
            lat=lat,
            lng=lng,
            tz_str=tz,
        )
        subjects = factory.get_ephemeris_data_as_astrological_subjects()
        ephem = []
        for s in subjects:
            try:
                p = getattr(s, planet_name.lower())
                ephem.append({
                    'date': datetime(s.year, s.month, s.day, s.hour, s.minute),
                    'pos': p.abs_pos,
                    'retro': getattr(p, 'retrograde', False),
                })
            except Exception:
                continue
        return ephem
    except Exception:
        ephem = []
        d = start_date
        while d <= end_date:
            try:
                s = _get_transit_subject(d, lat=lat, lng=lng, tz=tz)
                p = getattr(s, planet_name.lower())
                ephem.append({
                    'date': d,
                    'pos': p.abs_pos,
                    'retro': getattr(p, 'retrograde', False),
                })
            except Exception:
                pass
            d += timedelta(days=step_days)
        return ephem


def _find_long_term_aspect_events(ephemeris, target_pos, target_angle,
                                    aspect_name, transiting_planet,
                                    target_name, lat, lng, tz):
    """Находит все события аспекта (могут быть три касания из-за ретро)."""
    events = []
    if not ephemeris:
        return events

    orbs = []
    for e in ephemeris:
        orb = _aspect_orb(e['pos'], target_pos, target_angle)
        orbs.append({'date': e['date'], 'orb': orb, 'pos': e['pos'],
                     'retro': e['retro']})

    contacts = []
    for i in range(1, len(orbs) - 1):
        if orbs[i]['orb'] < orbs[i-1]['orb'] and orbs[i]['orb'] < orbs[i+1]['orb']:
            if orbs[i]['orb'] <= LT_WINDOW_ORB:
                contacts.append({
                    'approx_date': orbs[i]['date'],
                    'min_orb': orbs[i]['orb'],
                    'idx': i,
                })

    # FALLBACK: если локальных минимумов нет, но в окне есть точки в орбисе ≤3°,
    # значит планета монотонно приближается (или отдаляется) — берём ГЛОБАЛЬНЫЙ
    # минимум как событие. Это ловит транзиты которые ещё только входят в орбис
    # к концу горизонта (например Плутон-Солнце пик в 2029-2031, начинает входить
    # в орбис в 2026-2027).
    if not contacts:
        in_window = [o for o in orbs if o['orb'] <= LT_WINDOW_ORB]
        if in_window:
            # Глобальный минимум по всему окну
            min_orb_entry = min(orbs, key=lambda x: x['orb'])
            if min_orb_entry['orb'] <= LT_WINDOW_ORB:
                min_idx = orbs.index(min_orb_entry)
                contacts.append({
                    'approx_date': min_orb_entry['date'],
                    'min_orb': min_orb_entry['orb'],
                    'idx': min_idx,
                    'is_approaching': True,  # маркер «приближающийся транзит»
                })

    if not contacts:
        return events

    for contact in contacts:
        if contact['min_orb'] > LT_PEAK_ORB:
            refined_date = contact['approx_date']
            refined_orb = contact['min_orb']
        else:
            try:
                fine_start = contact['approx_date'] - timedelta(days=15)
                fine_end = contact['approx_date'] + timedelta(days=15)
                fine_ephem = _build_long_term_ephemeris(
                    fine_start, fine_end, step_days=1, lat=lat, lng=lng, tz=tz,
                    planet_name=transiting_planet
                )
                best = None
                for fe in fine_ephem:
                    orb = _aspect_orb(fe['pos'], target_pos, target_angle)
                    if best is None or orb < best['orb']:
                        best = {'date': fe['date'], 'orb': orb, 'pos': fe['pos']}
                if best:
                    refined_date = best['date']
                    refined_orb = best['orb']
                else:
                    refined_date = contact['approx_date']
                    refined_orb = contact['min_orb']
            except Exception:
                refined_date = contact['approx_date']
                refined_orb = contact['min_orb']

        window_start = None
        window_end = None
        for j in range(contact['idx'], -1, -1):
            if orbs[j]['orb'] > LT_WINDOW_ORB:
                window_start = orbs[j+1]['date'] if j+1 < len(orbs) else orbs[j]['date']
                break
        else:
            window_start = orbs[0]['date']
        for j in range(contact['idx'], len(orbs)):
            if orbs[j]['orb'] > LT_WINDOW_ORB:
                window_end = orbs[j-1]['date'] if j-1 >= 0 else orbs[j]['date']
                break
        else:
            window_end = orbs[-1]['date']

        events.append({
            'transiting_planet': transiting_planet,
            'target': target_name,
            'aspect': aspect_name,
            'aspect_angle': target_angle,
            'first_contact_date': refined_date.strftime('%Y-%m-%d')
                                   if refined_date else None,
            'pic_orb': round(refined_orb, 4),
            'is_approaching': contact.get('is_approaching', False),
            'window_start': window_start.strftime('%Y-%m-%d')
                              if window_start else None,
            'window_end': window_end.strftime('%Y-%m-%d') if window_end else None,
            'target_pos': round(target_pos, 4),
        })

    if len(events) > 1:
        for i in range(len(events)):
            events[i]['contacts_total'] = len(events)
            events[i]['contact_number'] = i + 1

    return events


def format_long_term_for_prompt(data, lang='ru'):
    """Форматирует многолетние транзиты для подачи в LLM-промпт."""
    if lang == 'ru':
        return _format_lt_ru(data)
    return _format_lt_en(data)


def _format_lt_ru(d):
    """Компактный вывод многолетних транзитов — только цифры."""
    lines = []
    lines.append(f"[МНОГОЛЕТНИЕ ТРАНЗИТЫ] год соляра {d['solar_year']}, горизонт {d['years_scanned'][0]}–{d['years_scanned'][1]}")

    transits = d.get('transits', [])
    if not transits:
        lines.append("  (нет активных)")
        return '\n'.join(lines)

    by_planet = {}
    for t in transits:
        by_planet.setdefault(t['transiting_planet'], []).append(t)

    for planet in ['Pluto', 'Neptune', 'Uranus', 'Saturn']:
        if planet not in by_planet:
            continue
        planet_ru = LT_PLANET_RU.get(planet, planet)
        for ev in by_planet[planet]:
            target_ru = LT_PLANET_RU.get(ev['target'], ev['target'])
            asp = ev['aspect']
            line = f"  {planet_ru} {asp} натал-{target_ru}"
            if ev.get('is_approaching'):
                line += f", ПРИБЛИЖАЕТСЯ ~{ev['first_contact_date']} (орбис {ev['pic_orb']:.2f}°)"
            elif ev.get('first_contact_date'):
                line += f", пик ~{ev['first_contact_date']} (орбис {ev['pic_orb']:.2f}°)"
            if ev.get('window_start') and ev.get('window_end'):
                line += f", окно {ev['window_start']}→{ev['window_end']}"
            if ev.get('contacts_total', 1) > 1:
                line += f" [{ev['contact_number']}/{ev['contacts_total']}]"
            lines.append(line)

    return '\n'.join(lines)


def _format_lt_en(d):
    """Compact long-term transits output — numbers only."""
    lines = []
    lines.append(f"[LONG-TERM TRANSITS] solar year {d['solar_year']}, horizon {d['years_scanned'][0]}–{d['years_scanned'][1]}")

    transits = d.get('transits', [])
    if not transits:
        lines.append("  (no active)")
        return '\n'.join(lines)

    by_planet = {}
    for t in transits:
        by_planet.setdefault(t['transiting_planet'], []).append(t)

    for planet in ['Pluto', 'Neptune', 'Uranus', 'Saturn']:
        if planet not in by_planet:
            continue
        for ev in by_planet[planet]:
            asp = ev['aspect']
            line = f"  {planet} {asp} natal-{ev['target']}"
            if ev.get('is_approaching'):
                line += f", APPROACHING ~{ev['first_contact_date']} (orb {ev['pic_orb']:.2f}°)"
            elif ev.get('first_contact_date'):
                line += f", peak ~{ev['first_contact_date']} (orb {ev['pic_orb']:.2f}°)"
            if ev.get('window_start') and ev.get('window_end'):
                line += f", window {ev['window_start']}→{ev['window_end']}"
            if ev.get('contacts_total', 1) > 1:
                line += f" [{ev['contact_number']}/{ev['contacts_total']}]"
            lines.append(line)

    return '\n'.join(lines)
