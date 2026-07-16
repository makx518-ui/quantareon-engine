"""
cascade_assembler.py — Сборщик: каскад + маркеры градусов

Берёт результат micro_cascade, подтягивает описание градуса
на каждом уровне из базы 360°, выдаёт размеченный текст для ИИ.
"""

from .micro_cascade import cascade_from_absolute, SIGNS_RU, SIGNS_SYM
from .degree_parser import DegreeDatabase

# ============================================================
# СБОРЩИК
# ============================================================


def assemble(abs_degree: float, levels: int = 6, db: DegreeDatabase = None) -> dict:
    """
    Полная сборка: расчёт каскада + маркеры на каждом уровне.

    Args:
        abs_degree: абсолютная позиция планеты (0-360)
        levels: глубина раскладки (1-12)
        db: экземпляр DegreeDatabase (если None — создаст сам)

    Returns:
        dict с полями:
        - base: данные основного градуса (позиция + описание)
        - levels: list of dict, каждый уровень с расчётом + описанием
        - markers_text: готовый текст для ИИ
    """
    if db is None:
        db = DegreeDatabase()

    # Расчёт каскада
    result = cascade_from_absolute(abs_degree, levels)

    # Основной градус — описание
    base_degree = db.get(result['sign_index'], result['sabian'])

    base = {
        'position': {
            'abs_degree': result['abs_degree'],
            'sign_index': result['sign_index'],
            'sign_name': result['sign_name'],
            'sign_symbol': result['sign_symbol'],
            'degree_int': result['degree_int'],
            'degree_min': result['degree_min'],
            'degree_sec': result['degree_sec'],
            'sabian': result['sabian'],
        },
        'description': base_degree,
    }

    # Уровни каскада — каждый с описанием
    assembled_levels = []
    for level in result['cascade']:
        degree_data = db.get(level['sign_index'], level['sabian'])

        assembled_levels.append({
            'calculation': level,
            'description': degree_data,
        })

    # Собираем текст для ИИ
    markers_text = _build_markers_text(base, assembled_levels)

    return {
        'base': base,
        'levels': assembled_levels,
        'markers_text': markers_text,
    }


# ============================================================
# ГЕНЕРАЦИЯ ТЕКСТА ДЛЯ ИИ
# ============================================================


def _build_markers_text(base: dict, levels: list) -> str:
    """Собирает размеченный текст для чтения ИИ."""
    lines = []

    # Заголовок
    pos = base['position']
    lines.append("=" * 60)
    lines.append("ФРАКТАЛЬНЫЙ РАСКЛАД")
    lines.append("=" * 60)
    lines.append("")

    # Основной градус
    lines.append(
        f"ЯДРО: {pos['sign_symbol']} {pos['degree_int']}°"
        f"{pos['degree_min']:02d}'{pos['degree_sec']:04.1f}\" "
        f"{pos['sign_name']} (сабиан {pos['sabian']}°)"
    )

    desc = base['description']
    if desc:
        lines.append(f"  ОБРАЗ: {desc['image']}")
        lines.append(f"  ЭНЕРГЕТИКА: {desc['energy']}")
        lines.append(f"  СУТЬ: {desc['essence']}")
        lines.append(f"  ШАГ ПУТИ: {desc['path_step']}")
    lines.append("")

    # Уровни
    lines.append("-" * 60)
    lines.append("УРОВНИ ГЛУБИНЫ (читать снизу вверх для сборки сюжета):")
    lines.append("-" * 60)
    lines.append("")

    for item in levels:
        calc = item['calculation']
        desc = item['description']

        size = calc['segment_size_arcsec']
        if size >= 60:
            size_str = f"{size / 60:.2f}'"
        elif size >= 1:
            size_str = f"{size:.4f}\""
        elif size >= 0.001:
            size_str = f"{size * 1000:.3f} mas"
        else:
            size_str = f"{size * 1e6:.3f} μas"

        lines.append(
            f"УРОВЕНЬ {calc['level']}  [{size_str}]"
        )
        lines.append(
            f"  Позиция: {calc['sign_symbol']} {calc['sign_name']} "
            f"{calc['degree_int']}°{calc['degree_min']:02d}' "
            f"(сабиан {calc['sabian']}°, стихия: {calc['element']})"
        )

        if desc:
            lines.append(f"  ОБРАЗ: {desc['image']}")
            lines.append(f"  ЭНЕРГЕТИКА: {desc['energy']}")
            lines.append(f"  СУТЬ: {desc['essence']}")
            if desc['path_step']:
                lines.append(f"  ШАГ ПУТИ: {desc['path_step']}")
        else:
            lines.append("  [описание градуса не найдено]")

        lines.append("")

    # Сводка
    lines.append("-" * 60)
    lines.append("СВОДКА:")
    lines.append("-" * 60)

    from collections import Counter

    sign_counts = Counter(
        item['calculation']['sign_name'] for item in levels
    )
    element_counts = Counter(
        item['calculation']['element'] for item in levels
    )

    lines.append(
        f"  Знаки: {', '.join(f'{s}({c})' for s, c in sign_counts.most_common())}"
    )
    lines.append(
        f"  Стихии: {', '.join(f'{e}({c})' for e, c in element_counts.most_common())}"
    )

    # Цепочка знаков
    chain = " → ".join(
        item['calculation']['sign_symbol'] for item in levels
    )
    lines.append(f"  Цепочка: {chain}")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# ТЕСТ
