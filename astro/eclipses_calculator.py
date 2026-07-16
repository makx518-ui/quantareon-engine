"""
astro/eclipses_calculator.py — модуль расчёта затмений солярного года.

ЗАТМЕНИЯ — одни из самых мощных событий в астрологии. Они активируют
кармическую узловую ось и часто совпадают с важными событиями жизни.

Логика затмений:
- Затмения всегда происходят рядом с Лунными Узлами (max ~18° от узла)
- Солнечные затмения = новолуния на оси узлов
- Лунные затмения = полнолуния на оси узлов
- Серии затмений (Сарос) повторяются примерно раз в 18.6 лет

Затмения 2026 — попадают на ось Дева-Рыбы.

Для соляра считаем:
- Все солнечные и лунные затмения года
- Их позиции (знак, градус)
- Аспекты затмений к натальной карте (орбис ≤3°)
- Аспекты к солярной карте
- Натальные дома куда попадают затмения
- Особо подсвечиваются попадания на натальные узлы / светила / углы

Источники:
- NASA eclipse data (использовали для верификации)
- Bernadette Brady "The Eagle and the Lark" (затмения как кармические триггеры)
- Эллинистическая школа (затмения = переломы судьбы)
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

# Орбисы для аспектов затмений к натальной карте
ECLIPSE_ORBIS = 3.0  # широкий — затмения работают по широкому орбису

# Известные затмения 2026 года (по NASA Eclipse Catalog)
# Format: (date, type, sign_index, degree_in_sign, kind_full_or_partial)
# Точные данные из NASA - используются для тестов, реальный расчёт делается через эфемериду
KNOWN_ECLIPSES_2026 = [
    # Лунное затмение 3 марта 2026
    ('2026-03-03 11:34', 'lunar', 'partial'),
    # Солнечное затмение 17 февраля 2026 (кольцевое)
    ('2026-02-17 12:13', 'solar', 'annular'),
    # Лунное затмение 28 августа 2026
    ('2026-08-28 04:14', 'lunar', 'partial'),
    # Солнечное затмение 12 августа 2026 (полное)
    ('2026-08-12 17:46', 'solar', 'total'),
]


def calculate_eclipses(natal_subject, solar_subject, yearly_subjects=None):
    """
    Главная функция: считает затмения солярного года и их связь
    с натальной/солярной картами.

    Параметры:
        natal_subject: kerykeion AstrologicalSubject — натальная карта
        solar_subject: kerykeion AstrologicalSubject — солярная карта

    Возвращает dict со всеми затмениями года и их аспектами.
    """
    nc = chart_from_subject(natal_subject)
    sc = chart_from_subject(solar_subject)

    solar_year = solar_subject.year
    lat = solar_subject.lat
    lng = solar_subject.lng
    tz = solar_subject.tz_str

    # Сканируем эфемериду на новолуния и полнолуния года
    eclipses = _find_eclipses_in_year(solar_year, lat, lng, tz, natal_subject, yearly_subjects=yearly_subjects)

    # Собираем натальные таргеты для проверки аспектов
    natal_targets = _build_targets(natal_subject, nc, prefix='натал_')
    solar_targets = _build_targets(solar_subject, sc, prefix='соляр_')

    # Для каждого затмения находим аспекты к натальной и солярной карте
    enriched = []
    for ecl in eclipses:
        sun_pos = ecl['sun_pos']
        moon_pos = ecl['moon_pos']

        # Натал-дом куда попадает Солнце затмения (точка зачина)
        natal_house_sun = degree_to_house(sun_pos, nc['cusps'])
        natal_house_moon = degree_to_house(moon_pos, nc['cusps'])
        solar_house_sun = degree_to_house(sun_pos, sc['cusps'])
        solar_house_moon = degree_to_house(moon_pos, sc['cusps'])

        # Аспекты Солнца затмения к натальной карте
        aspects_to_natal = _find_eclipse_aspects(sun_pos, 'Солнце_затмения', natal_targets)
        # Аспекты Луны затмения к натальной карте
        aspects_moon_natal = _find_eclipse_aspects(moon_pos, 'Луна_затмения', natal_targets)
        # К солярной карте
        aspects_to_solar = _find_eclipse_aspects(sun_pos, 'Солнце_затмения', solar_targets)
        aspects_moon_solar = _find_eclipse_aspects(moon_pos, 'Луна_затмения', solar_targets)

        # Особо отметить попадание на натальные узлы / светила / углы
        critical_hits = _find_critical_hits(sun_pos, moon_pos, natal_targets)

        enriched.append({
            'date': ecl['date'],
            'type': ecl['type'],  # 'solar' / 'lunar'
            'sun_sign_ru': SIGNS_RU[int(sun_pos // 30)],
            'sun_sign_en': SIGNS_EN[int(sun_pos // 30)],
            'sun_deg_in_sign': round(sun_pos % 30, 2),
            'sun_abs_pos': round(sun_pos, 4),
            'moon_sign_ru': SIGNS_RU[int(moon_pos // 30)],
            'moon_sign_en': SIGNS_EN[int(moon_pos // 30)],
            'moon_deg_in_sign': round(moon_pos % 30, 2),
            'moon_abs_pos': round(moon_pos, 4),
            'natal_house_sun': natal_house_sun,
            'natal_house_moon': natal_house_moon,
            'solar_house_sun': solar_house_sun,
            'solar_house_moon': solar_house_moon,
            'aspects_to_natal_sun': aspects_to_natal,
            'aspects_to_natal_moon': aspects_moon_natal,
            'aspects_to_solar_sun': aspects_to_solar,
            'aspects_to_solar_moon': aspects_moon_solar,
            'critical_hits': critical_hits,
        })

    return {
        'year': solar_year,
        'total_eclipses': len(enriched),
        'eclipses': enriched,
    }


def _find_eclipses_in_year(year, lat, lng, tz, natal_subject, yearly_subjects=None):
    """
    Сканирует эфемериду года на новолуния и полнолуния вблизи узлов
    (это и есть затмения).

    Затмение происходит когда Солнце и Луна образуют 0° или 180° аспект
    И их позиция близка к узлам Луны (max ~18° от узла).
    """
    from kerykeion import EphemerisDataFactory

    eclipses = []

    if yearly_subjects is not None:
        subjects = yearly_subjects
    else:
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        try:
            factory = EphemerisDataFactory(
                start_datetime=start_date,
                end_datetime=end_date,
                step_type='days',
                step=1,
                lat=lat,
                lng=lng,
                tz_str=tz,
            )
            subjects = factory.get_ephemeris_data_as_astrological_subjects()
        except Exception:
            return eclipses

    # Идём по дням, ищем дни близкого новолуния/полнолуния И близости к узлу
    # Шаг 1 день может пропустить точное соединение — берём порог 8° для
    # ПЕРВИЧНОГО поиска, потом уточняем через локальный минимум.
    candidates_solar = []
    candidates_lunar = []

    prev_conj = None
    prev_opp = None
    for i, s in enumerate(subjects):
        try:
            sun = s.sun.abs_pos
            moon = s.moon.abs_pos
            nn = s.true_north_lunar_node.abs_pos
        except Exception:
            continue

        sun_moon_diff = (moon - sun) % 360
        conj_dist = min(sun_moon_diff, 360 - sun_moon_diff)
        opp_dist = abs(sun_moon_diff - 180)

        sun_to_nn = abs(angular_distance(sun, nn))
        sun_to_sn = abs(angular_distance(sun, (nn + 180) % 360))
        min_node_dist = min(sun_to_nn, sun_to_sn)

        # Локальный минимум conj_dist в этом дне — кандидат на новолуние
        if i > 0 and i < len(subjects) - 1:
            try:
                prev_sun = subjects[i-1].sun.abs_pos
                prev_moon = subjects[i-1].moon.abs_pos
                next_sun = subjects[i+1].sun.abs_pos
                next_moon = subjects[i+1].moon.abs_pos
                prev_diff = (prev_moon - prev_sun) % 360
                prev_conj = min(prev_diff, 360 - prev_diff)
                prev_opp = abs(prev_diff - 180)
                next_diff = (next_moon - next_sun) % 360
                next_conj = min(next_diff, 360 - next_diff)
                next_opp = abs(next_diff - 180)

                # Локальный минимум conj_dist + близко к узлу
                if conj_dist <= prev_conj and conj_dist <= next_conj and conj_dist <= 8.0:
                    if min_node_dist <= 18.0:
                        candidates_solar.append({
                            'idx': i, 'date': s.iso_formatted_local_datetime,
                            'sun_pos': sun, 'moon_pos': moon,
                            'node_dist': min_node_dist,
                            'aspect_dist': conj_dist,
                        })

                # Локальный минимум opp_dist + близко к узлу
                if opp_dist <= prev_opp and opp_dist <= next_opp and opp_dist <= 8.0:
                    if min_node_dist <= 18.0:
                        candidates_lunar.append({
                            'idx': i, 'date': s.iso_formatted_local_datetime,
                            'sun_pos': sun, 'moon_pos': moon,
                            'node_dist': min_node_dist,
                            'aspect_dist': opp_dist,
                        })
            except Exception:
                continue

    # Уточняем каждое затмение почасовым шагом ±2 дня от даты-кандидата
    eclipses = []
    for cand in candidates_solar:
        refined = _refine_eclipse_moment(cand, 'solar', lat, lng, tz)
        if refined:
            eclipses.append(refined)
    for cand in candidates_lunar:
        refined = _refine_eclipse_moment(cand, 'lunar', lat, lng, tz)
        if refined:
            eclipses.append(refined)

    return sorted(eclipses, key=lambda x: x['date'])


def _refine_eclipse_moment(candidate, eclipse_type, lat, lng, tz):
    """
    Уточняет точный момент затмения почасовым проходом ±2 дня от
    даты-кандидата. Возвращает запись о затмении с точными позициями
    Солнца и Луны в момент пика.
    """
    from kerykeion import EphemerisDataFactory
    cand_date = datetime.fromisoformat(
        candidate['date'].replace('Z', '+00:00').split('+')[0]
    )
    start = cand_date - timedelta(days=2)
    end = cand_date + timedelta(days=2)
    try:
        factory = EphemerisDataFactory(
            start_datetime=start,
            end_datetime=end,
            step_type='hours',
            step=1,
            lat=lat,
            lng=lng,
            tz_str=tz,
        )
        subjects = factory.get_ephemeris_data_as_astrological_subjects()
    except Exception:
        return None

    best = None
    for s in subjects:
        try:
            sun = s.sun.abs_pos
            moon = s.moon.abs_pos
            nn = s.true_north_lunar_node.abs_pos
        except Exception:
            continue
        sun_moon_diff = (moon - sun) % 360
        if eclipse_type == 'solar':
            asp_dist = min(sun_moon_diff, 360 - sun_moon_diff)
        else:
            asp_dist = abs(sun_moon_diff - 180)
        # Близость к узлу
        sun_to_nn = abs(angular_distance(sun, nn))
        sun_to_sn = abs(angular_distance(sun, (nn + 180) % 360))
        node_dist = min(sun_to_nn, sun_to_sn)

        if best is None or asp_dist < best['aspect_dist']:
            best = {
                'date': s.iso_formatted_local_datetime,
                'type': eclipse_type,
                'sun_pos': sun,
                'moon_pos': moon,
                'aspect_dist': asp_dist,
                'node_dist': node_dist,
            }
    # Окончательная проверка — если точная позиция Солнца близка к узлу
    # (≤18°), это настоящее затмение
    if best and best['node_dist'] <= 18.0 and best['aspect_dist'] <= 1.0:
        return best
    return None


def _build_targets(subject, chart, prefix=''):
    """Собирает таргеты натальной/солярной карты для проверки аспектов."""
    targets = []
    for p in chart['planets']:
        targets.append({'name': f"{prefix}{p['name']}", 'deg': p['deg']})
    for a in chart['angles']:
        targets.append({'name': f"{prefix}{a['name']}", 'deg': a['deg']})
    try:
        targets.append({
            'name': f"{prefix}Сев.Узел",
            'deg': subject.true_north_lunar_node.abs_pos
        })
        targets.append({
            'name': f"{prefix}Юж.Узел",
            'deg': subject.true_south_lunar_node.abs_pos
        })
    except Exception:
        pass
    return targets


def _find_eclipse_aspects(eclipse_pos, eclipse_name, targets):
    """Находит аспекты затмения к таргетам с орбисом ≤3°."""
    results = []
    for t in targets:
        base_t = t['name'].replace('натал_', '').replace('соляр_', '')
        dist = angular_distance(eclipse_pos, t['deg'])
        for asp_name, asp_angle in MAJOR_ASPECTS:
            orb = abs(dist - asp_angle)
            if orb <= ECLIPSE_ORBIS:
                results.append({
                    'eclipse_point': eclipse_name,
                    'target': t['name'],
                    'target_base': base_t,
                    'aspect': asp_name,
                    'orb': round(orb, 3),
                })
                break
    return sorted(results, key=lambda x: x['orb'])


def _find_critical_hits(sun_pos, moon_pos, natal_targets):
    """
    Особые попадания затмения — на узлы, светила, углы.
    Орбис строгий: ≤2°.
    """
    CRITICAL_ORBIS = 2.0
    CRITICAL_TARGETS = ['Солнце', 'Луна', 'ASC', 'MC', 'IC', 'DSC',
                        'Сев.Узел', 'Юж.Узел']

    hits = []
    for point_name, pos in [('Солнце_затмения', sun_pos), ('Луна_затмения', moon_pos)]:
        for t in natal_targets:
            base_t = t['name'].replace('натал_', '')
            if base_t not in CRITICAL_TARGETS:
                continue
            dist = angular_distance(pos, t['deg'])
            for asp_name, asp_angle in MAJOR_ASPECTS:
                orb = abs(dist - asp_angle)
                if orb <= CRITICAL_ORBIS:
                    hits.append({
                        'eclipse_point': point_name,
                        'natal_target': base_t,
                        'aspect': asp_name,
                        'orb': round(orb, 3),
                    })
                    break
    return sorted(hits, key=lambda x: x['orb'])


# ============================================================
# ФОРМАТТЕР ДЛЯ ПРОМПТА
# ============================================================

def format_eclipses_for_prompt(data, lang='ru'):
    """Форматирует затмения для подачи в LLM-промпт."""
    if lang == 'ru':
        return _format_ru(data)
    return _format_en(data)


def _format_ru(d):
    """Компактный вывод затмений — только цифры."""
    lines = []
    lines.append(f"[ЗАТМЕНИЯ {d['year']}] всего {d['total_eclipses']}")
    if not d['eclipses']:
        return '\n'.join(lines)

    for ecl in d['eclipses']:
        type_ru = 'СОЛН' if ecl['type'] == 'solar' else 'ЛУНН'
        # Дата без таймзоны
        date_short = ecl['date'].split('T')[0] if 'T' in ecl['date'] else ecl['date']
        lines.append(f"{type_ru} {date_short}: ☀ {ecl['sun_sign_ru']} {ecl['sun_deg_in_sign']:.2f}° (натал-{ecl['natal_house_sun']}, соляр-{ecl['solar_house_sun']}) | 🌙 {ecl['moon_sign_ru']} {ecl['moon_deg_in_sign']:.2f}° (натал-{ecl['natal_house_moon']}, соляр-{ecl['solar_house_moon']})")

        if ecl['critical_hits']:
            for h in ecl['critical_hits']:
                lines.append(f"  🔥 {h['eclipse_point']} {h['aspect']} натал-{h['natal_target']}, орбис {h['orb']:.3f}°")
        # Все важные аспекты Солнца к натальной (макс 5)
        for a in ecl['aspects_to_natal_sun'][:5]:
            lines.append(f"  ☀_затм {a['aspect']} натал-{a['target_base']}, орбис {a['orb']:.3f}°")
        # Аспекты Луны (макс 5)
        for a in ecl['aspects_to_natal_moon'][:5]:
            lines.append(f"  🌙_затм {a['aspect']} натал-{a['target_base']}, орбис {a['orb']:.3f}°")
        # Аспекты к солярной (макс 3)
        for a in ecl['aspects_to_solar_sun'][:3]:
            lines.append(f"  ☀_затм {a['aspect']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°")

    return '\n'.join(lines)


def _format_en(d):
    """Compact eclipses output — numbers only."""
    lines = []
    lines.append(f"[ECLIPSES {d['year']}] total {d['total_eclipses']}")
    if not d['eclipses']:
        return '\n'.join(lines)

    for ecl in d['eclipses']:
        type_en = 'SOL' if ecl['type'] == 'solar' else 'LUN'
        date_short = ecl['date'].split('T')[0] if 'T' in ecl['date'] else ecl['date']
        lines.append(f"{type_en} {date_short}: ☀ {ecl['sun_sign_en']} {ecl['sun_deg_in_sign']:.2f}° (natal-{ecl['natal_house_sun']}, solar-{ecl['solar_house_sun']}) | 🌙 {ecl['moon_sign_en']} {ecl['moon_deg_in_sign']:.2f}° (natal-{ecl['natal_house_moon']}, solar-{ecl['solar_house_moon']})")

        if ecl['critical_hits']:
            for h in ecl['critical_hits']:
                lines.append(f"  🔥 {h['eclipse_point']} {h['aspect']} natal-{h['natal_target']}, orb {h['orb']:.3f}°")
        for a in ecl['aspects_to_natal_sun'][:5]:
            lines.append(f"  ☀_ecl {a['aspect']} natal-{a['target_base']}, orb {a['orb']:.3f}°")
        for a in ecl['aspects_to_natal_moon'][:5]:
            lines.append(f"  🌙_ecl {a['aspect']} natal-{a['target_base']}, orb {a['orb']:.3f}°")
        for a in ecl['aspects_to_solar_sun'][:3]:
            lines.append(f"  ☀_ecl {a['aspect']} solar-{a['target_base']}, orb {a['orb']:.3f}°")

    return '\n'.join(lines)
