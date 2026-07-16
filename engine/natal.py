"""
natal.py — Расчёт натальной карты через Swiss Ephemeris

Чистая математика: планеты, дома, куспиды, аспекты, управители.
Никакой интерпретации.
"""

import swisseph as swe
from typing import Optional
from pathlib import Path

# Путь к дополнительным эфемеридам (Хирон и др.)
_EPHE_PATHS = [
    '/usr/local/share/swisseph',
    '/usr/share/swisseph',
    str(Path(__file__).parent.parent / 'data' / 'ephe'),
]
for _p in _EPHE_PATHS:
    if Path(_p).exists():
        swe.set_ephe_path(_p)
        break

# ============================================================
# КОНСТАНТЫ
# ============================================================

SIGNS_RU = [
    'Овен', 'Телец', 'Близнецы', 'Рак',
    'Лев', 'Дева', 'Весы', 'Скорпион',
    'Стрелец', 'Козерог', 'Водолей', 'Рыбы',
]

SIGNS_SYM = [
    '♈', '♉', '♊', '♋', '♌', '♍',
    '♎', '♏', '♐', '♑', '♒', '♓',
]

ELEMENTS = {
    0: 'Огонь', 1: 'Земля', 2: 'Воздух', 3: 'Вода',
    4: 'Огонь', 5: 'Земля', 6: 'Воздух', 7: 'Вода',
    8: 'Огонь', 9: 'Земля', 10: 'Воздух', 11: 'Вода',
}

MODALITIES = {
    0: 'Кардинальный', 1: 'Фиксированный', 2: 'Мутабельный',
    3: 'Кардинальный', 4: 'Фиксированный', 5: 'Мутабельный',
    6: 'Кардинальный', 7: 'Фиксированный', 8: 'Мутабельный',
    9: 'Кардинальный', 10: 'Фиксированный', 11: 'Мутабельный',
}

# Управители знаков (современные)
RULERS_MODERN = {
    0: 'Марс', 1: 'Венера', 2: 'Меркурий', 3: 'Луна',
    4: 'Солнце', 5: 'Меркурий', 6: 'Венера', 7: 'Плутон',
    8: 'Юпитер', 9: 'Сатурн', 10: 'Уран', 11: 'Нептун',
}

# Управители знаков (традиционные)
RULERS_TRADITIONAL = {
    0: 'Марс', 1: 'Венера', 2: 'Меркурий', 3: 'Луна',
    4: 'Солнце', 5: 'Меркурий', 6: 'Венера', 7: 'Марс',
    8: 'Юпитер', 9: 'Сатурн', 10: 'Сатурн', 11: 'Юпитер',
}

# Планеты для расчёта
PLANETS = [
    (swe.SUN, 'Солнце', '☉'),
    (swe.MOON, 'Луна', '☽'),
    (swe.MERCURY, 'Меркурий', '☿'),
    (swe.VENUS, 'Венера', '♀'),
    (swe.MARS, 'Марс', '♂'),
    (swe.JUPITER, 'Юпитер', '♃'),
    (swe.SATURN, 'Сатурн', '♄'),
    (swe.URANUS, 'Уран', '♅'),
    (swe.NEPTUNE, 'Нептун', '♆'),
    (swe.PLUTO, 'Плутон', '♇'),
    (swe.TRUE_NODE, 'Сев.Узел', '☊'),
    (swe.MEAN_APOG, 'Лилит', '⚸'),
    (swe.CHIRON, 'Хирон', '⚷'),
]

# Аспекты
ASPECTS = {
    0: ('Соединение', '☌'),
    60: ('Секстиль', '⚹'),
    90: ('Квадрат', '□'),
    120: ('Трин', '△'),
    180: ('Оппозиция', '☍'),
}

# Орбисы (стандартные)
ORBS = {
    0: 8.0,
    60: 6.0,
    90: 7.0,
    120: 8.0,
    180: 8.0,
}


# ============================================================
# УТИЛИТЫ
# ============================================================


def to_julian_day(year: int, month: int, day: int,
                  hour: int = 0, minute: int = 0, second: float = 0,
                  timezone: float = 0) -> float:
    """
    Переводит дату/время в Julian Day.

    Args:
        timezone: смещение от UTC (например, +6 для GMT+6)
    """
    utc_hour = hour + minute / 60.0 + second / 3600.0 - timezone
    return swe.julday(year, month, day, utc_hour)


def normalize_deg(deg: float) -> float:
    """Нормализация градуса к 0-360."""
    return deg % 360.0


