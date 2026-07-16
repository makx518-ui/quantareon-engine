"""
matrix.py — Базовая матрица оператора

Карта оператора зашита как постоянный слой.
В машинной версии — для синастрии с клиентом.
В антенной версии — как антенна для прямого чтения.

Данные: Влад, 30.01.1961 20:56:40 GMT+6, с. Советское (54.42985°N 70.34136°E)
Ректифицированный ASC: 12°27'46" Девы
"""

from .natal import calculate_natal

# ============================================================
# ДАННЫЕ ОПЕРАТОРА
# ============================================================

OPERATOR = {
    'name': 'Vlad',
    'year': 1961,
    'month': 1,
    'day': 30,
    'hour': 20,
    'minute': 56,
    'second': 40.0,
    'timezone': 6.0,
    'timezone_str': 'Asia/Almaty',   # историческая зона: в 1961 = UTC+6 (декретное время)
    'latitude': 54.42985,
    'longitude': 70.34136,
    'place': 'с. Советское, СКО',
}

# Кэш карты оператора
_operator_chart = None


def get_operator_chart() -> dict:
    """
    Возвращает натальную карту оператора (кэшируется).
    Вычисляется один раз при первом вызове.
    """
    global _operator_chart
    if _operator_chart is None:
        _operator_chart = calculate_natal(**{
            k: v for k, v in OPERATOR.items()
            if k not in ('name', 'place', 'timezone_str')
        })
    return _operator_chart


def get_operator_uran() -> float:
    """Абсолютный градус Урана оператора."""
    chart = get_operator_chart()
    return chart['planets']['Уран']['abs_degree']


def get_operator_planets() -> dict:
    """Все планеты оператора."""
    chart = get_operator_chart()
    return chart['planets']


def get_operator_info() -> dict:
    """Метаданные оператора (без карты)."""
    return {
        'name': OPERATOR['name'],
        'birth': f"{OPERATOR['day']:02d}.{OPERATOR['month']:02d}.{OPERATOR['year']}",
        'time': f"{OPERATOR['hour']:02d}:{OPERATOR['minute']:02d}:{OPERATOR['second']:04.1f}",
        'timezone': f"GMT+{OPERATOR['timezone']:.0f}",
        'place': OPERATOR['place'],
        'coordinates': {
            'latitude': OPERATOR['latitude'],
            'longitude': OPERATOR['longitude'],
        },
    }


def is_matrix_active() -> bool:
    """
    Матрица активна если карта оператора загружена.
    В будущем: проверка статуса Урана (дозрел на MC или нет).
    """
    try:
        chart = get_operator_chart()
        return chart is not None and 'Уран' in chart.get('planets', {})
    except Exception:
        return False


def matrix_status() -> dict:
    """Статус матрицы для отображения в интерфейсе."""
    chart = get_operator_chart()
    uran = chart['planets']['Уран']

    return {
        'active': True,
        'operator': OPERATOR['name'],
        'uran_position': uran['sign']['formatted'],
        'uran_house': uran['house'],
        'mode': 'machine',  # 'machine' или 'antenna' (будущее)
    }
