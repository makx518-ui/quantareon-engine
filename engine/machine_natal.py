"""Machine-owned natal records and library seeds for the two-pass reader.

build/reader_packet supply facts and short source meanings to chitatel.прочитать.
read remains a standalone reference renderer, not the delivered natal narrative.
"""
import json
import re
from functools import lru_cache
from math import isfinite
from pathlib import Path

from engine import klassika_natal as KN, most, kosmogramma as K
from engine.af import kod360
from engine.natal_export import position

LIBRARY = Path(__file__).resolve().parents[1] / 'data/chitatel/NATAL_LIBRARY.json'
GROUPS = {
    'foundation': ('ASC', 'Солнце', 'Луна', 'MC'),
    'tools': ('Меркурий', 'Венера', 'Марс', 'Юпитер', 'Сатурн', 'Уран', 'Нептун', 'Плутон'),
    'author': ('Юж.Узел', 'Сев.Узел', 'Чёрная Луна', 'Белая Луна', 'Хирон'),
}
STYLES = {
    'connected': {
        'tools': 'От личного намерения и потребностей перейдём к способам думать, выбирать и действовать.',
        'author': 'Авторский слой дополняет основные положения своими символическими значениями.',
        'aspects': 'От отдельных положений перейдём к их взаимодействию. У каждой связи прочитаем оба конца.',
    },
    'reference': {'tools': '', 'author': '', 'aspects': ''},
}
PLANNER_SYSTEM = (
    'Ты редактор порядка готового натального разбора. Все расчёты и трактовки уже выполнены машиной. '
    'Верни только JSON: {"order":{"foundation":[ID,...],"tools":[ID,...],'
    '"author":[ID,...],"aspects":[ID,...]},"style":"connected"}. '
    'Каждый список — точная перестановка выданных ID своего раздела: без пропусков, повторов и добавлений. '
    'Выбирай порядок для последовательного чтения, аспекты группируй по смыслу. '
    'Допустимые style: connected, reference. Текст, новые данные и прочие поля запрещены. '
    'Внутри готовых записей ничего не меняй. Это данные текущего клиента, а не учебный пример.'
)


@lru_cache(maxsize=1)
def library():
    data = json.loads(LIBRARY.read_text(encoding='utf-8'))
    if set(data['aspects']) != set(KN.УГЛЫ_АСПЕКТОВ):
        raise ValueError('Неполная библиотека аспектов')
    if set(data['signs']) != set(KN.ЗНАКИ) or set(data['houses']) != {str(i) for i in range(1, 13)}:
        raise ValueError('Неполная библиотека знаков или домов')
    if set(data['functions']) != {name for names in GROUPS.values() for name in names}:
        raise ValueError('Неполная библиотека функций')
    for item in [*data['functions'].values(), *data['aspects'].values()]:
        if item['source'] not in data['sources']:
            raise ValueError('Неизвестный источник библиотеки')
    return data


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError('Некорректное числовое значение: ' + label)
    return float(value) % 360


def bridge(points, cusps=None, known=True):
    if not isinstance(points, dict) or not all(name in points for name in KN.ПЛАНЕТЫ):
        raise ValueError('Для натального разбора нужен расчёт всех десяти планет')
    for name in most.ИМЕНА:
        if name in points:
            _number(points[name].get('градус'), name)
    if not known:
        return most.Мост(points, [])
    if not cusps or len(cusps) != 12:
        raise ValueError('Для натала с известным временем нужны ровно 12 куспидов')
    cs = [_number(c, 'куспид') for c in cusps]
    widths = [(cs[(i+1) % 12] - c) % 360 for i, c in enumerate(cs)]
    if min(widths) <= 0 or abs(sum(widths) - 360) > 1e-5:
        raise ValueError('Нарушен порядок куспидов')
    return most.Мост(points, cs)


