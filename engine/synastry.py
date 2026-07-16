"""
synastry.py — Синастрия Квантариона

Два режима:
  1. Обычная синастрия — два натала на одном зодиаке
  2. Уран-синхрон — сдвиг карты клиента чтобы Ураны совпали

В обоих случаях: аспекты между картами + наложение по домам.
"""

from .natal import normalize_deg, deg_to_sign, SIGNS_RU, SIGNS_SYM

# Аспекты для синастрии
SYNASTRY_ASPECTS = {
    0: ('Соединение', '☌', 8.0),
    60: ('Секстиль', '⚹', 5.0),
    90: ('Квадрат', '□', 6.0),
    120: ('Трин', '△', 7.0),
    180: ('Оппозиция', '☍', 8.0),
}


def calculate_synastry(chart1: dict, chart2: dict) -> dict:
    """
    Обычная синастрия — два натала на одном зодиаке.

    Args:
        chart1: натальная карта первого (результат calculate_natal)
        chart2: натальная карта второго

    Returns:
        dict с полями:
        - aspects: аспекты между картами
        - planets_in_houses: планеты одного в домах другого
    """
    aspects = _cross_aspects(chart1['planets'], chart2['planets'])

    # Планеты chart2 в домах chart1
    p2_in_h1 = _planets_in_houses(
        chart2['planets'], chart1['cusps'], 'карта_2 → дома_1'
    )

    # Планеты chart1 в домах chart2
    p1_in_h2 = _planets_in_houses(
        chart1['planets'], chart2['cusps'], 'карта_1 → дома_2'
    )

    return {
        'aspects': aspects,
        'planets_in_houses_1': p2_in_h1,
        'planets_in_houses_2': p1_in_h2,
    }


def calculate_uran_sync(
    operator_chart: dict,
    client_chart: dict,
) -> dict:
    """
    Уран-синхрон: сдвигает карту клиента чтобы его Уран
    встал точно на Уран оператора.

    Все планеты клиента сдвигаются на одну и ту же дельту.
    Через точку совмещения Уранов читается весь код клиента.

    Args:
        operator_chart: карта оператора (постоянная матрица)
        client_chart: карта клиента

    Returns:
        dict с полями:
        - delta: угол сдвига
        - shifted_planets: сдвинутые позиции клиента
        - channels: контакты между сдвинутыми и оператором
        - uran_aspect_natural: натуральный аспект между Уранами
    """
    op_uran = operator_chart['planets'].get('Уран', {}).get('abs_degree', 0)
    cl_uran = client_chart['planets'].get('Уран', {}).get('abs_degree', 0)

    delta = cl_uran - op_uran

    # Натуральный аспект между Уранами (до сдвига)
    natural_diff = abs(cl_uran - op_uran)
    if natural_diff > 180:
        natural_diff = 360 - natural_diff
    natural_aspect = _identify_aspect(natural_diff)

    # Сдвигаем все планеты клиента
    shifted = {}
    for name, planet in client_chart['planets'].items():
        if 'abs_degree' not in planet:
            continue
        new_deg = normalize_deg(planet['abs_degree'] - delta)
        shifted[name] = {
            'name': name,
            'original': round(planet['abs_degree'], 4),
            'shifted': round(new_deg, 4),
            'shifted_sign': deg_to_sign(new_deg),
        }

    # Контакты: сдвинутые планеты клиента → планеты оператора
    channels = []
    for cl_name, cl_data in shifted.items():
        for op_name, op_planet in operator_chart['planets'].items():
            if 'abs_degree' not in op_planet:
                continue
            diff = abs(cl_data['shifted'] - op_planet['abs_degree'])
            if diff > 180:
                diff = 360 - diff
            if diff < 8:
                asp = _identify_aspect(diff)
                channels.append({
                    'client_planet': cl_name,
                    'client_shifted': cl_data['shifted_sign']['formatted'],
                    'operator_planet': op_name,
                    'operator_pos': deg_to_sign(
                        op_planet['abs_degree']
                    )['formatted'],
                    'orb': round(diff, 2),
                    'aspect': asp,
                    'description': (
                        f"{cl_name} клиента → {op_name} оператора"
                    ),
                })

    channels.sort(key=lambda c: c['orb'])

    return {
        'delta': round(delta, 4),
        'operator_uran': round(op_uran, 4),
        'client_uran': round(cl_uran, 4),
        'natural_aspect': natural_aspect,
        'shifted_planets': shifted,
        'channels': channels,
    }


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================


def _cross_aspects(planets1: dict, planets2: dict) -> list:
    """Находит аспекты между двумя наборами планет."""
    aspects = []

    for name1, p1 in planets1.items():
        if 'abs_degree' not in p1:
            continue
        for name2, p2 in planets2.items():
            if 'abs_degree' not in p2:
                continue

            diff = abs(p1['abs_degree'] - p2['abs_degree'])
            if diff > 180:
                diff = 360 - diff

            for asp_deg, (asp_name, asp_sym, max_orb) in SYNASTRY_ASPECTS.items():
                orb = abs(diff - asp_deg)
                if orb <= max_orb:
                    aspects.append({
                        'planet1': name1,
                        'planet2': name2,
                        'aspect': asp_name,
                        'symbol': asp_sym,
                        'degree': asp_deg,
                        'orb': round(orb, 2),
                        'exact': orb < 1.0,
                    })

    aspects.sort(key=lambda a: a['orb'])
    return aspects


def _planets_in_houses(planets: dict, cusps: list, label: str) -> list:
    """Определяет в какие дома попадают планеты."""
    from .natal import _find_house, _find_house_part

    result = []
    for name, p in planets.items():
        if 'abs_degree' not in p:
            continue
        house = _find_house(p['abs_degree'], cusps)
        part = _find_house_part(p['abs_degree'], cusps, house)
        result.append({
            'planet': name,
            'house': house,
            'house_part': part,
        })

    return result


def _identify_aspect(diff: float) -> str:
    """Определяет аспект по разнице градусов."""
    for asp_deg, (asp_name, asp_sym, max_orb) in SYNASTRY_ASPECTS.items():
        if abs(diff - asp_deg) <= max_orb:
            return f"{asp_name} ({asp_sym}) орб {abs(diff - asp_deg):.1f}°"
    return f"нет мажорного аспекта ({diff:.1f}°)"
