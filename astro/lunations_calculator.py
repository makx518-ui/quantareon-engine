"""
astro/lunations_calculator.py — модуль расчёта значимых лунаций года.

ЛУНАЦИИ — новолуния и полнолуния, которые НЕ являются затмениями
(находятся далеко от Лунных Узлов, поэтому без затмения).

За солярный год происходит ~12-13 новолуний и ~12-13 полнолуний.
Большинство из них астрологически малозначимы, НО когда лунация попадает
на натальную точку (планету, угол, узел) — она становится МЕСЯЧНЫМ ТРИГГЕРОМ
этой натальной темы.

Логика фильтрации:
- Считаем ВСЕ лунации года (~26 событий)
- Оставляем для промпта ТОЛЬКО те где есть аспект ≤2° к натальной точке
- Это даёт ~5-8 значимых лунаций года вместо 26

Орбисы:
- Аспект к натальной/солярной точке: ≤2°
- Критическое попадание (соединение/оппозиция к светилам/углам/узлам): ≤1°

Источники методики:
- Современная астрология (Liz Greene, Donna Cunningham)
- Эллинистическая школа (новолуния как ежемесячные посевы)
- Русская школа (Левин, Лосева)
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
LUNATION_ASPECT_ORBIS = 2.0  # для попадания в список значимых
LUNATION_CRITICAL_ORBIS = 1.0  # для подсветки критических попаданий

# Лунный возраст должен быть БОЛЬШЕ 18° от узла — иначе это затмение
# (затмения уже обрабатываются eclipses_calculator)
MIN_NODE_DIST_FOR_LUNATION = 18.0

# Критические таргеты (на которые попадание особенно важно)
CRITICAL_TARGETS = ['Солнце', 'Луна', 'ASC', 'MC', 'IC', 'DSC',
                    'Сев.Узел', 'Юж.Узел']


def calculate_lunations(natal_subject, solar_subject, yearly_subjects=None):
    """
    Главная функция: считает значимые лунации солярного года.

    Параметры:
        natal_subject: kerykeion AstrologicalSubject — натальная карта
        solar_subject: kerykeion AstrologicalSubject — солярная карта

    Возвращает dict с лунациями, попавшими на натальные точки.
    """
    nc = chart_from_subject(natal_subject)
    sc = chart_from_subject(solar_subject)

    solar_year = solar_subject.year
    lat = solar_subject.lat
    lng = solar_subject.lng
    tz = solar_subject.tz_str

    # Находим все лунации года (новолуния + полнолуния, не затмения)
    all_lunations = _find_all_lunations(solar_year, lat, lng, tz, yearly_subjects=yearly_subjects)

    # Натальные и солярные таргеты для проверки аспектов
    natal_targets = _build_targets(natal_subject, nc, prefix='натал_')
    solar_targets = _build_targets(solar_subject, sc, prefix='соляр_')

    # Обогащаем каждую лунацию аспектами
    enriched = []
    for lun in all_lunations:
        sun_pos = lun['sun_pos']
        moon_pos = lun['moon_pos']

        # Натал-дом куда попадают
        natal_house_sun = degree_to_house(sun_pos, nc['cusps'])
        natal_house_moon = degree_to_house(moon_pos, nc['cusps'])

        # Аспекты к натальной карте (строгий орбис)
        aspects_sun_natal = _find_aspects(sun_pos, natal_targets,
                                           LUNATION_ASPECT_ORBIS)
        aspects_moon_natal = _find_aspects(moon_pos, natal_targets,
                                            LUNATION_ASPECT_ORBIS)

        # Критические попадания (≤1°) на важные точки
        critical_hits = _find_critical_hits(sun_pos, moon_pos, natal_targets)

        # ФИЛЬТР ЗНАЧИМОСТИ: оставляем только лунации с попаданиями
        if not (aspects_sun_natal or aspects_moon_natal or critical_hits):
            continue

        enriched.append({
            'date': lun['date'],
            'type': lun['type'],  # 'new_moon' / 'full_moon'
            'sun_pos': sun_pos,
            'moon_pos': moon_pos,
            'sun_sign_ru': SIGNS_RU[int(sun_pos // 30)],
            'sun_sign_en': SIGNS_EN[int(sun_pos // 30)],
            'sun_deg_in_sign': round(sun_pos % 30, 2),
            'moon_sign_ru': SIGNS_RU[int(moon_pos // 30)],
            'moon_sign_en': SIGNS_EN[int(moon_pos // 30)],
            'moon_deg_in_sign': round(moon_pos % 30, 2),
            'natal_house_sun': natal_house_sun,
            'natal_house_moon': natal_house_moon,
            'aspects_to_natal_sun': aspects_sun_natal,
            'aspects_to_natal_moon': aspects_moon_natal,
            'critical_hits': critical_hits,
        })

    return {
        'year': solar_year,
        'total_lunations_in_year': len(all_lunations),
        'significant_lunations': len(enriched),
        'lunations': enriched,
    }


def _find_all_lunations(year, lat, lng, tz, yearly_subjects=None):
    """
    Находит все новолуния и полнолуния года, которые НЕ являются затмениями
    (расстояние от узла > 18°).
    """
    from kerykeion import EphemerisDataFactory

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
            return []

    # Ищем локальные минимумы conj_dist (новолуния) и opp_dist (полнолуния)
    candidates_new = []
    candidates_full = []

    for i in range(1, len(subjects) - 1):
        try:
            curr = subjects[i]
            prev = subjects[i-1]
            nxt = subjects[i+1]
            sun = curr.sun.abs_pos
            moon = curr.moon.abs_pos
            nn = curr.true_north_lunar_node.abs_pos
        except Exception:
            continue

        # Текущие расстояния Луна-Солнце
        sun_moon = (moon - sun) % 360
        conj = min(sun_moon, 360 - sun_moon)
        opp = abs(sun_moon - 180)

        # Предыдущие
        try:
            psm = (prev.moon.abs_pos - prev.sun.abs_pos) % 360
            prev_conj = min(psm, 360 - psm)
            prev_opp = abs(psm - 180)
            nsm = (nxt.moon.abs_pos - nxt.sun.abs_pos) % 360
            next_conj = min(nsm, 360 - nsm)
            next_opp = abs(nsm - 180)
        except Exception:
            continue

        # Близость к узлу — это ОТДЕЛЕНИЕ затмений от лунаций
        sun_to_nn = abs(angular_distance(sun, nn))
        sun_to_sn = abs(angular_distance(sun, (nn + 180) % 360))
        min_node_dist = min(sun_to_nn, sun_to_sn)

        # Лунация — это НЕ затмение, значит дистанция от узла > 18°
        if min_node_dist <= MIN_NODE_DIST_FOR_LUNATION:
            continue

        # Локальный минимум conj_dist — кандидат на новолуние
        if conj <= prev_conj and conj <= next_conj and conj <= 8.0:
            candidates_new.append({
                'idx': i, 'date': curr.iso_formatted_local_datetime,
                'sun_pos': sun, 'moon_pos': moon,
                'aspect_dist': conj,
            })
        # Локальный минимум opp_dist — кандидат на полнолуние
        if opp <= prev_opp and opp <= next_opp and opp <= 8.0:
            candidates_full.append({
                'idx': i, 'date': curr.iso_formatted_local_datetime,
                'sun_pos': sun, 'moon_pos': moon,
                'aspect_dist': opp,
            })

    # Уточняем каждое событие почасовым шагом ±2 дня
    lunations = []
    for cand in candidates_new:
        refined = _refine_lunation(cand, 'new_moon', lat, lng, tz)
        if refined:
            lunations.append(refined)
    for cand in candidates_full:
        refined = _refine_lunation(cand, 'full_moon', lat, lng, tz)
        if refined:
            lunations.append(refined)

    return sorted(lunations, key=lambda x: x['date'])


def _refine_lunation(candidate, lunation_type, lat, lng, tz):
    """Уточняет точный момент лунации почасовым шагом ±2 дня."""
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
            step=2,  # 2 часа достаточно — Луна за 2 часа проходит ~1°
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
        sun_moon = (moon - sun) % 360
        if lunation_type == 'new_moon':
            dist = min(sun_moon, 360 - sun_moon)
        else:
            dist = abs(sun_moon - 180)
        # Проверка что не затмение
        sun_to_nn = abs(angular_distance(sun, nn))
        sun_to_sn = abs(angular_distance(sun, (nn + 180) % 360))
        node_dist = min(sun_to_nn, sun_to_sn)

        if best is None or dist < best['aspect_dist']:
            best = {
                'date': s.iso_formatted_local_datetime,
                'type': lunation_type,
                'sun_pos': sun,
                'moon_pos': moon,
                'aspect_dist': dist,
                'node_dist': node_dist,
            }

    # Финальная проверка
    if best and best['aspect_dist'] <= 1.0 and best['node_dist'] > MIN_NODE_DIST_FOR_LUNATION:
        return best
    return None


def _build_targets(subject, chart, prefix=''):
    """Натальные/солярные точки для проверки аспектов."""
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


def _find_aspects(point_pos, targets, orbis):
    """Аспекты с заданным орбисом."""
    results = []
    for t in targets:
        base_t = t['name'].replace('натал_', '').replace('соляр_', '')
        dist = angular_distance(point_pos, t['deg'])
        for asp_name, asp_angle in MAJOR_ASPECTS:
            orb = abs(dist - asp_angle)
            if orb <= orbis:
                results.append({
                    'target': t['name'],
                    'target_base': base_t,
                    'aspect': asp_name,
                    'orb': round(orb, 3),
                })
                break
    return sorted(results, key=lambda x: x['orb'])


def _find_critical_hits(sun_pos, moon_pos, natal_targets):
    """Критические попадания на светила/углы/узлы (орбис ≤1°)."""
    hits = []
    for point_name, pos in [('Солнце_лунации', sun_pos), ('Луна_лунации', moon_pos)]:
        for t in natal_targets:
            base_t = t['name'].replace('натал_', '')
            if base_t not in CRITICAL_TARGETS:
                continue
            dist = angular_distance(pos, t['deg'])
            for asp_name, asp_angle in MAJOR_ASPECTS:
                orb = abs(dist - asp_angle)
                if orb <= LUNATION_CRITICAL_ORBIS:
                    hits.append({
                        'lunation_point': point_name,
                        'natal_target': base_t,
                        'aspect': asp_name,
                        'orb': round(orb, 3),
                    })
                    break
    return sorted(hits, key=lambda x: x['orb'])


# ============================================================
# ФОРМАТТЕР ДЛЯ ПРОМПТА
# ============================================================

def format_lunations_for_prompt(data, lang='ru'):
    """Форматирует лунации для подачи в LLM-промпт."""
    if lang == 'ru':
        return _format_ru(data)
    return _format_en(data)


def _format_ru(d):
    """Компактный вывод лунаций — только цифры, акцент на критические."""
    lines = []
    lines.append(f"[ЛУНАЦИИ {d['year']}] всего {d['total_lunations_in_year']}, значимых {d['significant_lunations']}")
    if not d['lunations']:
        return '\n'.join(lines)

    for lun in d['lunations']:
        type_ru = 'НЛ' if lun['type'] == 'new_moon' else 'ПЛ'
        date_short = lun['date'].split('T')[0] if 'T' in lun['date'] else lun['date']
        if lun['type'] == 'full_moon':
            head = f"{type_ru} {date_short}: ☀ {lun['sun_sign_ru']} {lun['sun_deg_in_sign']:.2f}° (натал-{lun['natal_house_sun']}) | 🌙 {lun['moon_sign_ru']} {lun['moon_deg_in_sign']:.2f}° (натал-{lun['natal_house_moon']})"
        else:
            head = f"{type_ru} {date_short}: ☀ {lun['sun_sign_ru']} {lun['sun_deg_in_sign']:.2f}° (натал-{lun['natal_house_sun']})"
        lines.append(head)

        if lun['critical_hits']:
            for h in lun['critical_hits']:
                lines.append(f"  🔥 {h['lunation_point']} {h['aspect']} натал-{h['natal_target']}, орбис {h['orb']:.3f}°")
        for a in lun['aspects_to_natal_sun'][:3]:
            lines.append(f"  ☀_лун {a['aspect']} натал-{a['target_base']}, орбис {a['orb']:.3f}°")
        if lun['type'] == 'full_moon':
            for a in lun['aspects_to_natal_moon'][:3]:
                lines.append(f"  🌙_лун {a['aspect']} натал-{a['target_base']}, орбис {a['orb']:.3f}°")

    return '\n'.join(lines)


def _format_en(d):
    """Compact lunations output — numbers only."""
    lines = []
    lines.append(f"[LUNATIONS {d['year']}] total {d['total_lunations_in_year']}, significant {d['significant_lunations']}")
    if not d['lunations']:
        return '\n'.join(lines)

    for lun in d['lunations']:
        type_en = 'NM' if lun['type'] == 'new_moon' else 'FM'
        date_short = lun['date'].split('T')[0] if 'T' in lun['date'] else lun['date']
        if lun['type'] == 'full_moon':
            head = f"{type_en} {date_short}: ☀ {lun['sun_sign_en']} {lun['sun_deg_in_sign']:.2f}° (natal-{lun['natal_house_sun']}) | 🌙 {lun['moon_sign_en']} {lun['moon_deg_in_sign']:.2f}° (natal-{lun['natal_house_moon']})"
        else:
            head = f"{type_en} {date_short}: ☀ {lun['sun_sign_en']} {lun['sun_deg_in_sign']:.2f}° (natal-{lun['natal_house_sun']})"
        lines.append(head)

        if lun['critical_hits']:
            for h in lun['critical_hits']:
                lines.append(f"  🔥 {h['lunation_point']} {h['aspect']} natal-{h['natal_target']}, orb {h['orb']:.3f}°")
        for a in lun['aspects_to_natal_sun'][:3]:
            lines.append(f"  ☀_lun {a['aspect']} natal-{a['target_base']}, orb {a['orb']:.3f}°")
        if lun['type'] == 'full_moon':
            for a in lun['aspects_to_natal_moon'][:3]:
                lines.append(f"  🌙_lun {a['aspect']} natal-{a['target_base']}, orb {a['orb']:.3f}°")

    return '\n'.join(lines)
