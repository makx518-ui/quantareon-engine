"""
degree_parser.py — Парсер базы 360 градусов зодиака

Читает gradusy_360_baza.txt и возвращает структурированные данные.
Каждый градус содержит: ОБРАЗ, ЭНЕРГЕТИКА, СУТЬ, ШАГ ПУТИ.
"""

import re
from pathlib import Path
from typing import Optional

# ============================================================
# ПАРСЕР
# ============================================================

# Маппинг русских названий знаков на индексы
SIGN_MAP = {
    'ОВЕН': 0, 'ТЕЛЕЦ': 1, 'БЛИЗНЕЦЫ': 2, 'РАК': 3,
    'ЛЕВ': 4, 'ДЕВА': 5, 'ВЕСЫ': 6, 'СКОРПИОН': 7,
    'СТРЕЛЕЦ': 8, 'КОЗЕРОГ': 9, 'ВОДОЛЕЙ': 10, 'РЫБЫ': 11,
}

SIGN_NAMES = [
    'Овен', 'Телец', 'Близнецы', 'Рак',
    'Лев', 'Дева', 'Весы', 'Скорпион',
    'Стрелец', 'Козерог', 'Водолей', 'Рыбы',
]


def parse_degree_file(filepath: str = None) -> dict:
    """
    Парсит файл gradusy_360_baza.txt.

    Возвращает:
        dict: ключ = (sign_index, degree) -> tuple (0-11, 1-30)
              значение = {
                  'sign': 'Овен',
                  'degree': 1,
                  'image': 'Женщина выходит из океана...',
                  'energy': 'Марс / Плутон',
                  'essence': 'Точка Я, первый вдох...',
                  'path_step': 'самое начало круга...',
                  'full_text': полный текст блока
              }
    """
    if filepath is None:
        filepath = str(
            Path(__file__).parent.parent / 'data' / 'gradusy_360_baza.txt'
        )

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    degrees = {}

    # Паттерн для каждого градуса: "ЗНАК N°"
    # Например: "ОВЕН 1°", "ТЕЛЕЦ 15°", "РЫБЫ 30°"
    pattern = re.compile(
        r'^([А-ЯЁІЇЄ]+)\s+(\d{1,2})°\s*$',
        re.MULTILINE
    )

    matches = list(pattern.finditer(content))

    for i, match in enumerate(matches):
        sign_str = match.group(1).upper()
        degree_num = int(match.group(2))

        if sign_str not in SIGN_MAP:
            continue

        sign_index = SIGN_MAP[sign_str]

        # Текст блока: от текущего заголовка до следующего
        start = match.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(content)

        block = content[start:end].strip()

        # Извлекаем поля
        image = _extract_field(block, 'ОБРАЗ')
        energy = _extract_field(block, 'ЭНЕРГЕТИКА')
        essence = _extract_field(block, 'СУТЬ')
        path_step = _extract_field(block, 'ШАГ ПУТИ')

        degrees[(sign_index, degree_num)] = {
            'sign': SIGN_NAMES[sign_index],
            'sign_index': sign_index,
            'degree': degree_num,
            'image': image,
            'energy': energy,
            'essence': essence,
            'path_step': path_step,
            'full_text': block,
        }

    return degrees


def _extract_field(block: str, field_name: str) -> str:
    """Извлекает значение поля из блока текста."""
    pattern = re.compile(
        rf'^{field_name}:\s*(.+?)(?=^(?:ОБРАЗ|ЭНЕРГЕТИКА|СУТЬ|ШАГ ПУТИ):|\Z)',
        re.MULTILINE | re.DOTALL
    )
    match = pattern.search(block)
    if match:
        return match.group(1).strip()
    return ''


# ============================================================
# ДОСТУП К ГРАДУСАМ
# ============================================================

class DegreeDatabase:
    """Обёртка для удобного доступа к градусам."""

    def __init__(self, filepath: str = None):
        self._data = parse_degree_file(filepath)

    @property
    def count(self) -> int:
        return len(self._data)

    def get(self, sign_index: int, degree: int) -> Optional[dict]:
        """
        Получить данные градуса.

        Args:
            sign_index: индекс знака (0=Овен, 11=Рыбы)
            degree: номер градуса (1-30)

        Returns:
            dict или None
        """
        return self._data.get((sign_index, degree))

    def get_by_absolute(self, abs_degree: float) -> Optional[dict]:
        """
        Получить данные по абсолютному градусу (0-360).

        Args:
            abs_degree: абсолютный градус

        Returns:
            dict или None
        """
        sign_index = int(abs_degree // 30)
        if sign_index >= 12:
            sign_index = 11
        degree_in_sign = int(abs_degree % 30) + 1
        return self.get(sign_index, degree_in_sign)

    def get_for_cascade_level(self, level: dict) -> Optional[dict]:
        """
        Получить данные градуса для уровня каскада.

        Args:
            level: dict из micro_cascade() — один уровень

        Returns:
            dict или None
        """
        return self.get(level['sign_index'], level['sabian'])

    def format_marker(self, sign_index: int, degree: int) -> str:
        """Краткий маркер: знак + градус + суть (одна строка)."""
        data = self.get(sign_index, degree)
        if not data:
            return f"{SIGN_NAMES[sign_index]} {degree}° — нет данных"

        essence = data['essence']
        # Берём первое предложение сути
        first_sentence = essence.split('.')[0] if essence else ''
        return f"{data['sign']} {degree}°: {first_sentence}"


# ============================================================
# ТЕСТ
# ============================================================

if __name__ == '__main__':
    db = DegreeDatabase()
    print(f"Загружено градусов: {db.count}")
    print()

    # Тест: Лев 25° (Уран)
    deg = db.get(4, 25)  # Лев = 4, 25°
    if deg:
        print(f"{deg['sign']} {deg['degree']}°")
        print(f"  ОБРАЗ: {deg['image']}")
        print(f"  ЭНЕРГЕТИКА: {deg['energy']}")
        print(f"  СУТЬ: {deg['essence'][:100]}...")
    print()

    # Тест: Рак 27° (где Луна натальная)
    deg2 = db.get(3, 27)
    if deg2:
        print(f"{deg2['sign']} {deg2['degree']}°")
        print(f"  ОБРАЗ: {deg2['image']}")