def _motion(a, b, kind, points):
    # Local derivative of angular deviation. No event time is predicted.
    reverse = {v: k for k, v in most.ИМЕНА.items()}
    pa, pb = points.get(reverse.get(a, a), {}), points.get(reverse.get(b, b), {})
    speeds = [pa.get('скорость'), pb.get('скорость')]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) for x in speeds):
        return 'не определено: нет скоростей обоих участников'
    delta = (float(pb['градус']) - float(pa['градус']) + 180) % 360 - 180
    angle = abs(delta)
    nominal = KN.УГЛЫ_АСПЕКТОВ[kind]
    if abs(angle - nominal) < 1e-6:
        return 'точность в момент расчёта'
    if abs(delta) < 1e-8 or abs(angle-180) < 1e-8:
        return 'не определено на границе угла'
    derivative = (1 if angle > nominal else -1) * (1 if delta > 0 else -1) * (speeds[1]-speeds[0])
    if abs(derivative) < 1e-8:
        return 'угловое отклонение почти не меняется'
    return 'сходящийся' if derivative < 0 else 'расходящийся'


def aspect_records(points, cusps=None, known=True):
    """One adopted aspect list for the reader, machine passport and SVG."""
    m = bridge(points, cusps, known)
    rows = []
    for kind, orb, a, b, note in KN.аспекты_классики(m.flat):
        angle = KN._разн(m.flat[a], m.flat[b])
        deviation = abs(angle - KN.УГЛЫ_АСПЕКТОВ[kind])
        rows.append({
            'id': 'a:' + '|'.join(sorted((a, b))) + ':' + kind,
            'A': a, 'B': b, 'kind': kind, 'nominal': KN.УГЛЫ_АСПЕКТОВ[kind],
            'angle': angle, 'orb': deviation, 'adopted_orb': orb,
            'direct': not bool(note), 'note': note,
            'exact': not bool(note) and deviation <= 1.0,
            'limit': KN.орбис_поз(m.flat, a, b, kind) if not note else None,
            'motion': _motion(a, b, kind, points) if not note else 'связь через соединение; не самостоятельная динамика',
        })
    return rows


def chart_aspects(points, cusps=None, known=True):
    """Compatibility shape for the existing HTML chart, including ASC and MC."""
    return [{'а': row['A'], 'б': row['B'], 'аспект': row['kind'],
             'орбис': row['orb'], 'точный': row['exact'], 'прямой': row['direct'],
             'пометка': row['note']} for row in aspect_records(points, cusps, known)]


def _address(p):
    return p['position'] + (f", дом {p['house']}" if p.get('house') else '')


def _point_text(p, data):
    name, fn = p['name'], data['functions'][p['name']]
    method = data['signs'][p['sign']]
    lines = [f"## {name} — {_address(p)}",
             f"{name}: {fn['theme']}. Это положение выражает данную функцию {method['method']}. "
             + (f"Область проявления — {data['houses'][str(p['house'])]}. " if p.get('house') else '')
             + f"Задача прочтения — {fn['task']}; возможное осложнение — {method['risk']}."]
    if p['layer'] == 'author':
        lines.append('Значение этой точки относится к авторскому символическому слою.')
    elif p['layer'] == 'modern':
        lines.append('Это современная трактовка высшей планеты; знак относится и к поколению, а личную конкретику уточняют дома и связи.')
    if p['ruler'] == name:
        lines.append(f"Диспозитор — {name}: цепь замыкается на собственной функции.")
    else:
        lines.append(f"Диспозитор — {p['ruler']}: {p['ruler_position']}. "
                     f"Эта связь переводит задачу точки к функции «{data['functions'][p['ruler']]['theme']}».")
    lines.append('Цепь диспозиторов: ' + ' → '.join(p['chain']) + '.')
    if p['rules']:
        lines.append('Управляет домами: ' + ', '.join(map(str, p['rules'])) + '. Эти области связаны с домом расположения управителя.')
    if p['dignity']:
        lines.append(f"Положение по принятой таблице достоинств: {p['dignity']}.")
    if p['retro'] is not None:
        lines.append('Движение: ' + ('ретроградное.' if p['retro'] else 'директное.') +
                     (' В трактовке это повод рассмотреть пересмотр и повторное освоение функции, без вывода о неизбежных событиях.' if p['retro'] else ''))
    if p['stationary']:
        lines.append('Расчётная отметка движения: стационарность. Она не определяется по одному флагу ретроградности.')
    code = p['code']
    lines.append(f"Авторский символ {p['symbol']}-го градуса знака — [{code['tag']}]. "
                 f"Смысл: {code['суть']} Действие: {code['действие']} Риск: {code['риск']}")
    return '\n\n'.join(lines)


