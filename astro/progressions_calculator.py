"""
astro/progressions_calculator.py — модуль расчёта вторичных прогрессий для соляра.

Вторичные прогрессии (Secondary Progressions) — классическая прогностическая
техника: натальная карта прогрессируется по правилу «день за год». То есть
для расчёта прогрессивной карты на возраст N лет берётся натальная позиция
на (N) дней после рождения.

Прогрессии показывают ВНУТРЕННЕЕ психологическое разворачивание:
- Прогрессивное Солнце — медленно меняет знак ~раз в 30 лет, показывает
  смену фазы жизни.
- Прогрессивная Луна — движется ~1° в месяц (~13° в год), проходит знак
  за 2.5 года и весь зодиак за ~28 лет. Показывает эмоциональный тон
  периода.
- Прогрессивные личные планеты (Меркурий, Венера, Марс) — медленно
  меняются, дают точечные внутренние события через аспекты к натальной
  карте.
- Прогрессивные узлы — двигаются очень медленно, обратно (~0.05°/год).

Дополнительно считаем:
- ЛУННЫЙ ВОЗРАСТ СОЛЯРА — фаза цикла Луна-Солнце в момент соляра.
  Показывает «тип года»: рождающий, реализующий или закрывающий.
- ПРОГРЕССИВНАЯ ФАЗА ЛУНА-СОЛНЦЕ — текущая фаза 30-летнего жизненного цикла
  (по Дэйну Радьяру).

Орбисы:
- Прогрессивная Луна → натальные: 1.5°
- Прогрессивное Солнце → натальные: 1.0° (Солнце почти не двигается)
- Прогрессивные личные планеты → натальные: 1.0°
- Все прогрессии → солярные: 1.5°
"""

from datetime import datetime, timedelta
from astro.astro_engine import (
    chart_from_subject,
    angular_distance,
    SIGNS_RU,
    SIGNS_EN,
    MAJOR_ASPECTS,
    degree_to_house,
)

# Орбисы
ORBIS_MOON_TO_NATAL = 1.5
ORBIS_SUN_TO_NATAL = 1.0
ORBIS_PERSONAL_TO_NATAL = 1.0
ORBIS_TO_SOLAR = 1.5
ORBIS_NODES = 2.0

# Символы аспектов
ASPECT_SYMBOLS = {
    'соединение': '☌',
    'секстиль': '⚹',
    'квадрат': '□',
    'трин': '△',
    'оппозиция': '☍',
}
RU_TO_EN_ASPECT = {
    'соединение': 'conjunction',
    'секстиль': 'sextile',
    'квадрат': 'square',
    'трин': 'trine',
    'оппозиция': 'opposition',
}
ASPECT_SYMBOLS_EN = {
    'conjunction': '☌',
    'sextile': '⚹',
    'square': '□',
    'trine': '△',
    'opposition': '☍',
}

# Лунные фазы (Луна-Солнце по углу) — 8 классических фаз по Радьяру
LUNAR_PHASES = [
    (0, 45, 'Новолуние', 'New Moon',
     'рождающая фаза: посев новой темы, инстинктивное движение, импульс начала'),
    (45, 90, 'Растущий серп', 'Crescent Moon',
     'фаза действия и преодоления сопротивления — посеянное приходит в столкновение с препятствиями'),
    (90, 135, 'Первая четверть', 'First Quarter',
     'кризис действия: момент прорыва через сопротивление, требование действия здесь и сейчас'),
    (135, 180, 'Растущая выпуклая', 'Gibbous Moon',
     'фаза роста и осмысления: то что посеяно растёт, требует анализа и шлифовки'),
    (180, 225, 'Полнолуние', 'Full Moon',
     'фаза реализации и ясного видения: то что зрело становится видимым, обретает форму, требует осознанной коммуникации'),
    (225, 270, 'Разорванная выпуклая', 'Disseminating Moon',
     'фаза служения и передачи плодов: накопленное должно быть передано миру, разделено с другими'),
    (270, 315, 'Последняя четверть', 'Last Quarter',
     'кризис осознания: переоценка пройденного пути, отделение жизнеспособного от исчерпанного'),
    (315, 360, 'Бальзамическая Луна', 'Balsamic Moon',
     'фаза отпускания и подготовки: завершение цикла, освобождение от прошлого, подготовка нового семени'),
]