# ============================================================

# ============================================================
# ПОЛНЫЙ РАСКЛАД ВСЕХ ПЛАНЕТ
# ============================================================


def assemble_full_natal(chart: dict, levels: int = 4, db: DegreeDatabase = None) -> dict:
    """
    Раскладывает ВСЕ планеты и точки натальной карты по микро-циклам.
    Одна кнопка — полный фрактальный портрет.

    Args:
        chart: результат calculate_natal()
        levels: глубина раскладки (1-6)
        db: экземпляр DegreeDatabase

    Returns:
        dict с полями:
        - planets: dict, ключ=имя планеты, значение=результат assemble()
        - summary: общая сводка (стихии, знаки, паттерны)
        - markers_text: полный текст для ИИ
    """
    if db is None:
        db = DegreeDatabase()

    results = {}
    all_signs = []
    all_elements = []

    for name, planet in chart['planets'].items():
        if 'abs_degree' not in planet:
            continue
        cascade = assemble(planet['abs_degree'], levels, db)
        cascade['planet_name'] = name
        cascade['planet_symbol'] = planet.get('symbol', '')
        cascade['house'] = planet.get('house', 0)
        cascade['house_part'] = planet.get('house_part', 0)
        cascade['retrograde'] = planet.get('retrograde', False)
        results[name] = cascade

        for level in cascade['levels']:
            all_signs.append(level['calculation']['sign_name'])
            all_elements.append(level['calculation']['element'])

    from collections import Counter
    sign_counts = Counter(all_signs)
    element_counts = Counter(all_elements)

    summary = {
        'total_planets': len(results),
        'total_levels': len(results) * levels,
        'dominant_signs': sign_counts.most_common(3),
        'dominant_elements': element_counts.most_common(),
        'sign_counts': dict(sign_counts),
        'element_counts': dict(element_counts),
    }

    full_text = _build_full_text(results, summary, chart)

    return {
        'planets': results,
        'summary': summary,
        'markers_text': full_text,
    }


def _build_full_text(results: dict, summary: dict, chart: dict) -> str:
    """Собирает полный текст для ИИ по всем планетам."""
    lines = []
    lines.append("=" * 60)
    lines.append("ПОЛНЫЙ ФРАКТАЛЬНЫЙ РАСКЛАД НАТАЛЬНОЙ КАРТЫ")
    lines.append("=" * 60)
    lines.append(f"Планет: {summary['total_planets']} | "
                 f"Уровней: {summary['total_levels']}")
    lines.append(f"Доминантные стихии: {', '.join(f'{e}({c})' for e, c in summary['dominant_elements'])}")
    lines.append(f"Доминантные знаки: {', '.join(f'{s}({c})' for s, c in summary['dominant_signs'])}")
    lines.append("")

    for name, cascade in results.items():
        base = cascade['base']
        pos = base['position']
        retro = ' R' if cascade.get('retrograde') else ''
        house = cascade.get('house', '')
        part = cascade.get('house_part', '')

        lines.append("-" * 60)
        lines.append(
            f"{pos['sign_symbol']} {name}{retro} | "
            f"{pos['degree_int']}°{pos['degree_min']:02d}' {pos['sign_name']} | "
            f"дом {house} ({part}/3) | сабиан {pos['sabian']}°"
        )

        desc = base['description']
        if desc:
            lines.append(f"  ОБРАЗ: {desc['image']}")
            lines.append(f"  СУТЬ: {desc['essence'][:100]}")

        for item in cascade['levels']:
            calc = item['calculation']
            desc = item['description']
            img = desc['image'][:50] if desc else '—'
            lines.append(
                f"  Ур.{calc['level']}: {calc['sign_symbol']} {calc['sign_name']:>10s} "
                f"{calc['degree_int']}°{calc['degree_min']:02d}' (саб.{calc['sabian']}°) "
                f"| {img}..."
            )
        lines.append("")

    return "\n".join(lines)


if __name__ == '__main__':
    # Уран 24°19'22.38" Льва = 144.322883°
    result = assemble(144.322883, levels=7)
    print(result['markers_text'])