def _chain(name, m):
    chain = [name]
    while len(chain) <= len(m.flat):
        ruler = KN.УПРАВИТЕЛЬ[KN._знак(m.flat[chain[-1]])]
        chain.append(ruler)
        if ruler in chain[:-1] or ruler not in m.flat:
            break
    return chain


def _aspect_text(row, cards, data):
    a, b = cards[row['A']], cards[row['B']]
    kind = row['kind']
    rule = data['aspects'][kind]
    af, bf = data['functions'][a['name']], data['functions'][b['name']]
    theme = data['pair_themes'].get(a['name']+'|'+b['name']) or data['pair_themes'].get(b['name']+'|'+a['name'])
    theme = theme or af['theme'] + ' и ' + bf['theme']
    geometry = (f"Номинальный угол {row['nominal']}°; фактический угол {row['angle']:.4f}°; "
                f"отклонение {row['orb']:.4f}°.")
    if row['direct']:
        geometry += f" Прямой аспект, допустимый орбис {row['limit']:g}°."
        geometry += ' Точный по порогу ≤1°.' if row['exact'] else ' Не обозначается как точный.'
        geometry += ' Динамика: ' + row['motion'] + '.'
    else:
        geometry += ' ' + row['note'] + '; это расширенная связь по принятому правилу, а не прямой аспект в стандартном орбисе.'
    lines = [f"## {a['name']} — {b['name']}: {kind}", geometry,
             f"Первый конец — {a['name']}: {_address(a)}; {af['theme']}, "
             f"{data['signs'][a['sign']]['method']}. Диспозитор — {a['ruler']}.",
             f"Второй конец — {b['name']}: {_address(b)}; {bf['theme']}, "
             f"{data['signs'][b['sign']]['method']}. Диспозитор — {b['ruler']}.",
             f"Связь функций — {theme}. {rule['principle']} "
             + rule['synthesis'].format(a_task=af['task'], b_task=bf['task'])]
    for point in (a, b):
        code = point['code']
        # The full dictionary meaning is printed once in the point's portrait;
        # each aspect retains its exact owner's short label, not a generated paraphrase.
        brief = re.split(r'(?<=[.!?])\s+', code['суть'], maxsplit=1)[0]
        lines.append(f"Градус {point['name']} — {point['symbol']}-й, [{code['tag']}]: {brief}")
    # Degree synthesis uses each owner's action, never guesses a substituted code.
    lines.append(f"Синтез градусов в этой связи: {a['name']} — {a['code']['действие']} "
                 f"{b['name']} — {b['code']['действие']} " +
                 {'соединение': 'Эти задачи следует выполнять совместно, различая их назначение.',
                  'оппозиция': 'Эти задачи необходимо согласовать, не исключая одну ради другой.',
                  'квадрат': 'Сопоставление этих задач помогает увидеть, какой способ действия нуждается в изменении.',
                  'трин': 'Согласованность этих задач можно использовать как ресурс для конкретного действия.',
                  'секстиль': 'Для сотрудничества этих задач нужен осознанный практический шаг.'}[kind])
    lines.append('Граница прочтения: ' + rule['risk'])
    if a['layer'] == 'author' or b['layer'] == 'author':
        lines.append('Связь с авторской точкой читается как символическое дополнение, отдельно от основных планетных функций.')
    return '\n\n'.join(lines)