def deg_to_sign(deg: float) -> dict:
    """Абсолютный градус → знак + позиция в знаке."""
    deg = normalize_deg(deg)
    sign_index = int(deg // 30)
    if sign_index >= 12:
        sign_index = 11
    pos = deg % 30
    d = int(pos)
    m = int((pos - d) * 60)
    s = ((pos - d) * 60 - m) * 60
    return {
        'abs_degree': round(deg, 6),
        'sign_index': sign_index,
        'sign_name': SIGNS_RU[sign_index],
        'sign_symbol': SIGNS_SYM[sign_index],
        'element': ELEMENTS[sign_index],
        'modality': MODALITIES[sign_index],
        'degree': d,
        'minute': m,
        'second': round(s, 2),
        'sabian': d + 1,
        'formatted': f"{d}°{m:02d}'{s:04.1f}\" {SIGNS_RU[sign_index]}",
    }


# ============================================================
# РАСЧЁТ НАТАЛЬНОЙ КАРТЫ
# ============================================================


def calculate_natal(year: int, month: int, day: int,
                    hour: int, minute: int, second: float = 0,
                    timezone: float = 0,
                    latitude: float = 0, longitude: float = 0,
                    house_system: str = 'P') -> dict:
    """
    Полный расчёт натальной карты.

    Args:
        year, month, day: дата рождения
        hour, minute, second: время рождения (местное)
        timezone: часовой пояс (GMT+X)
        latitude, longitude: координаты места
        house_system: система домов ('P'=Placidus, 'K'=Koch, и т.д.)

    Returns:
        dict с полями:
        - jd: Julian Day
        - planets: dict планет с позициями
        - cusps: list из 12 куспидов
        - angles: ASC, MC, DSC, IC
        - houses: dict домов с управителями
        - aspects: list аспектов
        - is_day_chart: дневная или ночная карта
    """
    # Julian Day
    jd = to_julian_day(year, month, day, hour, minute, second, timezone)

    # Куспиды домов.
    # ЗА ПОЛЯРНЫМ КРУГОМ (|широта| > 66.5) Плацидус и Кох НЕ СУЩЕСТВУЮТ:
    # часть градусов зодиака там вообще не всходит, делить нечего.
    # Швейцарская эфемерида честно падает. Переходим на Региомонтан —
    # из считающих там систем он ближе всех к Плацидусу (промах ~1.7°).
    _hs = house_system
    _polar = abs(latitude) > 66.5 and house_system in ('P', 'K')
    if _polar:
        _hs = 'R'
    cusps_raw, angles_raw = swe.houses(jd, latitude, longitude, _hs.encode())
    cusps = list(cusps_raw)
    asc = angles_raw[0]
    mc = angles_raw[1]
    _hs_name = {'P': 'Плацидус', 'K': 'Кох', 'R': 'Региомонтан',
                'O': 'Порфирий', 'C': 'Кампанус', 'W': 'Целые знаки'}.get(_hs, _hs)

    # Планеты
    planets = {}
    for planet_id, name, symbol in PLANETS:
        try:
            data = swe.calc_ut(jd, planet_id)[0]
            pos = data[0]
            speed = data[3] if len(data) > 3 else 0
            retro = speed < 0

            sign_data = deg_to_sign(pos)
            house = _find_house(pos, cusps)
            house_part = _find_house_part(pos, cusps, house)

            planets[name] = {
                'id': planet_id,
                'name': name,
                'symbol': symbol,
                'abs_degree': round(pos, 6),
                'speed': round(speed, 6),
                'retrograde': retro,
                'sign': sign_data,
                'house': house,
                'house_part': house_part,
            }
        except Exception:
            pass  # Пропускаем если эфемерида недоступна

    # Углы
    angles = {
        'ASC': deg_to_sign(asc),
        'MC': deg_to_sign(mc),
        'DSC': deg_to_sign(normalize_deg(asc + 180)),
        'IC': deg_to_sign(normalize_deg(mc + 180)),
    }

    # Дома с управителями
    houses = {}
    for i in range(12):
        cusp_sign_index = int(cusps[i] // 30)
        if cusp_sign_index >= 12:
            cusp_sign_index = 11

        houses[i + 1] = {
            'cusp': round(cusps[i], 6),
            'cusp_sign': deg_to_sign(cusps[i]),
            'ruler_modern': RULERS_MODERN[cusp_sign_index],
            'ruler_traditional': RULERS_TRADITIONAL[cusp_sign_index],
        }

    # Аспекты
    aspects = _calculate_aspects(planets)

    # Дневная/ночная карта
    sun_deg = planets.get('Солнце', {}).get('abs_degree', 0)
    moon_deg = planets.get('Луна', {}).get('abs_degree', 0)
    is_day = _is_day_chart(sun_deg, asc)

    # Вычисляемые точки
    # Южный Узел
    node_deg = planets.get('Сев.Узел', {}).get('abs_degree', 0)
    south_node_deg = normalize_deg(node_deg + 180)
    _add_computed_point(planets, 'Юж.Узел', '☋', south_node_deg, cusps, retro=True)

    # Точка Фортуны (день/ночь)
    if is_day:
        fortune_deg = normalize_deg(asc + moon_deg - sun_deg)
    else:
        fortune_deg = normalize_deg(asc + sun_deg - moon_deg)
    _add_computed_point(planets, 'Фортуна', '⊕', fortune_deg, cusps)

    # Селена (Белая Луна) — авестийская точка по П.Глобе
    selena_deg = _compute_selena(jd)
    _add_computed_point(planets, 'Селена', '⚜', selena_deg, cusps)

    # Вертекс — из расчёта домов (ascmc[3])
    vertex_deg = angles_raw[3]
    _add_computed_point(planets, 'Вертекс', 'Vx', vertex_deg, cusps)

    # Точка Жизни (на текущий момент)
    tz_deg = compute_point_of_life(jd)
    _add_computed_point(planets, 'ТЖ', '⊙', tz_deg, cusps)

    return {
        'jd': jd,
        'planets': planets,
        'cusps': cusps,
        'angles': angles,
        'houses': houses,
        'aspects': aspects,
        'is_day_chart': is_day,
        'house_system': _hs_name,
        'polar_fallback': _polar,
        'input': {
            'date': f"{day:02d}.{month:02d}.{year}",
            'time': f"{hour:02d}:{minute:02d}:{second:04.1f}",
            'timezone': f"GMT{'+' if timezone >= 0 else ''}{timezone}",
            'latitude': latitude,
            'longitude': longitude,
            'house_system': house_system,
        },
    }


# ============================================================
# ВЫЧИСЛЯЕМЫЕ ТОЧКИ
# ============================================================


def _add_computed_point(planets: dict, name: str, symbol: str,
                        abs_degree: float, cusps: list,
                        retro: bool = False):
    """Добавляет вычисляемую точку в словарь планет."""
    sign_data = deg_to_sign(abs_degree)
    house = _find_house(abs_degree, cusps)
    house_part = _find_house_part(abs_degree, cusps, house)

    planets[name] = {
        'id': -1,
        'name': name,
        'symbol': symbol,
        'abs_degree': round(abs_degree, 6),
        'speed': 0,
        'retrograde': retro,
        'sign': sign_data,
        'house': house,
        'house_part': house_part,
        'computed': True,
    }


def _compute_selena(julian_day: float) -> float:
    """
    Селена (Белая Луна) — авестийская кармическая точка по П.Глобе.
    Полный оборот за 7 лет (2556.75 дней).
    Опорная точка: 1.01.1990 12:00 UT = 88°03'.
    """
    JD_REFERENCE = 2447893.0
    SELENA_AT_REFERENCE = 88.05
    SELENA_SPEED_PER_DAY = 0.140804

    days_from_ref = julian_day - JD_REFERENCE
    selena_deg = SELENA_AT_REFERENCE + days_from_ref * SELENA_SPEED_PER_DAY
    return normalize_deg(selena_deg)


def compute_point_of_life(birth_jd: float, target_jd: float = None) -> float:
    """
    Точка Жизни (ТЖ) — по П.Глобе.

    Отсчёт от 0° Овна в момент рождения.
    Скорость: 1 знак (30°) за 7 лет. Полный цикл = 84 года.

    Args:
        birth_jd: Julian Day рождения
        target_jd: Julian Day расчёта (если None — текущий момент)

    Returns:
        Абсолютный градус ТЖ (0-360)
    """
    if target_jd is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        target_jd = swe.julday(
            now.year, now.month, now.day,
            now.hour + now.minute / 60.0
        )

    days = target_jd - birth_jd
    years = days / 365.25
    tz_deg = (years * 360.0 / 84.0) % 360.0
    return tz_deg


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================


def _find_house(pos: float, cusps: list) -> int:
    """Определяет в каком доме (1-12) находится точка."""
    pos = normalize_deg(pos)
    for i in range(12):
        c1 = cusps[i]
        c2 = cusps[(i + 1) % 12]
        if c2 < c1:  # переход через 0°
            if pos >= c1 or pos < c2:
                return i + 1
        else:
            if c1 <= pos < c2:
                return i + 1
    return 1


def _find_house_part(pos: float, cusps: list, house: int) -> int:
    """
    Определяет в какой трети дома находится точка (1/2/3).
    1 = начало (у куспида), 2 = середина, 3 = конец (у следующего куспида)
    """
    c1 = cusps[house - 1]
    c2 = cusps[house % 12]

    # Размер дома
    if c2 > c1:
        house_size = c2 - c1
        offset = normalize_deg(pos) - c1
    else:  # переход через 0°
        house_size = (360 - c1) + c2
        offset = normalize_deg(pos) - c1
        if offset < 0:
            offset += 360

    if house_size <= 0:
        return 2

    fraction = offset / house_size
    if fraction < 1 / 3:
        return 1
    elif fraction < 2 / 3:
        return 2
    else:
        return 3


def _is_day_chart(sun_deg: float, asc_deg: float) -> bool:
    """Дневная карта: Солнце над горизонтом (между DSC и ASC по часовой)."""
    dsc = normalize_deg(asc_deg + 180)
    sun = normalize_deg(sun_deg)

    if dsc < asc_deg:
        return dsc <= sun <= asc_deg
    else:
        return sun >= dsc or sun <= asc_deg


def _calculate_aspects(planets: dict) -> list:
    """Рассчитывает аспекты между всеми планетами."""
    aspects = []
    planet_names = list(planets.keys())

    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            name1 = planet_names[i]
            name2 = planet_names[j]
            pos1 = planets[name1]['abs_degree']
            pos2 = planets[name2]['abs_degree']

            diff = abs(pos1 - pos2)
            if diff > 180:
                diff = 360 - diff

            for asp_deg, (asp_name, asp_sym) in ASPECTS.items():
                orb = abs(diff - asp_deg)
                max_orb = ORBS.get(asp_deg, 6.0)

                if orb <= max_orb:
                    aspects.append({
                        'planet1': name1,
                        'planet2': name2,
                        'aspect': asp_name,
                        'aspect_symbol': asp_sym,
                        'aspect_degree': asp_deg,
                        'orb': round(orb, 2),
                        'exact': orb < 1.0,
                    })

    # Сортируем по точности
    aspects.sort(key=lambda a: a['orb'])
    return aspects


# ============================================================
# ФОРМАТИРОВАНИЕ
# ============================================================


def format_natal(chart: dict) -> str:
    """Текстовый вывод натальной карты."""
    lines = []
    inp = chart['input']

    lines.append("=" * 60)
    lines.append("НАТАЛЬНАЯ КАРТА")
    lines.append("=" * 60)
    lines.append(
        f"  Дата: {inp['date']} | Время: {inp['time']} ({inp['timezone']})"
    )
    lines.append(
        f"  Координаты: {inp['latitude']}°N {inp['longitude']}°E"
    )
    lines.append(
        f"  Карта: {'дневная' if chart['is_day_chart'] else 'ночная'}"
    )

    # Углы
    lines.append("")
    lines.append("УГЛЫ:")
    for name, data in chart['angles'].items():
        lines.append(f"  {name}: {data['formatted']}")

    # Планеты
    lines.append("")
    lines.append("ПЛАНЕТЫ:")
    for name, p in chart['planets'].items():
        r = ' R' if p['retrograde'] else ''
        part_str = f" ({p['house_part']}/3)" if p['house_part'] else ''
        lines.append(
            f"  {p['symbol']} {name:10s}: {p['sign']['formatted']:>26s}{r:3s}"
            f"  дом {p['house']:2d}{part_str}"
        )

    # Дома
    lines.append("")
    lines.append("ДОМА:")
    for num, h in chart['houses'].items():
        lines.append(
            f"  Дом {num:2d}: {h['cusp_sign']['formatted']:>26s}"
            f"  упр: {h['ruler_modern']}"
        )

    # Аспекты (только точные, орб < 3°)
    lines.append("")
    lines.append("АСПЕКТЫ (орб < 3°):")
    for a in chart['aspects']:
        if a['orb'] <= 3.0:
            exact = " !" if a['exact'] else ""
            lines.append(
                f"  {a['planet1']:10s} {a['aspect_symbol']} {a['planet2']:10s}"
                f"  {a['aspect']:12s} орб {a['orb']:.1f}°{exact}"
            )

    return "\n".join(lines)


# ============================================================
# ТЕСТ
# ============================================================

if __name__ == '__main__':
    # Влад: 30.01.1961 20:56:40 GMT+6, с. Советское
    chart = calculate_natal(
        year=1961, month=1, day=30,
        hour=20, minute=56, second=40,
        timezone=6,
        latitude=54.42985, longitude=70.34136,
    )
    print(format_natal(chart))
