"""
solar_calculator.py — Сборщик фактов соляра по методике А.Волгина.

Использует astro_engine.py как ядро расчётов.
Возвращает структурированный словарь со всеми ключевыми фактами для интерпретации.
Сам НЕ интерпретирует — только собирает данные.

Методика: 7 уровней анализа из skills/solar/volguine_method.md
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from astro_engine import (
    angular_distance, deg_to_sign_pos, degree_to_house, normalize_deg,
    extract_planets, extract_extras, extract_angles, extract_cusps,
    find_aspect, all_aspects, find_angular_planets, find_planets_in_houses,
    find_stelliums, find_retrogrades,
    get_sign_ruler, find_house_ruler,
    chart_from_subject,
    SIGNS_RU, SIGN_ELEMENTS, SIGN_MODALITIES,
    PLANET_NAMES_RU, ORBIS_BY_POINT, get_aspect_orb,
)


def calculate_solar_return(natal_subject, solar_return_subject,
                            ruler_system='modern',
                            include_minor_aspects=False):
    """
    Главная функция: собирает все факты соляра по методике Волгина (7 уровней).

    Параметры:
        natal_subject: kerykeion subject натальной карты
        solar_return_subject: kerykeion subject солярной карты
        ruler_system: 'modern' (по умолчанию) или 'traditional'
        include_minor_aspects: включить минорные аспекты (default False)

    Возвращает: dict со всеми ключевыми фактами
    """
    # Извлекаем оба chart-dict
    natal = chart_from_subject(natal_subject)
    solar = chart_from_subject(solar_return_subject)

    result = {
        'natal_chart': natal,
        'solar_chart': solar,
        'meta': {
            'ruler_system': ruler_system,
            'include_minor_aspects': include_minor_aspects,
            'natal_houses_system': getattr(natal_subject, 'houses_system_name', 'Placidus'),
            'solar_houses_system': getattr(solar_return_subject, 'houses_system_name', 'Placidus'),
        },
    }

    # === УРОВЕНЬ 1: АСЦЕНДЕНТ СОЛЯРА — тон года ===
    result['level_1_solar_asc'] = _analyze_solar_asc(natal, solar, ruler_system)

    # === УРОВЕНЬ 2: MIDHEAVEN СОЛЯРА — направление года ===
    result['level_2_solar_mc'] = _analyze_solar_mc(natal, solar, ruler_system)

    # === УРОВЕНЬ 3: СОЛНЦЕ СОЛЯРА — главная сфера ===
    result['level_3_solar_sun'] = _analyze_solar_sun(natal, solar)

    # === УРОВЕНЬ 4: УГЛОВЫЕ ПЛАНЕТЫ СОЛЯРА ===
    result['level_4_angular_planets'] = _find_angular_planets_with_strength(
        solar['planets'], solar['angles']
    )

    # === УРОВЕНЬ 5: НАТАЛЬНЫЕ ПЛАНЕТЫ НА УГЛАХ СОЛЯРА (классика!) ===
    result['level_5_natal_on_solar_angles'] = _find_natal_planets_on_solar_angles(
        natal['planets'], solar['angles']
    )

    # === УРОВЕНЬ 6: АСПЕКТЫ СОЛЯР-ПЛАНЕТ К НАТАЛ-ПЛАНЕТАМ ===
    # Углы (МС, АСЦ) натала включаем в аспектацию — иначе трины/квадраты/секстили
    # соляр-планет к карьерной вершине (МС) и асценденту вообще не вычисляются,
    # хотя движок и орбисы для них готовы. IC/DSC не берём — это зеркала на 180°.
    _natal_angles = [a for a in natal.get('angles', []) if a['name'] in ('MC', 'ASC')]
    result['level_6_solar_to_natal_aspects'] = all_aspects(
        solar['planets'], natal['planets'] + _natal_angles, include_minor=include_minor_aspects
    )

    # === УРОВЕНЬ 7: ПЕРЕХОДЫ ПЛАНЕТ (натал → соляр) — главный синтез ===
    result['level_7_planet_transitions'] = _build_planet_transitions(natal, solar)

    # === ДОПОЛНИТЕЛЬНО ===
    result['stelliums_solar'] = find_stelliums(solar['planets'], min_count=3, by='sign')
    result['retrogrades_solar'] = find_retrogrades(solar['planets'])

    # Соляр-планеты в натальных домах (важно для синтеза)
    result['solar_planets_in_natal_houses'] = [
        {
            'planet': p['name'],
            'sign': p['sign'],
            'pos_in_sign': round(p['pos_in_sign'], 1),
            'natal_house': degree_to_house(p['deg'], natal['cusps']),
            'solar_house': degree_to_house(p['deg'], solar['cusps']),
            'retrograde': p.get('retrograde', False),
        }
        for p in solar['planets']
    ]

    # Соляр-Луна (отдельно — эмоциональный тон года)
    result['solar_moon'] = _analyze_solar_moon(natal, solar)

    return result


# ============================================================
# ВНУТРЕННИЕ ФУНКЦИИ
# ============================================================

def _get_planet_by_name(planets, name):
    """Найти планету в списке по имени."""
    return next((p for p in planets if p['name'] == name), None)


def _get_angle_by_name(angles, name):
    """Найти угол в списке по имени."""
    return next((a for a in angles if a['name'] == name), None)


def _analyze_solar_asc(natal, solar, ruler_system='modern'):
    """Уровень 1: соляр-ASC + управитель в обеих картах + сдвиг."""
    sr_asc = _get_angle_by_name(solar['angles'], 'ASC')
    nat_asc = _get_angle_by_name(natal['angles'], 'ASC')

    if not sr_asc or not nat_asc:
        return None

    sr_sign, sr_pos = deg_to_sign_pos(sr_asc['deg'])
    nat_sign, nat_pos = deg_to_sign_pos(nat_asc['deg'])

    # Натальный дом куда попадает соляр-ASC (показывает на какую сферу натальной жизни выходит фокус года)
    sr_asc_in_natal_house = degree_to_house(sr_asc['deg'], natal['cusps'])

    # Управитель знака соляр-ASC
    ruler_name = get_sign_ruler(sr_sign, ruler_system)

    # Где этот управитель стоит в соляре и в натале
    ruler_in_solar = _get_planet_by_name(solar['planets'], ruler_name)
    ruler_in_natal = _get_planet_by_name(natal['planets'], ruler_name)

    return {
        'solar_asc': {
            'sign': sr_sign,
            'pos_in_sign': round(sr_pos, 2),
            'deg': round(sr_asc['deg'], 2),
            'element': SIGN_ELEMENTS.get(sr_sign),
            'modality': SIGN_MODALITIES.get(sr_sign),
            'in_natal_house': sr_asc_in_natal_house,
        },
        'natal_asc': {
            'sign': nat_sign,
            'pos_in_sign': round(nat_pos, 2),
            'deg': round(nat_asc['deg'], 2),
            'element': SIGN_ELEMENTS.get(nat_sign),
            'modality': SIGN_MODALITIES.get(nat_sign),
        },
        'shift': {
            'is_same_sign': sr_sign == nat_sign,
            'angular_distance': round(angular_distance(sr_asc['deg'], nat_asc['deg']), 2),
        },
        'ruler': {
            'name': ruler_name,
            'in_solar': _planet_summary(ruler_in_solar, solar['cusps'], natal['cusps']),
            'in_natal': _planet_summary_simple(ruler_in_natal, natal['cusps']),
        },
    }


def _analyze_solar_mc(natal, solar, ruler_system='modern'):
    """Уровень 2: соляр-MC + управитель в обеих картах + сдвиг."""
    sr_mc = _get_angle_by_name(solar['angles'], 'MC')
    nat_mc = _get_angle_by_name(natal['angles'], 'MC')

    if not sr_mc or not nat_mc:
        return None

    sr_sign, sr_pos = deg_to_sign_pos(sr_mc['deg'])
    nat_sign, nat_pos = deg_to_sign_pos(nat_mc['deg'])

    sr_mc_in_natal_house = degree_to_house(sr_mc['deg'], natal['cusps'])

    ruler_name = get_sign_ruler(sr_sign, ruler_system)
    ruler_in_solar = _get_planet_by_name(solar['planets'], ruler_name)
    ruler_in_natal = _get_planet_by_name(natal['planets'], ruler_name)

    return {
        'solar_mc': {
            'sign': sr_sign,
            'pos_in_sign': round(sr_pos, 2),
            'deg': round(sr_mc['deg'], 2),
            'in_natal_house': sr_mc_in_natal_house,
        },
        'natal_mc': {
            'sign': nat_sign,
            'pos_in_sign': round(nat_pos, 2),
            'deg': round(nat_mc['deg'], 2),
        },
        'shift': {
            'is_same_sign': sr_sign == nat_sign,
            'angular_distance': round(angular_distance(sr_mc['deg'], nat_mc['deg']), 2),
        },
        'ruler': {
            'name': ruler_name,
            'in_solar': _planet_summary(ruler_in_solar, solar['cusps'], natal['cusps']),
            'in_natal': _planet_summary_simple(ruler_in_natal, natal['cusps']),
        },
    }


def _analyze_solar_sun(natal, solar):
    """Уровень 3: соляр-Солнце по дому в обеих картах."""
    sr_sun = _get_planet_by_name(solar['planets'], 'Солнце')
    if not sr_sun:
        return None

    return {
        'sign': sr_sun['sign'],
        'pos_in_sign': round(sr_sun['pos_in_sign'], 2),
        'deg': round(sr_sun['deg'], 2),
        'solar_house': degree_to_house(sr_sun['deg'], solar['cusps']),
        'natal_house': degree_to_house(sr_sun['deg'], natal['cusps']),
    }


def _analyze_solar_moon(natal, solar):
    """Соляр-Луна — эмоциональный тон года."""
    sr_moon = _get_planet_by_name(solar['planets'], 'Луна')
    if not sr_moon:
        return None

    return {
        'sign': sr_moon['sign'],
        'pos_in_sign': round(sr_moon['pos_in_sign'], 2),
        'solar_house': degree_to_house(sr_moon['deg'], solar['cusps']),
        'natal_house': degree_to_house(sr_moon['deg'], natal['cusps']),
        'retrograde': sr_moon.get('retrograde', False),
    }


def _find_angular_planets_with_strength(planets, angles, max_orb=8.0):
    """
    Уровень 4: угловые планеты соляра с указанием силы активации.
    Сила: <3° = "ОЧЕНЬ СИЛЬНО", <5° = "сильно", иначе "умеренно".
    """
    raw = find_angular_planets(planets, angles, max_orb=max_orb)
    result = []
    for r in raw:
        orb = r['orb']
        if orb < 3.0:
            strength = 'ОЧЕНЬ СИЛЬНО'
        elif orb < 5.0:
            strength = 'сильно'
        else:
            strength = 'умеренно'
        result.append({**r, 'strength': strength})
    return result


def _find_natal_planets_on_solar_angles(natal_planets, solar_angles, max_orb=5.0):
    """
    Уровень 5: НАТАЛЬНЫЕ планеты на углах СОЛЯРА.
    Это главная классическая техника: натальные темы выходят на передний план в этом году.

    Используется орбис из ORBIS_BY_POINT для каждой натальной планеты.
    """
    result = []
    for p in natal_planets:
        for ang in solar_angles:
            orb = angular_distance(p['deg'], ang['deg'])
            # Используем максимальный из (орбис планеты, базовый 5°) — но не больше max_orb
            planet_orb = min(ORBIS_BY_POINT.get(p['name'], 5.0), max_orb)
            if orb <= planet_orb:
                if orb < 2.0:
                    strength = 'ЦЕНТРАЛЬНАЯ КОНФИГУРАЦИЯ ГОДА'
                elif orb < 3.5:
                    strength = 'сильная'
                else:
                    strength = 'умеренная'
                result.append({
                    'natal_planet': p['name'],
                    'sign': p['sign'],
                    'pos_in_sign': round(p['pos_in_sign'], 2),
                    'solar_angle': ang['name'],
                    'orb': round(orb, 2),
                    'strength': strength,
                })
    return sorted(result, key=lambda x: x['orb'])


def _build_planet_transitions(natal, solar):
    """
    Уровень 7: Переходы каждой из 10 планет — пара (натал, соляр).
    Это главный приём синтеза.
    """
    PLANET_LIST = ['Солнце', 'Луна', 'Меркурий', 'Венера', 'Марс',
                   'Юпитер', 'Сатурн', 'Уран', 'Нептун', 'Плутон']
    result = []
    for name in PLANET_LIST:
        np = _get_planet_by_name(natal['planets'], name)
        sp = _get_planet_by_name(solar['planets'], name)
        if not np or not sp:
            continue
        result.append({
            'planet': name,
            'natal': {
                'sign': np['sign'],
                'pos_in_sign': round(np['pos_in_sign'], 2),
                'house': degree_to_house(np['deg'], natal['cusps']),
                'retrograde': np.get('retrograde', False),
            },
            'solar': {
                'sign': sp['sign'],
                'pos_in_sign': round(sp['pos_in_sign'], 2),
                'solar_house': degree_to_house(sp['deg'], solar['cusps']),
                'natal_house': degree_to_house(sp['deg'], natal['cusps']),
                'retrograde': sp.get('retrograde', False),
            },
            'sign_changed': np['sign'] != sp['sign'],
            'element_natal': SIGN_ELEMENTS.get(np['sign']),
            'element_solar': SIGN_ELEMENTS.get(sp['sign']),
            'element_changed': SIGN_ELEMENTS.get(np['sign']) != SIGN_ELEMENTS.get(sp['sign']),
        })
    return result


def _planet_summary(planet, solar_cusps, natal_cusps):
    """Краткая сводка планеты в обоих наборах домов."""
    if planet is None:
        return None
    return {
        'sign': planet['sign'],
        'pos_in_sign': round(planet['pos_in_sign'], 2),
        'solar_house': degree_to_house(planet['deg'], solar_cusps) if solar_cusps else None,
        'natal_house': degree_to_house(planet['deg'], natal_cusps) if natal_cusps else None,
        'retrograde': planet.get('retrograde', False),
    }


def _planet_summary_simple(planet, cusps):
    """Сводка планеты только с одним набором домов (для натала)."""
    if planet is None:
        return None
    return {
        'sign': planet['sign'],
        'pos_in_sign': round(planet['pos_in_sign'], 2),
        'house': degree_to_house(planet['deg'], cusps) if cusps else None,
        'retrograde': planet.get('retrograde', False),
    }
