"""
micro_cascade.py — Фрактальный расчёт микро-циклов

Принцип: 1 градус (3600") делится на 12 знаков по 300".
Каждый сегмент делится снова на 12 — и так до заданной глубины.
На каждом уровне фиксируется: знак, градус в знаке, сабианский номер.

Чистая математика. Никакой интерпретации.
"""

from decimal import Decimal, getcontext

# Точность: 50 знаков — хватит на 12+ уровней без потери
getcontext().prec = 50

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

# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================


def micro_cascade(deg: float, min: float, sec: float, levels: int = 6) -> list:
    """
    Фрактальная раскладка позиции внутри градуса.

    Аргументы:
        deg:    градус в знаке (0-29), используется только для
                определения сабиана основного уровня
        min:    минуты дуги (0-59)
        sec:    секунды дуги (0-59.999)
        levels: глубина раскладки (1-12)

    Возвращает:
        list of dict, каждый уровень содержит:
        - level: номер уровня (1-N)
        - sign_index: индекс знака (0-11)
        - sign_name: название знака
        - sign_symbol: символ знака
        - element: стихия
        - degree: градус внутри микро-знака (0.0-30.0)
        - degree_int: целый градус
        - degree_min: минуты
        - sabian: сабианский номер (1-30)
        - segment_size_arcsec: размер сегмента в секундах дуги
    """
    # Переводим позицию в секунды дуги (Decimal для точности)
    total_arcsec = Decimal(str(min)) * 60 + Decimal(str(sec))

    # Размер первого уровня: 1 градус = 3600"
    segment = Decimal('3600')

    results = []
    current = total_arcsec

    for level in range(1, levels + 1):
        segment = segment / 12
        sign_index = int(current / segment)

        # Защита от выхода за границу
        if sign_index >= 12:
            sign_index = 11

        remainder = current - sign_index * segment

        # Градус внутри микро-знака (0-30)
        degree = float(remainder / segment) * 30.0

        degree_int = int(degree)
        degree_min = int((degree - degree_int) * 60)
        sabian = degree_int + 1

        # Определяем в какой градус полного зодиака попадает
        # (знак * 30 + degree) — для маркировки сабианом
        full_zodiac_degree = sign_index * 30 + degree_int + 1

        results.append({
            'level': level,
            'sign_index': sign_index,
            'sign_name': SIGNS_RU[sign_index],
            'sign_symbol': SIGNS_SYM[sign_index],
            'element': ELEMENTS[sign_index],
            'degree': round(degree, 4),
            'degree_int': degree_int,
            'degree_min': degree_min,
            'sabian': sabian,
            'full_zodiac_degree': int(full_zodiac_degree),
            'segment_size_arcsec': float(segment),
        })

        # Для следующего уровня — остаток
        current = remainder

    return results


def cascade_from_absolute(abs_degree: float, levels: int = 6) -> dict:
    """
    Раскладка из абсолютной позиции (0-360).

    Возвращает:
        dict с полями:
        - abs_degree: исходная абсолютная позиция
        - sign_index: знак (0-11)
        - sign_name: название знака
        - degree: градус в знаке (с дробной частью)
        - degree_int: целый градус
        - degree_min: минуты
        - degree_sec: секунды
        - sabian: сабианский номер основного градуса
        - cascade: list of dict (результат micro_cascade)
    """
    sign_index = int(abs_degree // 30)
    if sign_index >= 12:
        sign_index = 11

    pos_in_sign = abs_degree % 30
    deg_int = int(pos_in_sign)
    remaining_min = (pos_in_sign - deg_int) * 60
    min_int = int(remaining_min)
    sec_float = (remaining_min - min_int) * 60

    cascade = micro_cascade(deg_int, min_int, sec_float, levels)

    return {
        'abs_degree': abs_degree,
        'sign_index': sign_index,
        'sign_name': SIGNS_RU[sign_index],
        'sign_symbol': SIGNS_SYM[sign_index],
        'degree': round(pos_in_sign, 6),
        'degree_int': deg_int,
        'degree_min': min_int,
        'degree_sec': round(sec_float, 2),
        'sabian': deg_int + 1,
        'cascade': cascade,
    }


# ============================================================
# УТИЛИТЫ ФОРМАТИРОВАНИЯ
# ============================================================


def format_position(deg: int, min: int, sec: float = 0) -> str:
    """Форматирует позицию: 24°19'22\""""
    if sec:
        return f"{deg}°{min:02d}'{sec:04.1f}\""
    return f"{deg}°{min:02d}'"


def format_cascade(result: dict) -> str:
    """Красивый вывод каскада в текст."""
    lines = []
    r = result
    lines.append(
        f"{r['sign_symbol']} {format_position(r['degree_int'], r['degree_min'], r['degree_sec'])} "
        f"{r['sign_name']} (сабиан {r['sabian']}°)"
    )
    lines.append("")

    for level in r['cascade']:
        indent = "  " * level['level']
        size = level['segment_size_arcsec']

        if size >= 60:
            size_str = f"{size / 60:.2f}'"
        elif size >= 1:
            size_str = f"{size:.4f}\""
        elif size >= 0.001:
            size_str = f"{size * 1000:.3f} mas"
        else:
            size_str = f"{size * 1e6:.3f} μas"

        lines.append(
            f"{indent}└─ Ур.{level['level']}: "
            f"{level['sign_symbol']} {level['sign_name']} "
            f"{level['degree_int']}°{level['degree_min']:02d}' "
            f"(сабиан {level['sabian']}°) "
            f"[{size_str}]"
        )

    return "\n".join(lines)


# ============================================================
# ТЕСТ
# ============================================================

if __name__ == '__main__':
    # Уран 24°19'22.38" Льва
    result = cascade_from_absolute(144.322883, levels=7)
    print(format_cascade(result))
    print()

    # Статистика стихий
    elements = [l['element'] for l in result['cascade']]
    from collections import Counter
    print("Стихии:", dict(Counter(elements)))
    signs = [l['sign_name'] for l in result['cascade']]
    print("Знаки:", dict(Counter(signs)))