def build(points, cusps=None, known=True):
    data, m = library(), bridge(points, cusps, known)
    rulers = KN._дома_управления(m)
    reverse = {v: k for k, v in most.ИМЕНА.items()}
    cards = {}
    for name, longitude in m.flat.items():
        sign = KN._знак(longitude)
        ruler = KN.УПРАВИТЕЛЬ[sign]
        source = points.get(reverse.get(name, name), {})
        code = kod360.code_by_abs(longitude)
        card = {'id': 'p:' + name, 'name': name, 'longitude': longitude,
                'position': position(longitude), 'sign': sign, 'symbol': KN._градус(longitude),
                'house': m.house_of(longitude) if known else None,
                'ruler': ruler, 'ruler_position': position(m.flat[ruler]) +
                    (f", дом {m.house_of(m.flat[ruler])}" if known else ''),
                'chain': _chain(name, m), 'rules': rulers.get(name, []),
                'retro': bool(source.get('ретро')) if name not in KN.УГЛОВЫЕ else None,
                'stationary': bool(source.get('стоянка')) if name not in KN.УГЛОВЫЕ else False,
                'dignity': K.достоинство(name, sign)[0] if name in KN.ПЛАНЕТЫ else '',
                'layer': data['functions'][name].get('layer', 'classical'),
                'code': {k: code[k] for k in ('tag', 'суть', 'действие', 'риск')},
                'source': data['functions'][name]['source']}
        card['text'] = _point_text(card, data)
        cards[name] = card
    if known:
        for card in cards.values():
            house = card['house']
            cusp = m.cusps[house-1]
            owner = KN.УПРАВИТЕЛЬ[KN._знак(cusp)]
            card['house_cusp'] = position(cusp)
            card['house_ruler'] = owner
            card['house_ruler_position'] = _address(cards[owner])
    aspects = aspect_records(points, cusps, known)
    for row in aspects:
        row['text'] = _aspect_text(row, cards, data)
        row['source'] = 'aspects'
    groups = {key: [cards[n]['id'] for n in names if n in cards] for key, names in GROUPS.items()}
    groups['aspects'] = [row['id'] for row in aspects]
    return {'version': data['version'], 'known': known, 'points': cards,
            'aspects': aspects, 'groups': groups, 'bridge': m}