def calculate_progressions(natal_subject, solar_subject, prog_subject=None):
    """
    Главная функция: считает вторичные прогрессии для соляра.

    Параметры:
        natal_subject: kerykeion AstrologicalSubject — натальная карта
        solar_subject: kerykeion AstrologicalSubject — солярная карта
        prog_subject: optional, прогрессивный субъект (если уже посчитан)

    Возвращает dict со всеми ключевыми данными прогрессий.
    """
    nc = chart_from_subject(natal_subject)
    sc = chart_from_subject(solar_subject)

    natal_dt = datetime(natal_subject.year, natal_subject.month, natal_subject.day,
                        natal_subject.hour, natal_subject.minute)
    solar_dt = datetime(solar_subject.year, solar_subject.month, solar_subject.day,
                        solar_subject.hour, solar_subject.minute)
    age_years = (solar_dt - natal_dt).days / 365.2422

    # Прогрессивный субъект (день за год)
    if prog_subject is None:
        from kerykeion import AstrologicalSubjectFactory
        prog_date = natal_dt + timedelta(days=age_years)
        prog_subject = AstrologicalSubjectFactory.from_birth_data(
            'Progressed',
            prog_date.year, prog_date.month, prog_date.day,
            prog_date.hour, prog_date.minute,
            lng=natal_subject.lng, lat=natal_subject.lat,
            tz_str=natal_subject.tz_str, online=False
        )
    pc = chart_from_subject(prog_subject)

    # Натальные таргеты и солярные таргеты
    natal_targets = _build_targets(nc, natal_subject, prefix='натал_')
    solar_targets = _build_targets(sc, solar_subject, prefix='соляр_')

    # Прогрессивные данные по каждой ключевой планете
    progressed_data = {}

    # Прогрессивное Солнце
    progressed_data['progressed_sun'] = _build_planet_data(
        prog_subject.sun, 'Sun', 'Солнце', nc, sc,
        natal_targets, solar_targets, orbis=ORBIS_SUN_TO_NATAL, solar_dt=solar_dt
    )
    # Прогрессивная Луна (с расчётом смены знака/дома в течение года)
    progressed_data['progressed_moon'] = _build_moon_data(
        natal_subject, solar_subject, prog_subject, nc, sc,
        natal_targets, solar_targets, age_years
    )
    # Прогрессивный Меркурий
    progressed_data['progressed_mercury'] = _build_planet_data(
        prog_subject.mercury, 'Mercury', 'Меркурий', nc, sc,
        natal_targets, solar_targets, orbis=ORBIS_PERSONAL_TO_NATAL, solar_dt=solar_dt
    )
    # Прогрессивная Венера
    progressed_data['progressed_venus'] = _build_planet_data(
        prog_subject.venus, 'Venus', 'Венера', nc, sc,
        natal_targets, solar_targets, orbis=ORBIS_PERSONAL_TO_NATAL, solar_dt=solar_dt
    )
    # Прогрессивный Марс
    progressed_data['progressed_mars'] = _build_planet_data(
        prog_subject.mars, 'Mars', 'Марс', nc, sc,
        natal_targets, solar_targets, orbis=ORBIS_PERSONAL_TO_NATAL, solar_dt=solar_dt
    )
    # Прогрессивные узлы
    try:
        progressed_data['progressed_north_node'] = _build_node_data(
            prog_subject.true_north_lunar_node, 'NN', 'Сев.Узел',
            nc, sc, natal_targets, solar_targets
        )
        progressed_data['progressed_south_node'] = _build_node_data(
            prog_subject.true_south_lunar_node, 'SN', 'Юж.Узел',
            nc, sc, natal_targets, solar_targets
        )
    except Exception:
        pass

    # Лунный возраст соляра (фаза Луна-Солнце соляра)
    solar_lunar_phase = (solar_subject.moon.abs_pos - solar_subject.sun.abs_pos) % 360
    lunar_age_data = _identify_lunar_phase(solar_lunar_phase)

    # Прогрессивная фаза Луна-Солнце (30-летний жизненный цикл)
    prog_lunar_phase = (prog_subject.moon.abs_pos - prog_subject.sun.abs_pos) % 360
    progressive_phase_data = _identify_lunar_phase(prog_lunar_phase)

    return {
        'age_years': round(age_years, 4),
        'progressive_date': (natal_dt + timedelta(days=age_years)).isoformat(),
        'progressed_data': progressed_data,
        'lunar_age_of_solar': lunar_age_data,
        'progressive_lunar_phase': progressive_phase_data,
        # Сводные списки всех точных аспектов
        'all_critical_to_natal': _collect_all_critical(progressed_data, 'aspects_to_natal'),
        'all_critical_to_solar': _collect_all_critical(progressed_data, 'aspects_to_solar'),
    }


