"""
engine/vozrast_cikly.py — возрастные циклы для натальной трактовки (28.09: перенесено из Dream Oracle, astro/age_cycles.py, без изменений).

Считает где человек сейчас на ключевых астрологических циклах жизни:
- Возврат Сатурна (~29.46 лет) — кризисы зрелости (29, 58, 87)
- Оппозиция Урана (~42 года) — кризис среднего возраста
- Возврат Хирона (~50.7 лет) — кризис исцеления
- Возврат лунных узлов (~18.6 лет) — кармические повороты (18.6, 37.2, 55.8, 74.5)

Для каждого цикла возвращает:
- Прошедшие события (с приблизительной датой)
- Текущая фаза (между событиями)
- Следующее событие (с датой)
"""

from datetime import date, timedelta


# Длительность циклов в днях (точные астрономические значения)
SATURN_CYCLE_DAYS = 29.4571 * 365.25       # возврат Сатурна
URANUS_CYCLE_DAYS = 84.0205 * 365.25       # полный цикл Урана
URANUS_HALF_DAYS = URANUS_CYCLE_DAYS / 2   # оппозиция Урана
CHIRON_CYCLE_DAYS = 50.7 * 365.25          # средний возврат Хирона (эксцентрическая орбита)
NODES_CYCLE_DAYS = 18.6 * 365.25           # возврат лунных узлов (ретроградно)
JUPITER_CYCLE_DAYS = 11.86 * 365.25        # возврат Юпитера


def _calculate_event_dates(birth_date: date, cycle_days: float, today: date, name: str) -> dict:
    """Считает прошлые и будущие даты повторений цикла."""
    age_days = (today - birth_date).days
    age_years = age_days / 365.25

    # Сколько полных циклов уже прошло
    completed = int(age_days // cycle_days)

    past_events = []
    for i in range(1, completed + 1):
        event_date = birth_date + timedelta(days=cycle_days * i)
        age_at_event = (event_date - birth_date).days / 365.25
        past_events.append({
            'number': i,
            'date': event_date.strftime('%d.%m.%Y'),
            'age_years': round(age_at_event, 1),
        })

    # Следующее событие
    next_event_date = birth_date + timedelta(days=cycle_days * (completed + 1))
    age_at_next = (next_event_date - birth_date).days / 365.25
    days_until_next = (next_event_date - today).days

    # Текущая фаза цикла (0.0 = только что прошёл возврат, 1.0 = вот-вот следующий)
    current_phase = (age_days - cycle_days * completed) / cycle_days

    return {
        'name': name,
        'age_now_years': round(age_years, 1),
        'completed_count': completed,
        'past_events': past_events,
        'next_event': {
            'number': completed + 1,
            'date': next_event_date.strftime('%d.%m.%Y'),
            'age_years': round(age_at_next, 1),
            'days_until': days_until_next,
        },
        'current_phase_percent': round(current_phase * 100, 1),
    }


def calculate_age_cycles(birth_date_str: str, today: date = None) -> dict:
    """
    Главная функция: считает все возрастные циклы для натальной трактовки.

    Аргументы:
        birth_date_str: 'DD.MM.YYYY' — дата рождения
        today: date — сегодняшняя дата (по умолчанию date.today())

    Возвращает dict с циклами и единый текстовый блок для промта.
    """
    if today is None:
        today = date.today()

    # Парсим дату рождения
    try:
        parts = birth_date_str.strip().split('.')
        birth_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
    except Exception:
        return {'error': 'invalid birth_date_str format, expected DD.MM.YYYY'}

    age_years = (today - birth_date).days / 365.25

    cycles = {
        'saturn_return': _calculate_event_dates(birth_date, SATURN_CYCLE_DAYS, today, 'Возврат Сатурна'),
        'uranus_opposition': _calculate_event_dates(birth_date, URANUS_HALF_DAYS, today, 'Оппозиция Урана'),
        'chiron_return': _calculate_event_dates(birth_date, CHIRON_CYCLE_DAYS, today, 'Возврат Хирона'),
        'nodes_return': _calculate_event_dates(birth_date, NODES_CYCLE_DAYS, today, 'Возврат лунных узлов'),
        'jupiter_return': _calculate_event_dates(birth_date, JUPITER_CYCLE_DAYS, today, 'Возврат Юпитера'),
    }

    # Формируем текстовый блок для промта
    text_lines = [f"ВОЗРАСТ СЕЙЧАС: {age_years:.1f} лет\n"]

    cycle_titles = [
        ('saturn_return', '♄ ВОЗВРАТ САТУРНА (~29.46 лет)',
         'Кризис зрелости, оформление структуры жизни, ответственность'),
        ('uranus_opposition', '♅ ОППОЗИЦИЯ УРАНА (~42 года)',
         'Кризис среднего возраста, бунт против устаревшего, освобождение'),
        ('chiron_return', '⚷ ВОЗВРАТ ХИРОНА (~50.7 лет)',
         'Кризис исцеления, мудрость через боль, наставничество'),
        ('nodes_return', '☊☋ ВОЗВРАТ ЛУННЫХ УЗЛОВ (~18.6 лет)',
         'Кармический поворот, смена жизненного направления'),
        ('jupiter_return', '♃ ВОЗВРАТ ЮПИТЕРА (~11.86 лет)',
         'Расширение, новый цикл роста и возможностей'),
    ]

    for key, title, meaning in cycle_titles:
        c = cycles[key]
        text_lines.append(f"\n{title}")
        text_lines.append(f"  Смысл: {meaning}")
        if c['past_events']:
            past_str = ', '.join(
                f"#{e['number']}: {e['date']} (в {e['age_years']} лет)"
                for e in c['past_events']
            )
            text_lines.append(f"  Прошло: {past_str}")
        else:
            text_lines.append(f"  Прошло: ещё не было")
        n = c['next_event']
        text_lines.append(
            f"  Следующий: #{n['number']} — {n['date']} (в {n['age_years']} лет, через {n['days_until']} дней)"
        )
        text_lines.append(f"  Текущая фаза цикла: {c['current_phase_percent']}% (0% = только что был возврат, 100% = вот-вот следующий)")

    return {
        'age_years': round(age_years, 1),
        'cycles': cycles,
        'text_block': '\n'.join(text_lines),
    }


if __name__ == '__main__':
    # Простой тест
    result = calculate_age_cycles('30.01.1961')
    print(result['text_block'])
