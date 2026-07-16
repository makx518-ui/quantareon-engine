"""
astro/profections_calculator.py — модуль годовых профекций (Annual Profections).

ПРОФЕКЦИИ — древнейшая прогностическая техника эллинистической астрологии.
Каждый год жизни активируется один натальный дом по простой формуле:
    активный_дом = (возраст % 12) + 1

Управитель знака на куспиде активного дома становится "Господином Года"
(Time Lord / Хроносигнатором) — главной планетой 12 месяцев.

Логика:
- Возраст 0-1: 1-й дом
- Возраст 1-2: 2-й дом
- ...
- Возраст 11-12: 12-й дом
- Возраст 12-13: снова 1-й дом
- Возраст 65: (65 % 12) + 1 = 6-й дом

Месячные профекции — каждый месяц года активируется следующий дом по
той же логике, начиная с активного годового дома.

Дополнительно считаются:
- Все транзиты к господину года в течение солярного года
- Натальные аспекты к господину года (для понимания его силы)
- Соляр-позиция господина года и его аспекты в соляре

Источники методики:
- Hellenistic astrology (Vettius Valens, Ptolemy)
- Chris Brennan "Hellenistic Astrology" (2017)
- Demetra George "Ancient Astrology in Theory and Practice"
- Современная русская школа (Татьяна Ботанова, Анна Куликова)
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

# Управители знаков
# Традиционные (классическая астрология до Урана/Нептуна/Плутона)
TRADITIONAL_RULERS = {
    'Овен': 'Марс',
    'Телец': 'Венера',
    'Близнецы': 'Меркурий',
    'Рак': 'Луна',
    'Лев': 'Солнце',
    'Дева': 'Меркурий',
    'Весы': 'Венера',
    'Скорпион': 'Марс',
    'Стрелец': 'Юпитер',
    'Козерог': 'Сатурн',
    'Водолей': 'Сатурн',
    'Рыбы': 'Юпитер',
}

# Современные (с новыми планетами)
MODERN_RULERS = {
    'Овен': 'Марс',
    'Телец': 'Венера',
    'Близнецы': 'Меркурий',
    'Рак': 'Луна',
    'Лев': 'Солнце',
    'Дева': 'Меркурий',
    'Весы': 'Венера',
    'Скорпион': 'Плутон',
    'Стрелец': 'Юпитер',
    'Козерог': 'Сатурн',
    'Водолей': 'Уран',
    'Рыбы': 'Нептун',
}

# Английские управители (для EN форматтера)
TRADITIONAL_RULERS_EN = {
    'Aries': 'Mars', 'Taurus': 'Venus', 'Gemini': 'Mercury', 'Cancer': 'Moon',
    'Leo': 'Sun', 'Virgo': 'Mercury', 'Libra': 'Venus', 'Scorpio': 'Mars',
    'Sagittarius': 'Jupiter', 'Capricorn': 'Saturn', 'Aquarius': 'Saturn',
    'Pisces': 'Jupiter',
}
MODERN_RULERS_EN = {
    'Aries': 'Mars', 'Taurus': 'Venus', 'Gemini': 'Mercury', 'Cancer': 'Moon',
    'Leo': 'Sun', 'Virgo': 'Mercury', 'Libra': 'Venus', 'Scorpio': 'Pluto',
    'Sagittarius': 'Jupiter', 'Capricorn': 'Saturn', 'Aquarius': 'Uranus',
    'Pisces': 'Neptune',
}

# Тематика домов (краткая)
HOUSE_THEMES_RU = {
    1: "идентичность, тело, личность, начала, инициатива, физический облик",
    2: "ресурсы, деньги, имущество, ценности, навыки заработка, самоощущение",
    3: "общение, ближайшее окружение, обучение, поездки, братья/сёстры, информация",
    4: "корни, дом, семья, основание жизни, родовая память, частное пространство",
    5: "творчество, дети, романтика, самовыражение, удовольствия, авторство",
    6: "ежедневный труд, мастерство, служба, ремесло, рутина, здоровье, подчинённые",
    7: "партнёрства, открытые враги, договоры, брак, делегирование, иной",
    8: "трансформация, чужие ресурсы, кризисы, секс, смерть, наследство, тайное знание",
    9: "горизонты, философия, дальние поездки, преподавание, высшее образование, право",
    10: "карьера, репутация, статус, миссия, вершина пути, публичное признание, власть",
    11: "сообщества, друзья, цели, групповые проекты, надежды, поддерживающие связи",
    12: "уединение, мистерия, бессознательное, скрытые враги, потери, освобождение, монастырь",
}
HOUSE_THEMES_EN = {
    1: "identity, body, personality, beginnings, initiative, physical appearance",
    2: "resources, money, possessions, values, earning skills, self-worth",
    3: "communication, immediate environment, learning, short trips, siblings, information",
    4: "roots, home, family, life foundation, ancestral memory, private space",
    5: "creativity, children, romance, self-expression, pleasures, authorship",
    6: "daily work, mastery, service, craft, routine, health, subordinates",
    7: "partnerships, open enemies, contracts, marriage, delegation, the other",
    8: "transformation, others' resources, crises, sex, death, inheritance, hidden knowledge",
    9: "horizons, philosophy, long journeys, teaching, higher education, law",
    10: "career, reputation, status, mission, peak of path, public recognition, authority",
    11: "communities, friends, goals, group projects, hopes, supporting connections",
    12: "solitude, mystery, unconscious, hidden enemies, losses, liberation, monastery",
}


def calculate_profections(natal_subject, solar_subject, prog_subject=None):
    """
    Главная функция: считает годовые и месячные профекции для соляра.

    Параметры:
        natal_subject: kerykeion AstrologicalSubject — натальная карта
        solar_subject: kerykeion AstrologicalSubject — солярная карта

    Возвращает dict с полной информацией о профекциях года.
    """
    nc = chart_from_subject(natal_subject)

    # Точный возраст на момент соляра (целое число для расчёта дома)
    natal_dt = datetime(natal_subject.year, natal_subject.month, natal_subject.day)
    solar_dt = datetime(solar_subject.year, solar_subject.month, solar_subject.day)
    age_exact = (solar_dt - natal_dt).days / 365.2422
    age_int = int(age_exact)  # для расчёта дома берём целую часть

    # Активный натальный дом: (возраст mod 12) + 1, отсчёт от 1-го дома
    active_house = (age_int % 12) + 1

    # Куспид активного дома
    cusps = nc['cusps']  # 12 куспидов
    active_cusp_deg = cusps[active_house - 1]
    active_sign_idx = int(active_cusp_deg // 30)
    active_sign_ru = SIGNS_RU[active_sign_idx]
    active_sign_en = SIGNS_EN[active_sign_idx]

    # Управители (традиционный и современный)
    trad_ruler_ru = TRADITIONAL_RULERS[active_sign_ru]
    mod_ruler_ru = MODERN_RULERS[active_sign_ru]
    trad_ruler_en = TRADITIONAL_RULERS_EN[active_sign_en]
    mod_ruler_en = MODERN_RULERS_EN[active_sign_en]

    # Натальные позиции господ года
    trad_lord_data = _get_planet_data(natal_subject, trad_ruler_ru, trad_ruler_en, nc)
    mod_lord_data = (_get_planet_data(natal_subject, mod_ruler_ru, mod_ruler_en, nc)
                     if mod_ruler_ru != trad_ruler_ru else None)

    # Солярные позиции господ года — куда они попали в соляре
    sc = chart_from_subject(solar_subject)
    trad_lord_solar = _get_planet_solar_data(solar_subject, trad_ruler_ru, sc, nc)
    mod_lord_solar = (_get_planet_solar_data(solar_subject, mod_ruler_ru, sc, nc)
                      if mod_ruler_ru != trad_ruler_ru else None)

    # Месячные профекции — 12 домов начиная от активного годового
    monthly = []
    for month_num in range(12):
        house = ((active_house - 1 + month_num) % 12) + 1
        cusp_deg = cusps[house - 1]
        sign_idx = int(cusp_deg // 30)
        sign_ru = SIGNS_RU[sign_idx]
        sign_en = SIGNS_EN[sign_idx]
        trad_r_ru = TRADITIONAL_RULERS[sign_ru]
        mod_r_ru = MODERN_RULERS[sign_ru]
        trad_r_en = TRADITIONAL_RULERS_EN[sign_en]
        mod_r_en = MODERN_RULERS_EN[sign_en]
        # Месячный профекциональный месяц начинается от месяца рождения
        # На месяц 0 (натальный месяц рождения) активен годовой дом
        monthly.append({
            'month_number': month_num + 1,
            'active_house': house,
            'sign_ru': sign_ru,
            'sign_en': sign_en,
            'traditional_ruler_ru': trad_r_ru,
            'traditional_ruler_en': trad_r_en,
            'modern_ruler_ru': mod_r_ru,
            'modern_ruler_en': mod_r_en,
            'theme_ru': HOUSE_THEMES_RU[house],
            'theme_en': HOUSE_THEMES_EN[house],
        })

    return {
        'age_at_solar': round(age_exact, 4),
        'age_int': age_int,
        'active_house': active_house,
        'active_sign_ru': active_sign_ru,
        'active_sign_en': active_sign_en,
        'active_cusp_deg': round(active_cusp_deg, 2),
        'house_theme_ru': HOUSE_THEMES_RU[active_house],
        'house_theme_en': HOUSE_THEMES_EN[active_house],
        'time_lord_traditional': {
            'name_ru': trad_ruler_ru,
            'name_en': trad_ruler_en,
            'natal': trad_lord_data,
            'solar': trad_lord_solar,
        },
        'time_lord_modern': (
            {
                'name_ru': mod_ruler_ru,
                'name_en': mod_ruler_en,
                'natal': mod_lord_data,
                'solar': mod_lord_solar,
            } if mod_lord_data is not None else None
        ),
        'monthly_profections': monthly,
        'natal_dt': natal_dt.isoformat(),
        'solar_dt': solar_dt.isoformat(),
    }


def _get_planet_data(subject, planet_ru, planet_en, chart):
    """Возвращает натальную позицию планеты-управителя."""
    # Маппинг RU → kerykeion-атрибут
    KERY_MAP = {
        'Солнце': 'sun', 'Луна': 'moon', 'Меркурий': 'mercury',
        'Венера': 'venus', 'Марс': 'mars', 'Юпитер': 'jupiter',
        'Сатурн': 'saturn', 'Уран': 'uranus', 'Нептун': 'neptune',
        'Плутон': 'pluto', 'Хирон': 'chiron',
    }
    attr = KERY_MAP.get(planet_ru)
    if not attr:
        return None
    try:
        p = getattr(subject, attr)
        pos = p.abs_pos
        return {
            'name_ru': planet_ru,
            'name_en': planet_en,
            'pos': round(pos, 4),
            'sign_ru': SIGNS_RU[int(pos // 30)],
            'sign_en': SIGNS_EN[int(pos // 30)],
            'deg_in_sign': round(pos % 30, 2),
            'natal_house': degree_to_house(pos, chart['cusps']),
            'retrograde': getattr(p, 'retrograde', False),
        }
    except Exception:
        return None


def _get_planet_solar_data(solar_subject, planet_ru, sc, nc):
    """Возвращает солярную позицию планеты-управителя."""
    KERY_MAP = {
        'Солнце': 'sun', 'Луна': 'moon', 'Меркурий': 'mercury',
        'Венера': 'venus', 'Марс': 'mars', 'Юпитер': 'jupiter',
        'Сатурн': 'saturn', 'Уран': 'uranus', 'Нептун': 'neptune',
        'Плутон': 'pluto', 'Хирон': 'chiron',
    }
    attr = KERY_MAP.get(planet_ru)
    if not attr:
        return None
    try:
        p = getattr(solar_subject, attr)
        pos = p.abs_pos
        return {
            'pos': round(pos, 4),
            'sign_ru': SIGNS_RU[int(pos // 30)],
            'sign_en': SIGNS_EN[int(pos // 30)],
            'deg_in_sign': round(pos % 30, 2),
            'solar_house': degree_to_house(pos, sc['cusps']),
            'natal_house': degree_to_house(pos, nc['cusps']),
            'retrograde': getattr(p, 'retrograde', False),
        }
    except Exception:
        return None


# ============================================================
# ФОРМАТТЕР ДЛЯ ПРОМПТА
# ============================================================

def format_profections_for_prompt(data, lang='ru'):
    """Форматирует данные профекций для подачи в LLM-промпт."""
    if lang == 'ru':
        return _format_ru(data)
    return _format_en(data)


def _format_ru(d):
    """Компактный вывод профекций — только цифры."""
    lines = []
    lines.append(f"[ПРОФЕКЦИИ] возраст {d['age_at_solar']:.2f} → активный натал-дом {d['active_house']} ({d['active_sign_ru']})")
    lines.append(f"Тема дома: {d['house_theme_ru']}")

    trad = d['time_lord_traditional']
    if trad and trad['natal']:
        n = trad['natal']
        line = f"Господин года (трад.): {trad['name_ru']} — натал {n['sign_ru']} {n['deg_in_sign']:.2f}° (натал-{n['natal_house']})"
        if trad['solar']:
            s = trad['solar']
            line += f", соляр {s['sign_ru']} {s['deg_in_sign']:.2f}° (соляр-{s['solar_house']}, натал-{s['natal_house']})"
        lines.append(line)

    mod = d.get('time_lord_modern')
    if mod and mod['natal']:
        n = mod['natal']
        line = f"Господин года (совр.): {mod['name_ru']} — натал {n['sign_ru']} {n['deg_in_sign']:.2f}° (натал-{n['natal_house']})"
        if mod['solar']:
            s = mod['solar']
            line += f", соляр {s['sign_ru']} {s['deg_in_sign']:.2f}° (соляр-{s['solar_house']}, натал-{s['natal_house']})"
        lines.append(line)

    # Месячные — компактно одной строкой
    monthly = d.get('monthly_profections', [])
    if monthly:
        parts = []
        for m in monthly:
            r = m['traditional_ruler_ru'] if m['traditional_ruler_ru'] == m['modern_ruler_ru'] else f"{m['traditional_ruler_ru']}/{m['modern_ruler_ru']}"
            parts.append(f"M{m['month_number']}:{m['active_house']}({m['sign_ru']})—{r}")
        lines.append("Месячные профекции (M1=месяц рождения, дом+знак—управитель):")
        # По 4 в строку
        for i in range(0, len(parts), 4):
            lines.append("  " + " | ".join(parts[i:i+4]))

    return '\n'.join(lines)


def _format_en(d):
    """Compact profections output — numbers only."""
    lines = []
    lines.append(f"[PROFECTIONS] age {d['age_at_solar']:.2f} → active natal house {d['active_house']} ({d['active_sign_en']})")
    lines.append(f"House theme: {d['house_theme_en']}")

    trad = d['time_lord_traditional']
    if trad and trad['natal']:
        n = trad['natal']
        line = f"Time Lord (trad.): {trad['name_en']} — natal {n['sign_en']} {n['deg_in_sign']:.2f}° (natal-{n['natal_house']})"
        if trad['solar']:
            s = trad['solar']
            line += f", solar {s['sign_en']} {s['deg_in_sign']:.2f}° (solar-{s['solar_house']}, natal-{s['natal_house']})"
        lines.append(line)

    mod = d.get('time_lord_modern')
    if mod and mod['natal']:
        n = mod['natal']
        line = f"Time Lord (mod.): {mod['name_en']} — natal {n['sign_en']} {n['deg_in_sign']:.2f}° (natal-{n['natal_house']})"
        if mod['solar']:
            s = mod['solar']
            line += f", solar {s['sign_en']} {s['deg_in_sign']:.2f}° (solar-{s['solar_house']}, natal-{s['natal_house']})"
        lines.append(line)

    monthly = d.get('monthly_profections', [])
    if monthly:
        parts = []
        for m in monthly:
            r = m['traditional_ruler_en'] if m['traditional_ruler_en'] == m['modern_ruler_en'] else f"{m['traditional_ruler_en']}/{m['modern_ruler_en']}"
            parts.append(f"M{m['month_number']}:{m['active_house']}({m['sign_en']})—{r}")
        lines.append("Monthly profections (M1=birth month, house+sign—ruler):")
        for i in range(0, len(parts), 4):
            lines.append("  " + " | ".join(parts[i:i+4]))

    return '\n'.join(lines)
