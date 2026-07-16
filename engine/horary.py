"""
horary.py — Хорарный модуль Квантариона

Одно нажатие кнопки:
  таймстамп → хорарный ASC → натальная карта клиента

Принцип спонтанности: клиент нажимает когда чувствует,
его внутренний импульс синхронизирован с космическим моментом.
ASC хорара = натальный ASC клиента (гипотеза).
"""

import swisseph as swe
from datetime import datetime, timezone
from typing import Optional

from .natal import (
    calculate_natal, deg_to_sign, normalize_deg,
    to_julian_day, SIGNS_RU, SIGNS_SYM,
)


def horary_asc(
    latitude: float,
    longitude: float,
    timestamp: Optional[datetime] = None,
    house_system: str = 'P',
) -> dict:
    """
    Вычисляет хорарный ASC на момент таймстампа.

    Args:
        latitude, longitude: координаты места запроса
        timestamp: момент нажатия (если None — текущий UTC)
        house_system: система домов

    Returns:
        dict с полями:
        - timestamp: ISO строка момента
        - jd: Julian Day
        - asc: абсолютный градус ASC
        - asc_sign: данные знака ASC
        - mc: абсолютный градус MC
        - mc_sign: данные знака MC
        - cusps: все 12 куспидов
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Julian Day
    jd = swe.julday(
        timestamp.year, timestamp.month, timestamp.day,
        timestamp.hour + timestamp.minute / 60.0
        + timestamp.second / 3600.0
        + timestamp.microsecond / 3600_000_000.0
    )

    # Куспиды
    cusps_raw, angles_raw = swe.houses(
        jd, latitude, longitude, house_system.encode()
    )

    asc = angles_raw[0]
    mc = angles_raw[1]

    return {
        'timestamp': timestamp.isoformat(),
        'jd': jd,
        'asc': round(asc, 6),
        'asc_sign': deg_to_sign(asc),
        'mc': round(mc, 6),
        'mc_sign': deg_to_sign(mc),
        'cusps': [round(c, 6) for c in cusps_raw],
    }


def horary_to_natal(
    birth_year: int,
    birth_month: int,
    birth_day: int,
    latitude: float,
    longitude: float,
    timezone_offset: float = 0,
    timestamp: Optional[datetime] = None,
    horary_latitude: Optional[float] = None,
    horary_longitude: Optional[float] = None,
) -> dict:
    """
    Полный цикл: таймстамп → хорарный ASC → натальная карта.

    Принцип: хорарный ASC = натальный ASC клиента.
    Из ASC + даты рождения + координат места → полная карта.

    Args:
        birth_year, birth_month, birth_day: дата рождения
        latitude, longitude: координаты места рождения
        timezone_offset: часовой пояс рождения
        timestamp: момент нажатия кнопки
        horary_latitude, horary_longitude: координаты места запроса
            (если None — используются координаты рождения)

    Returns:
        dict с полями:
        - horary: данные хорарного момента
        - estimated_time: вычисленное время рождения
        - natal: полная натальная карта
    """
    # Координаты хорара (если не указаны — берём место рождения)
    h_lat = horary_latitude if horary_latitude is not None else latitude
    h_lon = horary_longitude if horary_longitude is not None else longitude

    # Хорарный ASC
    horary = horary_asc(h_lat, h_lon, timestamp)
    target_asc = horary['asc']

    # Ищем время рождения при котором ASC = хорарный ASC
    estimated_hour, estimated_minute, estimated_second = _find_birth_time(
        birth_year, birth_month, birth_day,
        latitude, longitude, timezone_offset,
        target_asc,
    )

    # Натальная карта с найденным временем
    natal = calculate_natal(
        year=birth_year, month=birth_month, day=birth_day,
        hour=estimated_hour, minute=estimated_minute,
        second=estimated_second,
        timezone=timezone_offset,
        latitude=latitude, longitude=longitude,
    )

    return {
        'horary': horary,
        'estimated_time': {
            'hour': estimated_hour,
            'minute': estimated_minute,
            'second': round(estimated_second, 1),
            'formatted': f"{estimated_hour:02d}:{estimated_minute:02d}:{estimated_second:04.1f}",
        },
        'natal': natal,
    }


def _find_birth_time(
    year: int, month: int, day: int,
    lat: float, lon: float, tz: float,
    target_asc: float,
) -> tuple:
    """
    Бинарный поиск времени рождения при котором ASC = target_asc.

    ASC проходит 360° за ~24 часа (~0.25° в минуту).
    Ищем с точностью до секунды.

    Returns:
        (hour, minute, second)
    """
    # Диапазон: полные сутки
    lo = 0.0       # 00:00:00
    hi = 86400.0   # 24:00:00

    # 20 итераций бинарного поиска: 86400 / 2^20 ≈ 0.08 сек
    for _ in range(20):
        mid = (lo + hi) / 2
        h = int(mid // 3600)
        m = int((mid % 3600) // 60)
        s = mid % 60

        jd = to_julian_day(year, month, day, h, m, s, tz)
        _, angles = swe.houses(jd, lat, lon, b'P')
        asc = angles[0]

        # Разница с учётом перехода через 0°
        diff = (asc - target_asc) % 360
        if diff > 180:
            diff -= 360

        if diff > 0:
            hi = mid
        else:
            lo = mid

    # Финальное значение
    final = (lo + hi) / 2
    hour = int(final // 3600)
    minute = int((final % 3600) // 60)
    second = final % 60

    return hour, minute, second


# ============================================================
# ТЕСТ
# ============================================================

if __name__ == '__main__':
    # Симуляция: таймстамп 20.06.2026 10:45 Ижевск
    from datetime import datetime, timezone, timedelta

    tz_offset = timezone(timedelta(hours=4))
    ts = datetime(2026, 6, 20, 10, 45, 0, tzinfo=tz_offset)

    result = horary_asc(
        latitude=56.8519, longitude=53.2114,
        timestamp=ts,
    )
    print(f"Хорарный ASC: {result['asc_sign']['formatted']}")
    print(f"Хорарный MC: {result['mc_sign']['formatted']}")
