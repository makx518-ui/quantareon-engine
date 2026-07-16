"""
astro/solar_arc_calculator.py — модуль расчёта Solar Arc дирекций для соляра.

Solar Arc Direction (дуга Солнца) — классическая прогностическая техника:
все натальные точки смещаются по дуге, равной движению прогрессивного Солнца
за прожитые годы (~1° в год). Дирекционные точки активируют натальные точки
через тонкие точные аспекты (орбис ≤1°).

Принципы:
- Только чистая математика и расчёты, никакой интерпретации
- Орбисы СТРОГИЕ: 1° для аспектов, 0.5° для соединений
- Особо выделяются дирекции к углам, светилам, узлам — они дают
  судьбоносные события года
- Дирекции рассматриваются к натальной И к солярной карте
- Дирекционные узлы (СУ и ЮУ) — отдельный объект анализа

Источники методики:
- Школа А.Волгина (классическая прогностика)
- Cosmobiology / Reinhold Ebertin (Solar Arc Directions)
- Современная западная астрология
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

# Строгие орбисы для дирекций (по школе Волгина)
DIRECTION_ORBIS_ASPECT = 1.0      # для трина/квадрата/секстиля/оппозиции
DIRECTION_ORBIS_CONJUNCTION = 1.0  # ±1° — единая логика дирекций (1° до точки и 1° после)

# Аспекты с подписями
ASPECT_NAMES_RU = {
    'соединение': '☌',
    'секстиль': '⚹',
    'квадрат': '□',
    'трин': '△',
    'оппозиция': '☍',
}
ASPECT_NAMES_EN = {
    'conjunction': '☌',
    'sextile': '⚹',
    'square': '□',
    'trine': '△',
    'opposition': '☍',
}
# Английский перевод аспектов
RU_TO_EN_ASPECT = {
    'соединение': 'conjunction',
    'секстиль': 'sextile',
    'квадрат': 'square',
    'трин': 'trine',
    'оппозиция': 'opposition',
}

# Категории точек (для приоритезации)
ANGLES = {'ASC', 'MC', 'IC', 'DSC'}
LUMINARIES = {'Солнце', 'Луна'}
NODES = {'Сев.Узел', 'Юж.Узел'}
PERSONAL_PLANETS = {'Меркурий', 'Венера', 'Марс'}
SOCIAL_PLANETS = {'Юпитер', 'Сатурн'}
OUTER_PLANETS = {'Уран', 'Нептун', 'Плутон'}


def _find_directed_convergence(directed_to_natal, node_aspects=None):
    """Узлы СХОЖДЕНИЯ дирекций: когда 2+ направленные точки падают на ОДНУ натальную —
    это усиленный узел судьбы (напр. направленные Плутон И Узел на натал-Нептун).
    Не два отдельных аспекта, а единая судьбоносная конфигурация — ядро года.
    Учитывает И направленные планеты, И направленные узлы (они считаются отдельно).
    """
    pool = list(directed_to_natal)
    # нормализуем аспекты направленных узлов в общий формат
    for na in (node_aspects or []):
        pool.append({
            'directed_base': na['node'].replace('dir_', ''),  # 'СУ' / 'ЮУ'
            'target_base': na['target_base'],
            'aspect': na['aspect'],
            'orb': na['orb'],
        })
    by_target = {}
    for a in pool:
        by_target.setdefault(a['target_base'], []).append(a)
    nodes = []
    for target, aspects in by_target.items():
        directed_pts = {a['directed_base'] for a in aspects}
        if len(directed_pts) >= 2:
            aspects_sorted = sorted(aspects, key=lambda x: x['orb'])
            nodes.append({
                'target': target,
                'directed': sorted(directed_pts),
                'aspects': aspects_sorted,
                'is_angle': target in ('МС', 'АСЦ', 'MC', 'ASC'),
                'is_luminary': target in ('Солнце', 'Луна'),
                'tightest_orb': aspects_sorted[0]['orb'],
            })
    nodes.sort(key=lambda n: (not (n['is_angle'] or n['is_luminary']), n['tightest_orb']))
    return nodes


def calculate_solar_arc(natal_subject, solar_subject, prog_subject=None):
    """
    Главная функция: считает Solar Arc дирекции для соляра.

    Параметры:
        natal_subject: kerykeion AstrologicalSubject — натальная карта
        solar_subject: kerykeion AstrologicalSubject — солярная карта
        prog_subject: optional, kerykeion AstrologicalSubject — прогрессивная карта.
                      Если не передана, вычисляется внутри.

    Возвращает dict со всеми ключевыми связями.
    """
    nc = chart_from_subject(natal_subject)
    sc = chart_from_subject(solar_subject)

    # Если прогрессивный субъект не передан, считаем его
    if prog_subject is None:
        # Соляр даёт нам год — используем дату соляра для расчёта возраста
        # ВАЖНО: возраст считается на момент соляра, не на текущую дату
        from kerykeion import AstrologicalSubjectFactory
        natal_dt = datetime(natal_subject.year, natal_subject.month, natal_subject.day,
                            natal_subject.hour, natal_subject.minute)
        solar_dt = datetime(solar_subject.year, solar_subject.month, solar_subject.day,
                            solar_subject.hour, solar_subject.minute)
        age_years = (solar_dt - natal_dt).days / 365.2422
        prog_date = natal_dt + timedelta(days=age_years)
        prog_subject = AstrologicalSubjectFactory.from_birth_data(
            'Progressed',
            prog_date.year, prog_date.month, prog_date.day,
            prog_date.hour, prog_date.minute,
            lng=natal_subject.lng, lat=natal_subject.lat,
            tz_str=natal_subject.tz_str, online=False
        )
    pc = chart_from_subject(prog_subject)

    # Расчёт дуги Солнца
    solar_arc = (prog_subject.sun.abs_pos - natal_subject.sun.abs_pos) % 360

    # Скорость дирекции (°/год) — для дат точного контакта и окон
    try:
        _dir_speed = (solar_arc / age_years) if age_years else None
        _dir_solar_dt = solar_dt
    except Exception:
        _dir_speed, _dir_solar_dt = None, None

    # Применяем дугу ко всем натальным точкам
    directed_points = _apply_solar_arc(nc, solar_arc)
    # Отдельно дирекционные узлы для углублённого анализа
    natal_NN = natal_subject.true_north_lunar_node.abs_pos
    natal_SN = natal_subject.true_south_lunar_node.abs_pos
    dir_NN = (natal_NN + solar_arc) % 360
    dir_SN = (natal_SN + solar_arc) % 360

    # Собираем натальные точки для сравнения с дирекциями
    natal_targets = _build_targets(nc, natal_subject, prefix='натал_')
    # Солярные точки
    solar_targets = _build_targets(sc, solar_subject, prefix='соляр_')

    # Аспекты дирекций к натальным точкам
    directed_to_natal = _find_strict_aspects(directed_points, natal_targets,
                                              skip_same_planet_natal=True,
                                              speed=_dir_speed, solar_dt=_dir_solar_dt)
    # Аспекты дирекций к солярным точкам
    directed_to_solar = _find_strict_aspects(directed_points, solar_targets,
                                              skip_same_planet_natal=False,
                                              speed=_dir_speed, solar_dt=_dir_solar_dt)

    # Особо выделяем критические дирекции
    critical_to_natal = _categorize_critical(directed_to_natal)
    critical_to_solar = _categorize_critical(directed_to_solar)

    # Дирекционные узлы — отдельный анализ
    directional_nodes_data = _analyze_directional_nodes(
        dir_NN, dir_SN, natal_targets, solar_targets,
        natal_cusps=nc['cusps']
    )

    # Узлы схождения дирекций (2+ направленные на одной натал-точке = ядро судьбы года).
    # Объединяем направленные планеты И направленные узлы (Плутон + Узел на Нептун и т.п.)
    _node_aspects = (directional_nodes_data.get('dir_NN_to_natal', []) +
                     directional_nodes_data.get('dir_SN_to_natal', []))
    directed_convergence = _find_directed_convergence(directed_to_natal, _node_aspects)


    return {
        'solar_arc_degrees': round(solar_arc, 4),
        'age_at_solar': round((datetime(solar_subject.year, solar_subject.month,
                                          solar_subject.day) -
                                datetime(natal_subject.year, natal_subject.month,
                                          natal_subject.day)).days / 365.2422, 2),
        'directed_points': directed_points,
        'directed_to_natal_aspects': directed_to_natal,
        'directed_to_solar_aspects': directed_to_solar,
        'directed_convergence': directed_convergence,
        'directions_to_angles': critical_to_natal['to_angles'],
        'directions_to_luminaries': critical_to_natal['to_luminaries'],
        'directions_to_nodes': critical_to_natal['to_nodes'],
        'directional_angles': critical_to_natal['from_angles'],
        'directional_nodes': directional_nodes_data,
        'solar_arc_directions_solar': {
            'to_angles': critical_to_solar['to_angles'],
            'to_luminaries': critical_to_solar['to_luminaries'],
            'from_angles': critical_to_solar['from_angles'],
        },
    }


def _apply_solar_arc(natal_chart, solar_arc):
    """Применяет дугу Солнца ко всем натальным точкам."""
    directed = []
    # Планеты
    for p in natal_chart['planets']:
        directed_pos = (p['deg'] + solar_arc) % 360
        directed.append({
            'name': f"dir_{p['name']}",
            'natal_pos': p['deg'],
            'deg': directed_pos,
            'sign_ru': SIGNS_RU[int(directed_pos // 30)],
            'sign_en': SIGNS_EN[int(directed_pos // 30)],
            'deg_in_sign': round(directed_pos % 30, 2),
            'category': _categorize_point(p['name']),
        })
    # Углы
    for a in natal_chart['angles']:
        directed_pos = (a['deg'] + solar_arc) % 360
        directed.append({
            'name': f"dir_{a['name']}",
            'natal_pos': a['deg'],
            'deg': directed_pos,
            'sign_ru': SIGNS_RU[int(directed_pos // 30)],
            'sign_en': SIGNS_EN[int(directed_pos // 30)],
            'deg_in_sign': round(directed_pos % 30, 2),
            'category': 'angle',
        })
    return directed


def _build_targets(chart, subject, prefix=''):
    """Собирает натальные/солярные точки для сравнения с дирекциями."""
    targets = []
    for p in chart['planets']:
        targets.append({
            'name': f"{prefix}{p['name']}",
            'deg': p['deg'],
            'category': _categorize_point(p['name']),
        })
    for a in chart['angles']:
        targets.append({
            'name': f"{prefix}{a['name']}",
            'deg': a['deg'],
            'category': 'angle',
        })
    # Узлы — отдельно
    try:
        targets.append({
            'name': f"{prefix}Сев.Узел",
            'deg': subject.true_north_lunar_node.abs_pos,
            'category': 'node',
        })
        targets.append({
            'name': f"{prefix}Юж.Узел",
            'deg': subject.true_south_lunar_node.abs_pos,
            'category': 'node',
        })
    except Exception:
        pass
    return targets


def _categorize_point(name):
    """Возвращает категорию точки: angle, luminary, node, personal, social, outer."""
    if name in ANGLES:
        return 'angle'
    if name in LUMINARIES:
        return 'luminary'
    if name in NODES:
        return 'node'
    if name in PERSONAL_PLANETS:
        return 'personal'
    if name in SOCIAL_PLANETS:
        return 'social'
    if name in OUTER_PLANETS:
        return 'outer'
    return 'other'


def _direction_dates(directed_deg, target_deg, asp_angle, speed, solar_dt):
    """Дата точного контакта дирекции и окно действия (±1° орба).

    Дирекция движется равномерно ~speed°/год (солнечная дуга). Зная текущую
    позицию и скорость, находим ближайший по времени точный контакт и окно ±1°.
    """
    from datetime import timedelta
    if not speed or speed <= 0 or solar_dt is None:
        return None, None, None
    cands = []
    for off in (asp_angle, -asp_angle):
        delta = (((target_deg + off) - directed_deg + 180) % 360) - 180
        cands.append(delta)
    signed = min(cands, key=abs)          # ближайший контакт (°, знак = до/после)
    try:
        exact = solar_dt + timedelta(days=(signed / speed) * 365.2422)
        half = (1.0 / speed) * 365.2422   # ±1° орб → ± этот период
        return (exact.date(),
                (exact - timedelta(days=half)).date(),
                (exact + timedelta(days=half)).date())
    except Exception:
        return None, None, None


def _find_strict_aspects(directed, targets, skip_same_planet_natal=True,
                         speed=None, solar_dt=None):
    """
    Ищет аспекты дирекций к таргетам с строгими орбисами.
    Соединение: 0.5°, остальные аспекты: 1.0°.

    skip_same_planet_natal: пропускать дирекцию планеты к этой же натальной
        (это просто сдвиг, не аспект).
    """
    results = []
    for d in directed:
        base_d = d['name'].replace('dir_', '')
        for t in targets:
            base_t = t['name'].replace('натал_', '').replace('соляр_', '')
            # Пропустить дирекцию планеты к самой себе натальной
            if skip_same_planet_natal and base_d == base_t and 'натал_' in t['name']:
                continue
            dist = angular_distance(d['deg'], t['deg'])
            for asp_name, asp_angle in MAJOR_ASPECTS:
                orb = abs(dist - asp_angle)
                # Разный орбис для соединения и остальных
                max_orb = DIRECTION_ORBIS_CONJUNCTION if asp_name == 'соединение' \
                          else DIRECTION_ORBIS_ASPECT
                if orb <= max_orb:
                    _ed, _ws, _we = _direction_dates(d['deg'], t['deg'], asp_angle, speed, solar_dt)
                    results.append({
                        'directed': d['name'],
                        'directed_base': base_d,
                        'directed_category': d['category'],
                        'target': t['name'],
                        'target_base': base_t,
                        'target_category': t['category'],
                        'target_deg': t.get('deg'),
                        'aspect': asp_name,
                        'aspect_symbol': ASPECT_NAMES_RU[asp_name],
                        'orb': round(orb, 3),
                        'exact_date': _ed, 'window_start': _ws, 'window_end': _we,
                        'is_to_angle': t['category'] == 'angle',
                        'is_to_luminary': t['category'] == 'luminary',
                        'is_to_node': t['category'] == 'node',
                        'is_from_angle': d['category'] == 'angle',
                    })
                    break
    # Сортируем по орбису (точнее → сильнее)
    return sorted(results, key=lambda x: x['orb'])


def _categorize_critical(aspects_list):
    """
    Делит аспекты по категориям важности:
    - to_angles: дирекции к натальным углам (события публичной/корневой жизни)
    - to_luminaries: дирекции к натальным светилам (события эго/эмоциональной жизни)
    - to_nodes: дирекции к натальным узлам (кармические события)
    - from_angles: дирекционные углы к натальным планетам (повороты судьбы)
    """
    to_angles = [a for a in aspects_list if a['is_to_angle']]
    to_luminaries = [a for a in aspects_list if a['is_to_luminary']]
    to_nodes = [a for a in aspects_list if a['is_to_node']]
    from_angles = [a for a in aspects_list if a['is_from_angle']]
    return {
        'to_angles': to_angles,
        'to_luminaries': to_luminaries,
        'to_nodes': to_nodes,
        'from_angles': from_angles,
    }


def _analyze_directional_nodes(dir_NN, dir_SN, natal_targets, solar_targets,
                                natal_cusps):
    """
    Анализирует дирекционные узлы — их положения и аспекты ко всем точкам.
    Орбис для дирекционных узлов чуть шире: 2° (узлы — медленные точки).
    """
    NODE_ORBIS = 2.0
    dir_NN_point = {'name': 'dir_СУ', 'deg': dir_NN, 'category': 'node'}
    dir_SN_point = {'name': 'dir_ЮУ', 'deg': dir_SN, 'category': 'node'}

    def find_node_aspects(node_pt, targets):
        out = []
        for t in targets:
            base_t = t['name'].replace('натал_', '').replace('соляр_', '')
            dist = angular_distance(node_pt['deg'], t['deg'])
            for asp_name, asp_angle in MAJOR_ASPECTS:
                orb = abs(dist - asp_angle)
                if orb <= NODE_ORBIS:
                    out.append({
                        'node': node_pt['name'],
                        'target': t['name'],
                        'target_base': base_t,
                        'target_category': t['category'],
                        'aspect': asp_name,
                        'orb': round(orb, 3),
                    })
                    break
        return sorted(out, key=lambda x: x['orb'])

    return {
        'dir_NN_pos': round(dir_NN, 2),
        'dir_NN_sign_ru': SIGNS_RU[int(dir_NN // 30)],
        'dir_NN_sign_en': SIGNS_EN[int(dir_NN // 30)],
        'dir_NN_deg_in_sign': round(dir_NN % 30, 2),
        'dir_NN_natal_house': degree_to_house(dir_NN, natal_cusps),
        'dir_SN_pos': round(dir_SN, 2),
        'dir_SN_sign_ru': SIGNS_RU[int(dir_SN // 30)],
        'dir_SN_sign_en': SIGNS_EN[int(dir_SN // 30)],
        'dir_SN_deg_in_sign': round(dir_SN % 30, 2),
        'dir_SN_natal_house': degree_to_house(dir_SN, natal_cusps),
        'dir_NN_to_natal': find_node_aspects(dir_NN_point, natal_targets),
        'dir_SN_to_natal': find_node_aspects(dir_SN_point, natal_targets),
        'dir_NN_to_solar': find_node_aspects(dir_NN_point, solar_targets),
        'dir_SN_to_solar': find_node_aspects(dir_SN_point, solar_targets),
    }


# ============================================================
# ФОРМАТТЕР ДЛЯ ПРОМПТА
# ============================================================

_SA_MONTHS = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
              'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def _dir_date_suffix(a):
    """Суффикс с датой точного контакта и окном действия дирекции."""
    ed = a.get('exact_date')
    if not ed:
        return ""
    s = f"  → точный контакт ~{ed.day} {_SA_MONTHS[ed.month]} {ed.year}"
    ws, we = a.get('window_start'), a.get('window_end')
    if ws and we:
        s += (f" (в орбе с {ws.day} {_SA_MONTHS[ws.month]} {ws.year} "
              f"по {we.day} {_SA_MONTHS[we.month]} {we.year})")
    return s


def format_solar_arc_for_prompt(data, lang='ru'):
    """Форматирует данные Solar Arc для подачи в LLM промпт."""
    if lang == 'ru':
        return _format_ru(data)
    return _format_en(data)


def _format_ru(d):
    """Компактный вывод дирекций — только цифры, минимум заголовков."""
    lines = []
    lines.append(f"[SOLAR ARC ДИРЕКЦИИ] возраст {d['age_at_solar']:.1f}, дуга {d['solar_arc_degrees']:.2f}°")
    _conv = d.get('directed_convergence', [])
    if _conv:
        lines.append("  *** УЗЛЫ СХОЖДЕНИЯ — ЯДРО СУДЬБЫ ГОДА (с этого начинай Тему) ***")
        for c in _conv:
            tag = "УГОЛ" if c['is_angle'] else ("СВЕТИЛО" if c['is_luminary'] else "натал-точка")
            parts = ", ".join(f"напр.{a['directed_base']} {a['aspect']} (орб {a['orb']:.2f}°)" for a in c['aspects'])
            lines.append(f"  >>> направленные {' + '.join(c['directed'])} ВСЕ сходятся на натал-{c['target']} [{tag}]: {parts}. Единая конфигурация судьбы, не отдельные аспекты — разворачивай как глубочайший корень года.")

    # Все дирекции к натальной карте (отсортированы по орбису, по группам)
    all_natal = d['directed_to_natal_aspects']
    if all_natal:
        lines.append("Дирекции к натальной карте (орбис ≤1° / соед. ≤0.5°):")
        for a in all_natal:
            _g = ""
            try:
                from astro.solar_prompt_builder import _degree_by_abs as _dba_d
                _gg = _dba_d(a.get('target_deg')) if a.get('target_deg') is not None else ''
                if _gg:
                    _g = f" [ГРАДУС натал-{a['target_base']}: {_gg}]"
            except Exception:
                pass
            lines.append(f"  dir_{a['directed_base']} {a['aspect_symbol']} натал-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a) + _g)

    # Дирекции к солярной карте (только ключевые: к углам и светилам соляра)
    sol = d['solar_arc_directions_solar']
    sol_lines = []
    seen = set()
    def _add(line, key):
        if key not in seen:
            seen.add(key)
            sol_lines.append(line)
    for a in sol['to_angles']:
        key = (a['directed_base'], a['aspect'], a['target_base'])
        _add(f"  dir_{a['directed_base']} {a['aspect_symbol']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a), key)
    for a in sol['to_luminaries']:
        key = (a['directed_base'], a['aspect'], a['target_base'])
        _add(f"  dir_{a['directed_base']} {a['aspect_symbol']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a), key)
    for a in sol['from_angles']:
        if a['target_category'] != 'angle':
            key = (a['directed_base'], a['aspect'], a['target_base'])
            _add(f"  dir_{a['directed_base']} {a['aspect_symbol']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a), key)
    if sol_lines:
        lines.append("Дирекции к солярной карте (к углам/светилам):")
        lines.extend(sol_lines)

    # Дирекционные узлы
    dn = d['directional_nodes']
    lines.append(f"Дирекционные узлы: dir_СУ {dn['dir_NN_sign_ru']} {dn['dir_NN_deg_in_sign']:.2f}° (натал-{dn['dir_NN_natal_house']}), dir_ЮУ {dn['dir_SN_sign_ru']} {dn['dir_SN_deg_in_sign']:.2f}° (натал-{dn['dir_SN_natal_house']})")
    if dn['dir_NN_to_natal']:
        for a in dn['dir_NN_to_natal']:
            lines.append(f"  dir_СУ {a['aspect']} натал-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a))
    if dn['dir_SN_to_natal']:
        for a in dn['dir_SN_to_natal']:
            lines.append(f"  dir_ЮУ {a['aspect']} натал-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a))
    if dn['dir_NN_to_solar']:
        for a in dn['dir_NN_to_solar']:
            lines.append(f"  dir_СУ {a['aspect']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a))
    if dn['dir_SN_to_solar']:
        for a in dn['dir_SN_to_solar']:
            lines.append(f"  dir_ЮУ {a['aspect']} соляр-{a['target_base']}, орбис {a['orb']:.3f}°" + _dir_date_suffix(a))

    return '\n'.join(lines)


def _format_en(d):
    """Compact directions output — numbers only, minimal headers."""
    lines = []
    lines.append(f"[SOLAR ARC DIRECTIONS] age {d['age_at_solar']:.1f}, arc {d['solar_arc_degrees']:.2f}°")

    conv = d.get('directed_convergence', [])
    if conv:
        lines.append("  *** CONVERGENCE NODES — the CORE of the year's fate (open the THEME here) ***")
        for c in conv:
            tag = "ANGLE" if c['is_angle'] else ("LUMINARY" if c['is_luminary'] else "natal point")
            parts = ", ".join(f"dir_{a['directed_base']} {RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])} (orb {a['orb']:.2f}°)" for a in c['aspects'])
            lines.append(f"  >>> directed {' + '.join(c['directed'])} ALL converge on natal-{c['target']} [{tag}]: {parts}. One single fate-configuration, not separate aspects — unfold as the year's deepest root.")

    all_natal = d['directed_to_natal_aspects']
    if all_natal:
        lines.append("Directions to natal chart (orb ≤1°):")
        for a in all_natal:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            sym = ASPECT_NAMES_EN.get(asp_en, '')
            lines.append(f"  dir_{a['directed_base']} {sym} natal-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))

    sol = d['solar_arc_directions_solar']
    sol_lines = []
    seen = set()
    for a in sol['to_angles']:
        key = (a['directed_base'], a['aspect'], a['target_base'])
        if key in seen: continue
        seen.add(key)
        asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
        sym = ASPECT_NAMES_EN.get(asp_en, '')
        sol_lines.append(f"  dir_{a['directed_base']} {sym} solar-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))
    for a in sol['to_luminaries']:
        key = (a['directed_base'], a['aspect'], a['target_base'])
        if key in seen: continue
        seen.add(key)
        asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
        sym = ASPECT_NAMES_EN.get(asp_en, '')
        sol_lines.append(f"  dir_{a['directed_base']} {sym} solar-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))
    for a in sol['from_angles']:
        if a['target_category'] != 'angle':
            key = (a['directed_base'], a['aspect'], a['target_base'])
            if key in seen: continue
            seen.add(key)
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            sym = ASPECT_NAMES_EN.get(asp_en, '')
            sol_lines.append(f"  dir_{a['directed_base']} {sym} solar-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))
    if sol_lines:
        lines.append("Directions to solar chart (to angles/luminaries):")
        lines.extend(sol_lines)

    dn = d['directional_nodes']
    lines.append(f"Directed nodes: dir_NN {dn['dir_NN_sign_en']} {dn['dir_NN_deg_in_sign']:.2f}° (natal-{dn['dir_NN_natal_house']}), dir_SN {dn['dir_SN_sign_en']} {dn['dir_SN_deg_in_sign']:.2f}° (natal-{dn['dir_SN_natal_house']})")
    if dn['dir_NN_to_natal']:
        for a in dn['dir_NN_to_natal']:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            lines.append(f"  dir_NN {asp_en} natal-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))
    if dn['dir_SN_to_natal']:
        for a in dn['dir_SN_to_natal']:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            lines.append(f"  dir_SN {asp_en} natal-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))
    if dn['dir_NN_to_solar']:
        for a in dn['dir_NN_to_solar']:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            lines.append(f"  dir_NN {asp_en} solar-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))
    if dn['dir_SN_to_solar']:
        for a in dn['dir_SN_to_solar']:
            asp_en = RU_TO_EN_ASPECT.get(a['aspect'], a['aspect'])
            lines.append(f"  dir_SN {asp_en} solar-{a['target_base']}, orb {a['orb']:.3f}°" + _dir_date_suffix(a))

    return '\n'.join(lines)
