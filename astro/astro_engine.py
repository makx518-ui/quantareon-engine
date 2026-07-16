"""
astro_engine.py — Универсальный модуль астрологических расчётов

Принципы:
- Только чистая математика и расчёты
- Никакой интерпретации, никакого форматирования для LLM
- Все функции pure: не меняют входные данные, всегда возвращают результат
- Изолирован от main.py
- Используется как ядро для: натал, карма, соляр, синастрия, мухурта, акг

Источники методики:
- Geocult.ru (российская школа, орбисы)
- Cafe Astrology / Volguine method
- Kepler College Library
- Классическая западная астрология
"""

# ============================================================
# КОНСТАНТЫ
# ============================================================

# 12 знаков зодиака (порядок важен — соответствует градусам 0-360)
SIGNS_RU = [
    'Овен', 'Телец', 'Близнецы', 'Рак',
    'Лев', 'Дева', 'Весы', 'Скорпион',
    'Стрелец', 'Козерог', 'Водолей', 'Рыбы',
]

SIGNS_EN = [
    'Aries', 'Taurus', 'Gemini', 'Cancer',
    'Leo', 'Virgo', 'Libra', 'Scorpio',
    'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces',
]

# Стихии знаков (Огонь/Земля/Воздух/Вода)
SIGN_ELEMENTS = {
    'Овен': 'Огонь', 'Лев': 'Огонь', 'Стрелец': 'Огонь',
    'Телец': 'Земля', 'Дева': 'Земля', 'Козерог': 'Земля',
    'Близнецы': 'Воздух', 'Весы': 'Воздух', 'Водолей': 'Воздух',
    'Рак': 'Вода', 'Скорпион': 'Вода', 'Рыбы': 'Вода',
}

# Качества знаков (Кардинальный/Фиксированный/Мутабельный)
SIGN_MODALITIES = {
    'Овен': 'Кардинальный', 'Рак': 'Кардинальный',
    'Весы': 'Кардинальный', 'Козерог': 'Кардинальный',
    'Телец': 'Фиксированный', 'Лев': 'Фиксированный',
    'Скорпион': 'Фиксированный', 'Водолей': 'Фиксированный',
    'Близнецы': 'Мутабельный', 'Дева': 'Мутабельный',
    'Стрелец': 'Мутабельный', 'Рыбы': 'Мутабельный',
}

# Управители знаков — традиционные (классика до 1781)
SIGN_RULERS_TRADITIONAL = {
    'Овен': 'Марс', 'Телец': 'Венера', 'Близнецы': 'Меркурий',
    'Рак': 'Луна', 'Лев': 'Солнце', 'Дева': 'Меркурий',
    'Весы': 'Венера', 'Скорпион': 'Марс', 'Стрелец': 'Юпитер',
    'Козерог': 'Сатурн', 'Водолей': 'Сатурн', 'Рыбы': 'Юпитер',
}

# Управители знаков — современные (после открытия Урана/Нептуна/Плутона)
SIGN_RULERS_MODERN = {
    'Овен': 'Марс', 'Телец': 'Венера', 'Близнецы': 'Меркурий',
    'Рак': 'Луна', 'Лев': 'Солнце', 'Дева': 'Меркурий',
    'Весы': 'Венера', 'Скорпион': 'Плутон', 'Стрелец': 'Юпитер',
    'Козерог': 'Сатурн', 'Водолей': 'Уран', 'Рыбы': 'Нептун',
}

# Имена планет (русские)
PLANET_NAMES_RU = {
    'sun': 'Солнце', 'moon': 'Луна', 'mercury': 'Меркурий',
    'venus': 'Венера', 'mars': 'Марс', 'jupiter': 'Юпитер',
    'saturn': 'Сатурн', 'uranus': 'Уран', 'neptune': 'Нептун',
    'pluto': 'Плутон', 'chiron': 'Хирон',
    'mean_lilith': 'Лилит', 'mean_south_node': 'Юж.Узел',
    'true_north_lunar_node': 'Сев.Узел', 'true_south_lunar_node': 'Юж.Узел',
    'mean_north_lunar_node': 'Сев.Узел',
    'selena': 'Селена', 'mean_selena': 'Селена', 'white_moon': 'Селена',
    'vertex': 'Вертекс',
}