def reader_packet(machine, names=None, with_aspects=True):
    """Short contextual shelves; identities refer to the same calculation as SVG.

    The model supplies a contextual reading, not new facts. Both endpoint degree
    meanings remain in their own point records, including when the rulers coincide.
    """
    data = library()
    cards = []
    for p in machine['points'].values():
        if names is not None and p['name'] not in names:
            continue
        card = {k: p[k] for k in ('id', 'name', 'position', 'symbol', 'ruler',
                 'ruler_position', 'chain', 'rules', 'retro', 'stationary', 'dignity', 'layer', 'code')}
        card['function'] = data['functions'][p['name']]['theme']
        card['task'] = data['functions'][p['name']]['task']
        card['sign_method'] = data['signs'][p['sign']]
        if machine['known']:
            card.update({k: p[k] for k in ('house', 'house_cusp', 'house_ruler', 'house_ruler_position')})
            card['house_meaning'] = data['houses'][str(p['house'])]
        cards.append(card)
    aspects = []
    for row in machine['aspects'] if with_aspects else []:
        a, b = machine['points'][row['A']], machine['points'][row['B']]
        theme = (data['pair_themes'].get(a['name']+'|'+b['name']) or
                 data['pair_themes'].get(b['name']+'|'+a['name']) or
                 data['functions'][a['name']]['theme']+' и '+data['functions'][b['name']]['theme'])
        item = {k: row[k] for k in ('id', 'A', 'B', 'kind', 'nominal', 'angle',
                                   'orb', 'direct', 'exact', 'note', 'motion')}
        item['endpoint_ids'] = [a['id'], b['id']]
        item['pair_theme'] = theme
        item['degree_actions'] = {a['name']: a['code']['действие'], b['name']: b['code']['действие']}
        if machine['known']:
            item['life_domains'] = {a['name']: data['houses'][str(a['house'])],
                                    b['name']: data['houses'][str(b['house'])]}
        aspects.append(item)
    payload = {'source': 'текущая карта; точные факты и смысловые основания, не готовый рассказ',
               'version': machine['version'], 'known_birth_time': machine['known'],
               'points': cards, 'aspects': aspects,
               'aspect_meanings': {k: {'principle': v['principle'], 'risk': v['risk']}
                                   for k, v in data['aspects'].items()} if with_aspects else {},
               'sources': data['sources'],
               'reading_task': 'Прочти оба конца из их собственных записей и раскрой совместный смысл '
                 'через вид аспекта, функции, жизненные сферы и оба значения градусов. '
                 'Повторяющиеся темы свяжи в сквозной сценарий. Не печатай эти записи вместо рассказа.'}
    return '[МАШИННЫЕ ОСНОВАНИЯ ДЛЯ ГЛУБОКОГО ПРОЧТЕНИЯ]\n'+json.dumps(
        payload, ensure_ascii=False, separators=(',', ':'))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def validate_plan(raw, groups):
    """Reject omission, prose, foreign IDs, duplicate IDs/keys and type tricks."""
    if not isinstance(raw, str) or len(raw) > 24000:
        raise ValueError('Некорректный ответ редактора')
    fence = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', raw, flags=re.S)
    if fence:
        raw = fence.group(1)
    plan = json.loads(raw, object_pairs_hook=_unique_object)
    if (not isinstance(plan, dict) or set(plan) != {'order', 'style'}
            or not isinstance(plan['style'], str) or plan['style'] not in STYLES):
        raise ValueError('Нарушен контракт редактора')
    order = plan['order']
    if not isinstance(order, dict) or set(order) != set(groups):
        raise ValueError('Нарушен список разделов')
    for key, required in groups.items():
        ids = order[key]
        if (not isinstance(ids, list) or any(not isinstance(x, str) for x in ids)
                or len(ids) != len(required) or len(set(ids)) != len(ids) or set(ids) != set(required)):
            raise ValueError('Нарушено полное покрытие: ' + key)
    return plan


def _house_texts(m, cards, data):
    result = []
    for i, cusp in enumerate(m.cusps, 1):
        sign = KN._знак(cusp)
        ruler = KN.УПРАВИТЕЛЬ[sign]
        occupants = [p['name'] for p in cards.values() if p['house'] == i and p['name'] not in KN.УГЛОВЫЕ]
        destination = cards[ruler]['house']
        result.append(f"## Дом {i} — {data['houses'][str(i)]}\n\n"
                      f"Куспид: {position(cusp)}. Управитель — {ruler}: {_address(cards[ruler])}. "
                      f"Сфера выражается {data['signs'][sign]['method']}; "
                      f"управитель связывает эту область с темой «{data['houses'][str(destination)]}». "
                      + ('В доме: ' + ', '.join(occupants) + '. Их функции конкретизируют эту сферу.' if occupants else
                         'В доме нет точек принятого набора. Его тема читается через куспид и управителя, а не считается отсутствующей.') +
                      f"\n\nАвторский символ {KN._градус(cusp)}-го градуса куспида — "
                      f"[{kod360.code_by_abs(cusp)['tag']}]: {kod360.code_by_abs(cusp)['суть']}")
    return result