def _build_planet_data(planet, name_en, name_ru, nc, sc, natal_targets, solar_targets, orbis, solar_dt=None):
    """Собирает данные по прогрессивной планете."""
    pos = planet.abs_pos
    return {
        'name_ru': name_ru,
        'name_en': name_en,
        'pos': round(pos, 4),
        'sign_ru': SIGNS_RU[int(pos // 30)],
        'sign_en': SIGNS_EN[int(pos // 30)],
        'deg_in_sign': round(pos % 30, 2),
        'natal_house': degree_to_house(pos, nc['cusps']),
        'solar_house': degree_to_house(pos, sc['cusps']),
        'aspects_to_natal': _find_aspects(pos, f"prog_{name_ru}", natal_targets, orbis,
                                          speed=_PROG_SPEED.get(name_ru), solar_dt=solar_dt),
        'aspects_to_solar': _find_aspects(pos, f"prog_{name_ru}", solar_targets, ORBIS_TO_SOLAR,
                                          speed=_PROG_SPEED.get(name_ru), solar_dt=solar_dt),
    }


def _build_moon_data(natal_subject, solar_subject, prog_subject, nc, sc,  # solar_dt derived below
                     natal_targets, solar_targets, age_years):
    """
    Прогрессивная Луна — отдельный объект с расчётом смены знака и дома
    в течение года соляра.
    """
    from datetime import datetime as _dt
    _moon_solar_dt = _dt(solar_subject.year, solar_subject.month, solar_subject.day)
    moon = prog_subject.moon
    pos = moon.abs_pos
    base_data = {
        'name_ru': 'Луна',
        'name_en': 'Moon',
        'pos': round(pos, 4),
        'sign_ru': SIGNS_RU[int(pos // 30)],
        'sign_en': SIGNS_EN[int(pos // 30)],
        'deg_in_sign': round(pos % 30, 2),
        'natal_house': degree_to_house(pos, nc['cusps']),
        'solar_house': degree_to_house(pos, sc['cusps']),
        'aspects_to_natal': _find_aspects(pos, "prog_Луна", natal_targets, ORBIS_MOON_TO_NATAL,
                                          speed=_PROG_SPEED['Луна'], solar_dt=_moon_solar_dt),
        'aspects_to_solar': _find_aspects(pos, "prog_Луна", solar_targets, ORBIS_TO_SOLAR,
                                          speed=_PROG_SPEED['Луна'], solar_dt=_moon_solar_dt),
    }

    # Расчёт прогрессивной Луны на конец года соляра (+12 месяцев = +12 дней прогрессии)
    natal_dt = datetime(natal_subject.year, natal_subject.month, natal_subject.day,
                        natal_subject.hour, natal_subject.minute)
    year_end_age = age_years + 1.0
    try:
        from kerykeion import AstrologicalSubjectFactory
        year_end_date = natal_dt + timedelta(days=year_end_age)
        prog_year_end = AstrologicalSubjectFactory.from_birth_data(
            'ProgYearEnd',
            year_end_date.year, year_end_date.month, year_end_date.day,
            year_end_date.hour, year_end_date.minute,
            lng=natal_subject.lng, lat=natal_subject.lat,
            tz_str=natal_subject.tz_str, online=False
        )
        moon_at_year_end = prog_year_end.moon.abs_pos
        base_data['pos_at_year_end'] = round(moon_at_year_end, 4)
        base_data['sign_ru_at_year_end'] = SIGNS_RU[int(moon_at_year_end // 30)]
        base_data['sign_en_at_year_end'] = SIGNS_EN[int(moon_at_year_end // 30)]
        base_data['natal_house_at_year_end'] = degree_to_house(moon_at_year_end, nc['cusps'])
        base_data['movement_degrees'] = round((moon_at_year_end - pos) % 360, 2)

        # Смена знака в течение года?
        if base_data['sign_ru'] != base_data['sign_ru_at_year_end']:
            base_data['sign_change_in_year'] = {
                'from': base_data['sign_ru'],
                'to': base_data['sign_ru_at_year_end'],
                'from_en': base_data['sign_en'],
                'to_en': base_data['sign_en_at_year_end'],
            }
            # Поиск точной даты смены знака (бинарный поиск)
            target_deg = (int(pos // 30) + 1) * 30
            change_date = _find_moon_crossing_date(
                natal_subject, age_years, year_end_age, target_deg
            )
            if change_date:
                base_data['sign_change_in_year']['date'] = change_date

        # Смена натал-дома в течение года?
        if base_data['natal_house'] != base_data['natal_house_at_year_end']:
            base_data['house_change_in_year'] = {
                'from': base_data['natal_house'],
                'to': base_data['natal_house_at_year_end'],
            }
            # Поиск точной даты пересечения куспида
            # Куспид следующего дома
            next_house_idx = base_data['natal_house'] % 12  # 0-11
            target_cusp = nc['cusps'][next_house_idx]
            change_date = _find_moon_crossing_date(
                natal_subject, age_years, year_end_age, target_cusp
            )
            if change_date:
                base_data['house_change_in_year']['date'] = change_date
    except Exception as e:
        base_data['year_end_error'] = str(e)

    return base_data


def _build_node_data(node, name_en, name_ru, nc, sc, natal_targets, solar_targets):
    """Собирает данные по прогрессивному узлу."""
    pos = node.abs_pos
    return {
        'name_ru': name_ru,
        'name_en': name_en,
        'pos': round(pos, 4),
        'sign_ru': SIGNS_RU[int(pos // 30)],
        'sign_en': SIGNS_EN[int(pos // 30)],
        'deg_in_sign': round(pos % 30, 2),
        'natal_house': degree_to_house(pos, nc['cusps']),
        'aspects_to_natal': _find_aspects(pos, f"prog_{name_ru}", natal_targets, ORBIS_NODES),
        'aspects_to_solar': _find_aspects(pos, f"prog_{name_ru}", solar_targets, ORBIS_NODES),
    }


def _build_targets(chart, subject, prefix=''):
    """Собирает таргеты для сравнения с прогрессиями."""
    targets = []
    for p in chart['planets']:
        targets.append({'name': f"{prefix}{p['name']}", 'deg': p['deg']})
    for a in chart['angles']:
        targets.append({'name': f"{prefix}{a['name']}", 'deg': a['deg']})
    try:
        targets.append({'name': f"{prefix}Сев.Узел",
                       'deg': subject.true_north_lunar_node.abs_pos})
        targets.append({'name': f"{prefix}Юж.Узел",
                       'deg': subject.true_south_lunar_node.abs_pos})
    except Exception:
        pass
    return targets


_PROG_SPEED = {'Солнце': 1.0, 'Луна': 13.2, 'Меркурий': 1.4, 'Венера': 1.2, 'Марс': 0.5}
_PROG_MONTHS = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def _prog_dates(prog_deg, target_deg, asp_angle, speed, solar_dt):
    """Дата точного контакта прогрессии и окно ±1° — со скоростью данной планеты.

    Луна ~13°/год → окно ~2 месяца; Солнце ~1°/год → ~2 года. Медленные точки
    (|speed|<0.15) пропускаем — они действуют весь год фоном, дата не информативна.
    """
    from datetime import timedelta
    if not speed or abs(speed) < 0.15 or solar_dt is None:
        return None, None, None
    cands = []
    for off in (asp_angle, -asp_angle):
        delta = (((target_deg + off) - prog_deg + 180) % 360) - 180
        cands.append(delta)
    signed = min(cands, key=abs)
    try:
        exact = solar_dt + timedelta(days=(signed / speed) * 365.2422)
        half = (1.0 / abs(speed)) * 365.2422
        return (exact.date(),
                (exact - timedelta(days=half)).date(),
                (exact + timedelta(days=half)).date())
    except Exception:
        return None, None, None


def _prog_date_suffix(a):
    ed = a.get('exact_date')
    if not ed:
        return ""
    s = f"  → точный контакт ~{ed.day} {_PROG_MONTHS[ed.month]} {ed.year}"
    ws, we = a.get('window_start'), a.get('window_end')
    if ws and we:
        s += (f" (в орбе с {ws.day} {_PROG_MONTHS[ws.month]} {ws.year} "
              f"по {we.day} {_PROG_MONTHS[we.month]} {we.year})")
    return s


def _find_aspects(prog_pos, prog_name, targets, orbis, speed=None, solar_dt=None):
    """Ищет аспекты прогрессивной точки к таргетам с заданным орбисом."""
    base_prog = prog_name.replace('prog_', '')
    results = []
    for t in targets:
        base_t = t['name'].replace('натал_', '').replace('соляр_', '')
        # Пропустить аспект к той же натальной планете (это близкая позиция,
        # не аспект)
        if base_prog == base_t and 'натал_' in t['name']:
            continue
        dist = angular_distance(prog_pos, t['deg'])
        for asp_name, asp_angle in MAJOR_ASPECTS:
            orb = abs(dist - asp_angle)
            if orb <= orbis:
                _ed, _ws, _we = _prog_dates(prog_pos, t['deg'], asp_angle, speed, solar_dt)
                results.append({
                    'prog': prog_name,
                    'prog_base': base_prog,
                    'target': t['name'],
                    'target_base': base_t,
                    'aspect': asp_name,
                    'aspect_symbol': ASPECT_SYMBOLS[asp_name],
                    'orb': round(orb, 3),
                    'exact_date': _ed, 'window_start': _ws, 'window_end': _we,
                })
                break
    return sorted(results, key=lambda x: x['orb'])


def _find_moon_crossing_date(natal_subject, start_age, end_age, target_deg):
    """
    Бинарный поиск даты когда прогрессивная Луна пересекает заданный градус.
    Возвращает дату в формате ISO или None если не найдено.
    """
    from kerykeion import AstrologicalSubjectFactory
    natal_dt = datetime(natal_subject.year, natal_subject.month, natal_subject.day,
                        natal_subject.hour, natal_subject.minute)

    def moon_at_age(age):
        d = natal_dt + timedelta(days=age)
        s = AstrologicalSubjectFactory.from_birth_data(
            'TmpProg', d.year, d.month, d.day, d.hour, d.minute,
            lng=natal_subject.lng, lat=natal_subject.lat,
            tz_str=natal_subject.tz_str, online=False
        )
        return s.moon.abs_pos

    # Бинарный поиск с шагом ~0.5 дня прогрессии (~15 дней реального времени)
    low, high = start_age, end_age
    target_deg = target_deg % 360
    for _ in range(30):
        mid = (low + high) / 2
        moon_pos = moon_at_age(mid)
        # Расстояние от Луны до целевого градуса
        diff = (target_deg - moon_pos) % 360
        if diff > 180:
            diff -= 360
        if abs(diff) < 0.05:
            # Найдено — конвертируем age в реальную дату
            # 1 день прогрессии = 1 год реального времени
            # Реальная дата = натальная дата + (mid - 0) лет
            natal_birth = datetime(natal_subject.year, natal_subject.month,
                                  natal_subject.day)
            real_date = natal_birth + timedelta(days=mid * 365.2422)
            return real_date.strftime('%Y-%m-%d')
        if diff > 0:
            low = mid
        else:
            high = mid
    return None


def _identify_lunar_phase(phase_deg):
    """Определяет фазу Луны по углу Луна-Солнце."""
    for start, end, name_ru, name_en, meaning in LUNAR_PHASES:
        if start <= phase_deg < end:
            return {
                'phase_deg': round(phase_deg, 2),
                'name_ru': name_ru,
                'name_en': name_en,
                'meaning_ru': meaning,
            }
    return None


def _collect_all_critical(progressed_data, key):
    """Собирает все аспекты из всех прогрессивных точек в один список."""
    all_aspects = []
    for planet_key, planet_data in progressed_data.items():
        if isinstance(planet_data, dict) and key in planet_data:
            all_aspects.extend(planet_data[key])
    return sorted(all_aspects, key=lambda x: x.get('orb', 99))


# ============================================================
# ФОРМАТТЕР ДЛЯ ПРОМПТА
# ============================================================

def format_progressions_for_prompt(data, lang='ru'):
    if lang == 'ru':
        return _format_ru(data)
    return _format_en(data)


def _format_ru(d):
    """Компактный вывод прогрессий — только цифры."""
    lines = []
    lines.append(f"[ПРОГРЕССИИ] возраст {d['age_years']:.2f} лет")

    pd = d['progressed_data']
    sun = pd.get('progressed_sun')
    if sun:
        lines.append(f"Прогр.Солнце: {sun['sign_ru']} {sun['deg_in_sign']:.2f}° (натал-{sun['natal_house']}, соляр-{sun['solar_house']})")

    moon = pd.get('progressed_moon')
    if moon:
        line = f"Прогр.Луна: {moon['sign_ru']} {moon['deg_in_sign']:.2f}° (натал-{moon['natal_house']}, соляр-{moon['solar_house']})"
        if 'pos_at_year_end' in moon:
            line += f" → конец года {moon['sign_ru_at_year_end']} {moon['pos_at_year_end'] % 30:.2f}° (натал-{moon['natal_house_at_year_end']}), движ {moon['movement_degrees']:.1f}°"
        lines.append(line)
        if 'sign_change_in_year' in moon:
            sc = moon['sign_change_in_year']
            date_str = sc.get('date', '?')
            lines.append(f"  ⚡ Смена знака в году: {sc['from']} → {sc['to']} ~{date_str}")
        if 'house_change_in_year' in moon:
            hc = moon['house_change_in_year']
            date_str = hc.get('date', '?')
            lines.append(f"  ⚡ Смена натал-дома в году: {hc['from']} → {hc['to']} ~{date_str}")

    for key, label in [('progressed_mercury', 'Прогр.Меркурий'),
                       ('progressed_venus', 'Прогр.Венера'),
                       ('progressed_mars', 'Прогр.Марс')]:
        p = pd.get(key)
        if p:
            lines.append(f"{label}: {p['sign_ru']} {p['deg_in_sign']:.2f}° (натал-{p['natal_house']})")

    pn = pd.get('progressed_north_node')
    ps = pd.get('progressed_south_node')
    if pn or ps:
        parts = []
        if pn:
            parts.append(f"прогр.СУ {pn['sign_ru']} {pn['deg_in_sign']:.2f}° (натал-{pn['natal_house']})")
        if ps:
            parts.append(f"прогр.ЮУ {ps['sign_ru']} {ps['deg_in_sign']:.2f}° (натал-{ps['natal_house']})")
        lines.append("Прогр.узлы: " + " | ".join(parts))

    # Все точные прогрессивные аспекты — сводно
    crit_natal = d.get('all_critical_to_natal', [])
    if crit_natal:
        lines.append("Прогр. аспекты к натальной (орбис ≤1° планеты / ≤1.5° Луна):")
        for a in crit_natal:
            lines.append(f"  {a['prog']} {a['aspect_symbol']} натал-{a['target_base']}, орбис {a['orb']:.3f}°" + _prog_date_suffix(a))

    crit_solar = d.get('all_critical_to_solar', [])
    if crit_solar:
        lines.append("Прогр. аспекты к солярной (орбис ≤1.5°):")
        for a in crit_solar:
            lines.append(f"  {a['prog']} {a['aspect_symbol']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°" + _prog_date_suffix(a))

    # Лунные фазы
    lar = d.get('lunar_age_of_solar')
    if lar:
        lines.append(f"Лунный возраст соляра: {lar['name_ru']} ({lar['phase_deg']:.2f}°) — {lar['meaning_ru']}")

    plp = d.get('progressive_lunar_phase')
    if plp:
        lines.append(f"Прогр.фаза Луна-Солнце (30-летний цикл): {plp['name_ru']} ({plp['phase_deg']:.2f}°) — {plp['meaning_ru']}")

    return '\n'.join(lines)


def _format_en(d):
    """Compact progressions output — numbers only."""
    lines = []
    lines.append(f"[PROGRESSIONS] age {d['age_years']:.2f} years")

    pd = d['progressed_data']
    sun = pd.get('progressed_sun')
    if sun:
        lines.append(f"Prog.Sun: {sun['sign_en']} {sun['deg_in_sign']:.2f}° (natal-{sun['natal_house']}, solar-{sun['solar_house']})")

    moon = pd.get('progressed_moon')
    if moon:
        line = f"Prog.Moon: {moon['sign_en']} {moon['deg_in_sign']:.2f}° (natal-{moon['natal_house']}, solar-{moon['solar_house']})"
        if 'pos_at_year_end' in moon:
            line += f" → year-end {moon['sign_en_at_year_end']} {moon['pos_at_year_end'] % 30:.2f}° (natal-{moon['natal_house_at_year_end']}), move {moon['movement_degrees']:.1f}°"
        lines.append(line)
        if 'sign_change_in_year' in moon:
            sc = moon['sign_change_in_year']
            date_str = sc.get('date', '?')
            lines.append(f"  ⚡ Sign change in year: {sc['from_en']} → {sc['to_en']} ~{date_str}")
        if 'house_change_in_year' in moon:
            hc = moon['house_change_in_year']
            date_str = hc.get('date', '?')
            lines.append(f"  ⚡ Natal house change in year: {hc['from']} → {hc['to']} ~{date_str}")

    for key, label in [('progressed_mercury', 'Prog.Mercury'),
                       ('progressed_venus', 'Prog.Venus'),
                       ('progressed_mars', 'Prog.Mars')]:
        p = pd.get(key)
        if p:
            lines.append(f"{label}: {p['sign_en']} {p['deg_in_sign']:.2f}° (natal-{p['natal_house']})")

    pn = pd.get('progressed_north_node')
    ps = pd.get('progressed_south_node')
    if pn or ps:
        parts = []
        if pn:
            parts.append(f"prog.NN {pn['sign_en']} {pn['deg_in_sign']:.2f}° (natal-{pn['natal_house']})")
        if ps:
            parts.append(f"prog.SN {ps['sign_en']} {ps['deg_in_sign']:.2f}° (natal-{ps['natal_house']})")
        lines.append("Prog.nodes: " + " | ".join(parts))

    crit_natal = d.get('all_critical_to_natal', [])
    if crit_natal:
        lines.append("Prog. aspects to natal (orb ≤1° planets / ≤1.5° Moon):")
        for a in crit_natal:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            sym = ASPECT_SYMBOLS_EN.get(asp_en, '')
            lines.append(f"  {a['prog']} {sym} natal-{a['target_base']}, orb {a['orb']:.3f}°")

    crit_solar = d.get('all_critical_to_solar', [])
    if crit_solar:
        lines.append("Prog. aspects to solar (orb ≤1.5°):")
        for a in crit_solar:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            sym = ASPECT_SYMBOLS_EN.get(asp_en, '')
            lines.append(f"  {a['prog']} {sym} solar-{a['target_base']}, orb {a['orb']:.3f}°")

    lar = d.get('lunar_age_of_solar')
    if lar:
        lines.append(f"Lunar age of solar: {lar['name_en']} ({lar['phase_deg']:.2f}°)")

    plp = d.get('progressive_lunar_phase')
    if plp:
        lines.append(f"Prog. Moon-Sun phase (30-yr cycle): {plp['name_en']} ({plp['phase_deg']:.2f}°)")

    return '\n'.join(lines)