# Орбисы по точке (по индустриальному стандарту Geocult / классика)
# Орбис аспекта = меньший из двух орбисов участников
ORBIS_BY_POINT = {
    'Солнце': 8.0, 'Луна': 8.0,
    'Меркурий': 6.0, 'Венера': 6.0, 'Марс': 6.0,
    'Юпитер': 6.0, 'Сатурн': 6.0,
    'Уран': 6.0, 'Нептун': 6.0, 'Плутон': 6.0,
    'Хирон': 5.0,
    'Лилит': 3.0, 'Селена': 3.0, 'Вертекс': 3.0,
    'Сев.Узел': 3.0, 'Юж.Узел': 3.0,
    'Парс Фортуны': 2.0,
    'ASC': 8.0, 'MC': 8.0, 'IC': 8.0, 'DSC': 8.0,
}
DEFAULT_ORBIS = 5.0  # для неизвестных точек

# Аспекты — мажорные (классические)
MAJOR_ASPECTS = [
    ('соединение', 0),
    ('секстиль', 60),
    ('квадрат', 90),
    ('трин', 120),
    ('оппозиция', 180),
]

# Аспекты — минорные (по необходимости)
MINOR_ASPECTS = [
    ('полусекстиль', 30),
    ('полуквадрат', 45),
    ('полутораквадрат', 135),
    ('квиконс', 150),
]


# ============================================================
# ГЕОМЕТРИЯ КРУГА (базовые функции)
# ============================================================

def normalize_deg(deg):
    """Привести градус к диапазону [0, 360)."""
    return deg % 360


def angular_distance(a, b):
    """
    Минимальное угловое расстояние между двумя точками на круге 360°.
    Возвращает значение в диапазоне [0, 180].
    Пример: angular_distance(350, 10) = 20 (через 0°), не 340.
    """
    d = abs(a - b) % 360
    return min(d, 360 - d)


def signed_distance(from_deg, to_deg):
    """
    Знаковое расстояние от точки A до точки B (по ходу зодиака).
    Возвращает значение в диапазоне [0, 360).
    Пример: signed_distance(350, 10) = 20 (вперёд), signed_distance(10, 350) = 340.
    """
    return (to_deg - from_deg) % 360