def _scenario(machine, data):
    cards, aspects = machine['points'], machine['aspects']
    personal = {'Солнце', 'Луна', 'Меркурий', 'Венера', 'Марс', 'ASC'}
    direct = [r for r in aspects if r['direct'] and {r['A'], r['B']} & personal]
    hard = sorted((r for r in direct if r['kind'] in ('квадрат', 'оппозиция')), key=lambda r: (r['orb'], r['id']))
    support = sorted((r for r in direct if r['kind'] in ('трин', 'секстиль')), key=lambda r: (r['orb'], r['id']))
    def point(name, stage):
        p = cards[name]
        fn = data['functions'][name]
        return f"## {stage}\n\nОснование — {name}: {_address(p)}. " + fn['task'].capitalize() + \
            f" {data['signs'][p['sign']]['method']}. Практическое уточнение градуса: {p['code']['действие']}"
    def connection(rows, stage):
        if not rows:
            return f"## {stage}\n\nВ принятом наборе нет прямой связи этого типа с личными точками; выбирать её догадкой нельзя."
        r = rows[0]
        a, b = cards[r['A']], cards[r['B']]
        rule = data['aspects'][r['kind']]
        return (f"## {stage}\n\nОснование — {r['A']} — {r['B']}: {r['kind']}, орб {r['orb']:.4f}°. "
                'Это наиболее тесная прямая связь данного типа с личной точкой, а не единственный главный фактор карты. '
                + rule['synthesis'].format(a_task=data['functions'][a['name']]['task'], b_task=data['functions'][b['name']]['task']))
    texts = ['Последовательность «вход → потребность → действие → противоречие → опора → выход» '
             'связывает функции личности. Это порядок прочтения, без назначенных дат и событий.',
             point('ASC' if machine['known'] else 'Солнце', '1. Вход'),
             point('Луна', '2. Потребность'), point('Марс', '3. Действие'),
             connection(hard, '4. Противоречие'), connection(support, '5. Опора'),
             point('MC' if machine['known'] else 'Солнце', '6. Выход')]
    if 'Сев.Узел' in cards and 'Юж.Узел' in cards:
        south, north = cards['Юж.Узел'], cards['Сев.Узел']
        texts.append(f"## Авторский вектор\n\nЮж.Узел — {_address(south)}: {south['code']['действие']} "
                     f"Сев.Узел — {_address(north)}: {north['code']['действие']} "
                     'Привычный способ можно использовать как опору для освоения нового, без вывода о предопределённой биографии.')
    return '\n\n'.join(texts)


def _configuration_text(m):
    """Keep machine figure identities; omit legacy promises about the native."""
    lines = KN.конфигурации(m).splitlines()[1:]
    # A yod also uses this separator between its two base points. Only the
    # last separator introduces the legacy interpretation, so retain both ends.
    cleaned = [line.rsplit(' — ', 1)[0].strip() for line in lines]
    if any('ЙОД' in line for line in cleaned):
        cleaned.append('Йод — дополнительная конфигурация: секстиль основания и два квинкункса 150° '
                       'к вершине, каждый в пределах 3°. Квинкунксы учитываются здесь отдельно от пяти основных аспектов.')
    return '\n'.join(cleaned)