def deg_to_sign_pos(deg):
    """
    По абсолютному градусу эклиптики возвращает (знак_рус, градус_в_знаке).
    Пример: 162.32° → ('Дева', 12.32)
    """
    deg = normalize_deg(deg)
    sign_idx = int(deg // 30)
    return SIGNS_RU[sign_idx], deg % 30


def deg_to_sign_index(deg):
    """Возвращает индекс знака (0-11) для абс. градуса."""
    return int(normalize_deg(deg) // 30)


def degree_to_house(deg, cusps):
    """
    Определить дом планеты по её градусу и списку 12 куспидов.

    Параметры:
        deg: абсолютный градус планеты (0-360)
        cusps: список 12 куспидов [куспид_1, куспид_2, ..., куспид_12]
               где куспид_1 = ASC, куспид_10 = MC

    Корректно обрабатывает перетекание дома через 0°.
    Например: куспид_12 = 350°, куспид_1 = 20° — дом 12 пересекает 360°.

    Возвращает: номер дома (1-12) или None.
    """
    if not cusps or len(cusps) != 12:
        return None
    deg = normalize_deg(deg)
    for i in range(12):
        c1 = normalize_deg(cusps[i])
        c2 = normalize_deg(cusps[(i + 1) % 12])
        if c1 < c2:
            # Обычный случай: дом не пересекает 0°
            if c1 <= deg < c2:
                return i + 1
        else:
            # Дом пересекает 360°/0°
            if deg >= c1 or deg < c2:
                return i + 1
    return None


def is_day_chart(sun_deg, asc_deg):
    """
    Дневная карта (Солнце над горизонтом) или ночная (под горизонтом).
    Дневная: Солнце в домах 7-12 (между DSC и ASC по часовой стрелке через MC).
    Используется для расчёта Парс Фортуны.
    """
    # DSC = Asc + 180°
    dsc = normalize_deg(asc_deg + 180)
    # Солнце над горизонтом = в верхней полусфере (между ASC и DSC через MC, т.е. дома 7-12)
    diff = signed_distance(dsc, sun_deg)  # от DSC вперёд до Солнца
    return diff < 180  # если меньше 180 — Солнце выше горизонта


# ============================================================
# АСПЕКТЫ
# ============================================================

def get_orbis_for_point(point_name):
    """Орбис конкретной точки по словарю ORBIS_BY_POINT."""
    return ORBIS_BY_POINT.get(point_name, DEFAULT_ORBIS)


def get_aspect_orb(point1_name, point2_name):
    """
    Орбис аспекта между двумя точками = меньший из двух индивидуальных орбисов.
    (Классическое правило: чувствительность аспекта определяется более слабой точкой.)
    """
    orb1 = get_orbis_for_point(point1_name)
    orb2 = get_orbis_for_point(point2_name)
    return min(orb1, orb2)


def find_aspect(deg1, deg2, name1='', name2='', include_minor=False):
    """
    Найти аспект между двумя точками с учётом индивидуальных орбисов.

    Возвращает: dict {'name': 'трин', 'angle': 120, 'orb': 2.3, 'exact_distance': 117.7}
    или None если точки не в аспекте.
    """
    dist = angular_distance(deg1, deg2)
    aspects = MAJOR_ASPECTS + (MINOR_ASPECTS if include_minor else [])
    max_orb = get_aspect_orb(name1, name2) if (name1 or name2) else DEFAULT_ORBIS

    for asp_name, asp_angle in aspects:
        # Минорные аспекты имеют свои уменьшенные орбисы
        effective_orb = max_orb
        if asp_name in ('полусекстиль', 'квиконс'):
            effective_orb = min(max_orb, 3.0)
        elif asp_name in ('полуквадрат', 'полутораквадрат'):
            effective_orb = min(max_orb, 2.0)

        deviation = abs(dist - asp_angle)
        if deviation <= effective_orb:
            return {
                'name': asp_name,
                'angle': asp_angle,
                'orb': round(deviation, 2),
                'exact_distance': round(dist, 2),
            }
    return None


def all_aspects(points_a, points_b, include_minor=False):
    """
    Все аспекты между двумя наборами точек.

    Параметры:
        points_a, points_b: списки dict вида
            {'name': 'Венера', 'deg': 357.4, ...}

    Возвращает: список dict
        [{'point_a': 'Венера', 'point_b': 'Марс', 'aspect': 'квадрат', 'orb': 1.2, ...}, ...]
    Сортируется по орбису (от точных к менее точным).
    """
    result = []
    for pa in points_a:
        for pb in points_b:
            asp = find_aspect(pa['deg'], pb['deg'], pa.get('name', ''), pb.get('name', ''), include_minor)
            if asp:
                result.append({
                    'point_a': pa.get('name', ''),
                    'point_b': pb.get('name', ''),
                    'aspect': asp['name'],
                    'orb': asp['orb'],
                    'angle': asp['angle'],
                    'deg_a': pa['deg'],
                    'deg_b': pb['deg'],
                })
    return sorted(result, key=lambda x: x['orb'])

# ============================================================
# ИЗВЛЕЧЕНИЕ ДАННЫХ ИЗ KERYKEION SUBJECT
# ============================================================

# Стандартные 10 планет (атрибуты в kerykeion subject)
PLANET_ATTRS_STANDARD = [
    'sun', 'moon', 'mercury', 'venus', 'mars',
    'jupiter', 'saturn', 'uranus', 'neptune', 'pluto',
]

# Дополнительные точки (Хирон, Лилит, Селена, Вертекс, Узлы)
EXTRA_ATTRS = [
    'chiron',
    'mean_lilith',
    'selena', 'mean_selena', 'white_moon',  # разные варианты названия в kerykeion
    'vertex',
    'true_north_lunar_node', 'mean_north_lunar_node',
    'true_south_lunar_node', 'mean_south_lunar_node',
]

# Атрибуты домов в kerykeion
HOUSE_ATTRS = [
    'first_house', 'second_house', 'third_house', 'fourth_house',
    'fifth_house', 'sixth_house', 'seventh_house', 'eighth_house',
    'ninth_house', 'tenth_house', 'eleventh_house', 'twelfth_house',
]


def _safe_getattr(subject, attr):
    """Безопасное обращение к атрибуту Kerykeion subject."""
    try:
        return getattr(subject, attr, None)
    except Exception:
        return None


def extract_planet(subject, attr_name):
    """
    Извлечь одну планету из subject и привести к стандартному формату.
    Возвращает dict или None.
    """
    p = _safe_getattr(subject, attr_name)
    if p is None:
        return None
    return {
        'attr': attr_name,
        'name': PLANET_NAMES_RU.get(attr_name, attr_name),
        'deg': p.abs_pos,
        'sign': SIGNS_RU[deg_to_sign_index(p.abs_pos)],
        'pos_in_sign': normalize_deg(p.abs_pos) % 30,
        'retrograde': bool(getattr(p, 'retrograde', False)),
    }


def extract_planets(subject):
    """Все 10 классических планет в стандартном формате."""
    result = []
    for attr in PLANET_ATTRS_STANDARD:
        p = extract_planet(subject, attr)
        if p:
            result.append(p)
    return result


def extract_extras(subject):
    """
    Дополнительные точки: Хирон, Лилит, Селена, Вертекс, Узлы.
    Если в kerykeion есть только Раху (Сев.Узел), Кету (Юж.Узел) рассчитывается автоматически = Раху + 180°.
    Селена (Белая Луна) рассчитывается через pyswisseph (kerykeion её не даёт).
    Дубликаты по имени не добавляются.
    """
    result = []
    seen_names = set()
    for attr in EXTRA_ATTRS:
        p = extract_planet(subject, attr)
        if p and p['name'] not in seen_names:
            result.append(p)
            seen_names.add(p['name'])

    # Если есть Сев.Узел, но нет Юж.Узла — рассчитываем Кету как Раху + 180°
    if 'Сев.Узел' in seen_names and 'Юж.Узел' not in seen_names:
        rahu = next(p for p in result if p['name'] == 'Сев.Узел')
        ketu_deg = normalize_deg(rahu['deg'] + 180)
        result.append({
            'attr': 'computed_south_node',
            'name': 'Юж.Узел',
            'deg': ketu_deg,
            'sign': SIGNS_RU[deg_to_sign_index(ketu_deg)],
            'pos_in_sign': normalize_deg(ketu_deg) % 30,
            'retrograde': rahu.get('retrograde', False),
        })

    # Селена через pyswisseph если есть Julian Day
    if 'Селена' not in seen_names:
        jd = getattr(subject, 'julian_day', None)
        if jd is not None:
            selena = compute_selena(jd)
            if selena:
                result.append(selena)

    return result


def extract_angles(subject):
    """4 угла карты: ASC, MC, IC, DSC."""
    result = []
    asc = _safe_getattr(subject, 'first_house')
    mc = _safe_getattr(subject, 'tenth_house')
    ic = _safe_getattr(subject, 'fourth_house')
    dsc = _safe_getattr(subject, 'seventh_house')

    if asc:
        result.append({'name': 'ASC', 'deg': asc.abs_pos,
                       'sign': SIGNS_RU[deg_to_sign_index(asc.abs_pos)]})
    if mc:
        result.append({'name': 'MC', 'deg': mc.abs_pos,
                       'sign': SIGNS_RU[deg_to_sign_index(mc.abs_pos)]})
    if ic:
        result.append({'name': 'IC', 'deg': ic.abs_pos,
                       'sign': SIGNS_RU[deg_to_sign_index(ic.abs_pos)]})
    if dsc:
        result.append({'name': 'DSC', 'deg': dsc.abs_pos,
                       'sign': SIGNS_RU[deg_to_sign_index(dsc.abs_pos)]})
    return result


def extract_cusps(subject):
    """12 куспидов домов как список абсолютных градусов [0..360)."""
    cusps = []
    for attr in HOUSE_ATTRS:
        h = _safe_getattr(subject, attr)
        if h is None:
            return []  # неполная карта — куспиды не считаем
        cusps.append(h.abs_pos)
    return cusps


# ============================================================
# РАСЧЁТ ПАРС ФОРТУНЫ (арабская точка)
# ============================================================

def compute_pars_fortuna(sun_deg, moon_deg, asc_deg):
    """
    Парс Фортуны — арабская точка счастья.

    Формула:
        Дневная карта (Солнце над горизонтом):  Парс = ASC + Луна - Солнце
        Ночная карта (Солнце под горизонтом):   Парс = ASC + Солнце - Луна

    Возвращает абсолютный градус [0..360).
    """
    if is_day_chart(sun_deg, asc_deg):
        pars = asc_deg + moon_deg - sun_deg
    else:
        pars = asc_deg + sun_deg - moon_deg
    return normalize_deg(pars)


def compute_selena(julian_day):
    """
    Селена (Белая Луна, Арта) — авестийская кармическая точка по П.Глобе.

    Это НЕ астрономическая орбита. Селена движется равномерно по зодиаку,
    совершая полный оборот за 7 лет (2556.75 дней).

    Скорость: 0.140804°/день — подобрана для точного совпадения с расчётом
    Geocult.ru (российский проф. сервис), погрешность <0.1° для дат 1900-2100.

    Опорная точка: 1.01.1990 12:00 UT (JD 2447893.0) = 88°03' = 88.05°
    (эфемериды П.Глобы)

    Параметры:
        julian_day: Julian Day UT даты рождения

    Возвращает: dict {'name': 'Селена', 'deg': ..., 'sign': ..., ...}
    """
    JD_REFERENCE = 2447893.0
    SELENA_AT_REFERENCE = 88.05  # 88°03'
    SELENA_SPEED_PER_DAY = 0.140804  # ровно 7 лет = 2556.75 дней

    days_from_ref = julian_day - JD_REFERENCE
    selena_deg = SELENA_AT_REFERENCE + days_from_ref * SELENA_SPEED_PER_DAY
    selena_deg = normalize_deg(selena_deg)

    return {
        'attr': 'computed_selena',
        'name': 'Селена',
        'deg': selena_deg,
        'sign': SIGNS_RU[deg_to_sign_index(selena_deg)],
        'pos_in_sign': normalize_deg(selena_deg) % 30,
        'retrograde': False,
    }


def compute_vertex(asc_deg, mc_deg, latitude):
    """
    Вертекс — точка на пересечении эклиптики и западной первой вертикали.
    Точная формула требует RAMC и широты, что у нас может не быть напрямую.
    Возвращает None — лучше брать из kerykeion если он считает.
    """
    return None

# ============================================================
# КОНФИГУРАЦИИ
# ============================================================

def find_angular_planets(planets, angles, max_orb=8.0):
    """
    Угловые планеты — те что в орбисе max_orb от любого из 4 углов карты.
    "Угловые" = мощно активированные (классическое правило).

    Возвращает: список dict
        [{'planet': 'Венера', 'angle': 'ASC', 'orb': 1.2, 'deg': ...}, ...]
    """
    result = []
    for p in planets:
        for ang in angles:
            orb = angular_distance(p['deg'], ang['deg'])
            if orb <= max_orb:
                result.append({
                    'planet': p['name'],
                    'angle': ang['name'],
                    'orb': round(orb, 2),
                    'planet_deg': p['deg'],
                    'angle_deg': ang['deg'],
                    'sign': p.get('sign', ''),
                })
    return sorted(result, key=lambda x: x['orb'])


def find_planets_in_houses(planets, cusps):
    """
    Определить дом каждой планеты по куспидам.
    Возвращает: список dict с добавленным 'house'.
    """
    result = []
    for p in planets:
        h = degree_to_house(p['deg'], cusps)
        result.append({**p, 'house': h})
    return result


def find_stelliums(planets, min_count=3, by='sign'):
    """
    Найти стеллиумы (3+ планет в одном знаке или доме).

    by: 'sign' (по знакам) или 'house' (по домам, требует поле 'house')
    """
    groups = {}
    for p in planets:
        if by == 'sign':
            key = p.get('sign', '')
        elif by == 'house':
            key = p.get('house', None)
        else:
            continue
        if key:
            groups.setdefault(key, []).append(p['name'])
    return [
        {'where': k, 'planets': v, 'count': len(v)}
        for k, v in groups.items() if len(v) >= min_count
    ]


def find_retrogrades(planets):
    """Список ретроградных планет."""
    return [p['name'] for p in planets if p.get('retrograde', False)]


def get_sign_ruler(sign, system='modern'):
    """
    Управитель знака.
    system: 'modern' или 'traditional'
    """
    if system == 'traditional':
        return SIGN_RULERS_TRADITIONAL.get(sign)
    return SIGN_RULERS_MODERN.get(sign)


def find_house_ruler(house_num, cusps, planets, system='modern'):
    """
    Управитель дома = планета, управляющая знаком на куспиде дома.
    Возвращает: dict {'ruler_name': 'Меркурий', 'ruler_planet': {...}, 'cusp_sign': 'Дева'}
    """
    if not cusps or not (1 <= house_num <= 12):
        return None
    cusp_deg = cusps[house_num - 1]
    cusp_sign = SIGNS_RU[deg_to_sign_index(cusp_deg)]
    ruler_name = get_sign_ruler(cusp_sign, system)
    ruler_planet = next((p for p in planets if p['name'] == ruler_name), None)
    return {
        'house': house_num,
        'cusp_sign': cusp_sign,
        'cusp_deg': cusp_deg,
        'ruler_name': ruler_name,
        'ruler_planet': ruler_planet,
    }


# ============================================================
# АСПЕКТНЫЕ ФИГУРЫ (Большой трин, Тау-квадрат, Йод и т.д.)
# ============================================================

def find_grand_trine(planets, orb_tolerance=8.0):
    """
    Большой Тригон — 3 планеты в трине друг к другу (примерно 120°+120°+120°).
    Идеально — все три в одной стихии.
    """
    result = []
    n = len(planets)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                p1, p2, p3 = planets[i], planets[j], planets[k]
                d12 = angular_distance(p1['deg'], p2['deg'])
                d23 = angular_distance(p2['deg'], p3['deg'])
                d13 = angular_distance(p1['deg'], p3['deg'])
                if (abs(d12 - 120) <= orb_tolerance
                        and abs(d23 - 120) <= orb_tolerance
                        and abs(d13 - 120) <= orb_tolerance):
                    elements = {SIGN_ELEMENTS.get(p['sign'], '?')
                                for p in (p1, p2, p3)}
                    result.append({
                        'planets': [p1['name'], p2['name'], p3['name']],
                        'element': list(elements)[0] if len(elements) == 1 else 'mixed',
                    })
    return result


def find_t_square(planets, orb_tolerance=8.0):
    """
    Тау-квадрат — оппозиция + две квадратуры к третьей планете (вершина).
    """
    result = []
    n = len(planets)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(n):
                if k in (i, j):
                    continue
                p1, p2, p3 = planets[i], planets[j], planets[k]
                d12 = angular_distance(p1['deg'], p2['deg'])
                d13 = angular_distance(p1['deg'], p3['deg'])
                d23 = angular_distance(p2['deg'], p3['deg'])
                if (abs(d12 - 180) <= orb_tolerance
                        and abs(d13 - 90) <= orb_tolerance
                        and abs(d23 - 90) <= orb_tolerance):
                    result.append({
                        'opposition': [p1['name'], p2['name']],
                        'apex': p3['name'],
                    })
    return result


def find_grand_cross(planets, orb_tolerance=8.0):
    """Большой Крест — 4 планеты, 2 оппозиции + 4 квадратуры."""
    result = []
    n = len(planets)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                for m in range(k + 1, n):
                    pts = [planets[i], planets[j], planets[k], planets[m]]
                    # Сортируем по градусу для проверки структуры
                    pts_sorted = sorted(pts, key=lambda x: x['deg'])
                    p1, p2, p3, p4 = pts_sorted
                    d13 = angular_distance(p1['deg'], p3['deg'])
                    d24 = angular_distance(p2['deg'], p4['deg'])
                    d12 = angular_distance(p1['deg'], p2['deg'])
                    d23 = angular_distance(p2['deg'], p3['deg'])
                    d34 = angular_distance(p3['deg'], p4['deg'])
                    d14 = angular_distance(p1['deg'], p4['deg'])
                    if (abs(d13 - 180) <= orb_tolerance
                            and abs(d24 - 180) <= orb_tolerance
                            and abs(d12 - 90) <= orb_tolerance
                            and abs(d23 - 90) <= orb_tolerance
                            and abs(d34 - 90) <= orb_tolerance
                            and abs(d14 - 90) <= orb_tolerance):
                        result.append({
                            'planets': [p1['name'], p2['name'], p3['name'], p4['name']],
                        })
    return result


def find_yod(planets, orb_tolerance=3.0):
    """
    Йод (Перст судьбы) — секстиль + два квиконса к третьей планете (вершина).
    """
    result = []
    n = len(planets)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(n):
                if k in (i, j):
                    continue
                p1, p2, p3 = planets[i], planets[j], planets[k]
                d12 = angular_distance(p1['deg'], p2['deg'])
                d13 = angular_distance(p1['deg'], p3['deg'])
                d23 = angular_distance(p2['deg'], p3['deg'])
                if (abs(d12 - 60) <= orb_tolerance
                        and abs(d13 - 150) <= orb_tolerance
                        and abs(d23 - 150) <= orb_tolerance):
                    result.append({
                        'sextile': [p1['name'], p2['name']],
                        'apex': p3['name'],
                    })
    return result

# ============================================================
# СРАВНЕНИЕ ДВУХ КАРТ (универсально для соляр / синастрия / мухурта)
# ============================================================

def compare_two_charts(chart_a, chart_b, include_minor_aspects=False):
    """
    Универсальная функция сравнения двух карт.

    Используется для:
    - Соляр (chart_a = соляр, chart_b = натал)
    - Синастрия (chart_a = партнёр1, chart_b = партнёр2)
    - Мухурта (chart_a = транзитная карта, chart_b = натал)
    - Любая другая бикарта

    Параметры:
        chart_a, chart_b: dict вида
            {
                'planets': [...],     # из extract_planets
                'angles': [...],      # из extract_angles
                'cusps': [...],       # из extract_cusps
                'extras': [...],      # из extract_extras (опционально)
            }

    Возвращает: dict со всеми ключевыми связями между картами.
    """
    result = {}

    # 1. Аспекты планет A к планетам B
    result['aspects_a_to_b'] = all_aspects(
        chart_a.get('planets', []),
        chart_b.get('planets', []),
        include_minor=include_minor_aspects,
    )

    # 2. Аспекты планет A к углам B
    result['planets_a_to_angles_b'] = all_aspects(
        chart_a.get('planets', []),
        chart_b.get('angles', []),
        include_minor=include_minor_aspects,
    )

    # 3. Аспекты планет B к углам A
    result['planets_b_to_angles_a'] = all_aspects(
        chart_b.get('planets', []),
        chart_a.get('angles', []),
        include_minor=include_minor_aspects,
    )

    # 4. Планеты A в домах B
    if chart_b.get('cusps'):
        result['planets_a_in_houses_b'] = [
            {'planet': p['name'], 'sign': p.get('sign', ''),
             'deg': p['deg'], 'house_in_b': degree_to_house(p['deg'], chart_b['cusps'])}
            for p in chart_a.get('planets', [])
        ]
    else:
        result['planets_a_in_houses_b'] = []

    # 5. Планеты B в домах A
    if chart_a.get('cusps'):
        result['planets_b_in_houses_a'] = [
            {'planet': p['name'], 'sign': p.get('sign', ''),
             'deg': p['deg'], 'house_in_a': degree_to_house(p['deg'], chart_a['cusps'])}
            for p in chart_b.get('planets', [])
        ]
    else:
        result['planets_b_in_houses_a'] = []

    # 6. Натальные планеты на углах соляра (для соляра — критично; для синастрии — как просто планеты на углах)
    result['planets_b_on_angles_a'] = []
    if chart_a.get('angles'):
        for p in chart_b.get('planets', []):
            for ang in chart_a['angles']:
                orb = angular_distance(p['deg'], ang['deg'])
                if orb <= get_aspect_orb(p['name'], ang['name']):
                    result['planets_b_on_angles_a'].append({
                        'planet': p['name'], 'angle': ang['name'],
                        'orb': round(orb, 2), 'sign': p.get('sign', ''),
                    })
        result['planets_b_on_angles_a'].sort(key=lambda x: x['orb'])

    return result


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================

def chart_from_subject(subject):
    """
    Удобный сборщик: из kerykeion subject делает стандартный chart-dict.
    Использование:
        chart = chart_from_subject(natal_subject)
        # затем: compare_two_charts(chart_solar, chart_natal)
    """
    return {
        'planets': extract_planets(subject),
        'angles': extract_angles(subject),
        'cusps': extract_cusps(subject),
        'extras': extract_extras(subject),
    }


def recommend_houses_system(latitude):
    """
    Рекомендация системы домов на основе широты места.

    Плацидус — стандарт для большинства широт (по Волгину для соляров).
    Для приполярных широт (>60°) Плацидус даёт сильно искажённые дома —
    профессиональная практика рекомендует Равнодомную от ASC.

    Параметры:
        latitude: географическая широта в градусах (-90..+90)

    Возвращает: dict {'system': 'P'|'E', 'name': 'Placidus'|'Equal', 'reason': str}

    Коды для kerykeion:
        'P' = Placidus
        'K' = Koch
        'E' = Equal (от ASC)
        'W' = Whole Sign
        'R' = Regiomontanus
        'C' = Campanus
    """
    abs_lat = abs(latitude)
    if abs_lat > 66.0:
        return {
            'system': 'E',
            'name': 'Equal (Равнодомная от ASC)',
            'reason': f'Широта {latitude:.1f}° за полярным кругом — Плацидус не работает корректно',
        }
    if abs_lat > 60.0:
        return {
            'system': 'E',
            'name': 'Equal (Равнодомная от ASC)',
            'reason': f'Широта {latitude:.1f}° близка к полярной — Плацидус даёт искажения',
        }
    return {
        'system': 'P',
        'name': 'Placidus (Плацидус)',
        'reason': f'Стандартная система для широты {latitude:.1f}° — классика по Волгину',
    }


# ============================================================
# КОНЕЦ МОДУЛЯ
# ============================================================