def read(points, cusps=None, known=True, ask=None, birth=None, name='человек', lunar_day=None):
    machine = build(points, cusps, known)
    data, groups = library(), machine['groups']
    phase_angle = (machine['points']['Луна']['longitude'] - machine['points']['Солнце']['longitude']) % 360
    phase = ('Фаза на момент рождения: ' if known else 'Фаза условного момента расчёта: ') + most.фаза_словами(phase_angle)
    phase += f"; угол от Солнца к Луне по ходу зодиака {phase_angle:.4f}°."
    if known and isinstance(lunar_day, int) and not isinstance(lunar_day, bool) and 1 <= lunar_day <= 30:
        phase += f" Лунный день по месту рождения: {lunar_day}."
    machine['points']['Луна']['text'] += '\n\n' + phase
    plan = {'order': groups, 'style': 'connected'}
    mode, reason = 'machine', 'редактор не запрошен'
    if ask is not None:
        packet = {'groups': groups, 'cards': list(machine['points'].values()),
                  'aspects': machine['aspects'], 'sources': data['sources']}
        try:
            raw = ask(PLANNER_SYSTEM, [{'role': 'user', 'content': json.dumps(packet, ensure_ascii=False)}],
                      максимум=4000, температура=0, редактор=True)
            plan = validate_plan(raw, groups)
            mode, reason = 'ai_order', ''
        except Exception as exc:
            # No delivery hold for an unavailable/invalid stylistic planner.
            reason = type(exc).__name__
    texts = {p['id']: p['text'] for p in machine['points'].values()}
    texts.update({r['id']: r['text'] for r in machine['aspects']})
    sections = []
    passport = [f"Карта: {name}."]
    for key, label in [('дата', 'Дата'), ('время', 'Местное время'), ('место', 'Место'),
                       ('широта', 'Широта'), ('долгота', 'Долгота'), ('гмт', 'UTC на дату рождения'),
                       ('момент_utc', 'Момент UTC' if known else 'Условный момент UTC')]:
        if key == 'время' and not known:
            passport.append('Время рождения неизвестно. Условный момент расчёта не заменяет время рождения.')
        elif birth and birth.get(key) is not None:
            passport.append(f"{label}: {birth[key]}.")
    passport.append('Дома: Плацидус.' if known else 'Дома, ASC и MC не определяются. Положение Луны и быстрых точек зависит от неизвестного часа.')
    passport.append('Числа получены расчётом. Трактовки — отдельный слой правил: основные значения планет и аспектов, '
                    'современные управители и авторские значения градусов AF. Символ градуса — его порядковый номер, '
                    'он отличается от точной координаты. Основной список содержит пять основных аспектов. '
                    'Вспомогательные углы конфигураций, если они найдены, описываются отдельно.')
    sections.append(('Основания карты', '\n\n'.join(passport)))
    for group, title in [('foundation', 'Личность, потребности и направление'),
                         ('tools', 'Способы мышления, выбора и действия'),
                         ('author', 'Авторский символический слой')]:
        if plan['order'][group]:
            intro = STYLES[plan['style']].get(group, '')
            sections.append((title, '\n\n'.join([intro] if intro else []) +
                             ('\n\n' if intro else '') + '\n\n'.join(texts[x] for x in plan['order'][group])))
    if known:
        sections.append(('Двенадцать областей жизни', '\n\n'.join(_house_texts(machine['bridge'], machine['points'], data))))
    sections.append(('Аспектный каркас — обе стороны каждой связи',
                     (STYLES[plan['style']]['aspects'] + '\n\n' if STYLES[plan['style']]['aspects'] else '') +
                     '\n\n'.join(texts[x] for x in plan['order']['aspects']) if machine['aspects'] else 'Нет аспектов в принятых орбисах.'))
    m = machine['bridge']
    blocks = [KN.баланс(m), KN.цепи_диспозиторов(m)]
    # These are machine-written blocks. Removing their technical frame doesn't rewrite facts.
    sections.append(('Общий рисунок: баланс, управление и конфигурации',
                     '\n\n'.join('\n'.join(b.splitlines()[1:]) for b in blocks if b) +
                     '\n\n' + _configuration_text(m)))
    sections.append(('Сквозной сценарий — от входа к выходу', _scenario(machine, data)))
    sections.append(('Основа прочтения',
                     'Краткая библиотека основных значений: Linda Reid, «The Planets», «The Houses», «Planetary Rulerships»; '
                     'Deborah Houlding, «The Classical Origin and Traditional Use of Aspects». Русские формулировки и их '
                     'соединение — редакционная систематизация QUANTAREON, а не цитаты авторов. '
                     'Значения градусов и дополнительных точек — авторский слой AF. '
                     'Ретроградность не означает неизбежного события; аспект сам по себе не обещает конкретного исхода.'))
    full = '\n\n'.join(title + '\n\n' + text for title, text in sections)
    report = {'version': data['version'], 'mode': mode, 'fallback_reason': reason,
              'points': len(machine['points']), 'houses': 12 if known else 0,
              'aspects': len(machine['aspects']), 'direct': sum(r['direct'] for r in machine['aspects']),
              'linked': sum(not r['direct'] for r in machine['aspects']),
              'rendered_ids': [x for ids in plan['order'].values() for x in ids]}
    return {'razdely': sections, 'tekst': full, 'razbor': full, 'gologramma': _scenario(machine, data),
            'storozh': [], 'machine_natal': report}
