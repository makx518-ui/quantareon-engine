"""Self-contained chart and factual positions from the calculated natal snapshot."""
from html import escape
from math import cos, sin, radians, isfinite

SIGNS = ['Овен','Телец','Близнецы','Рак','Лев','Дева','Весы','Скорпион','Стрелец','Козерог','Водолей','Рыбы']
ZODIAC = '♈♉♊♋♌♍♎♏♐♑♒♓'
GLYPHS = dict(zip(['Солнце','Луна','Меркурий','Венера','Марс','Юпитер','Сатурн','Уран','Нептун','Плутон','Сев.Узел','Юж.Узел','Лилит','Хирон','Селена'], ['☉','☽','☿','♀','♂','♃','♄','♅','♆','♇','☊','☋','⚸','⚷','⚜']))
GLYPHS.update({'Прозерпина': 'Pz', 'Приап': 'Pr'})
GLYPHS.update({'Фортуна': '⊗', 'Вертекс': 'Vx'})

def position(degree):
    degree = float(degree) % 360
    seconds = round(degree * 3600) % (360 * 3600)
    sign, remainder = divmod(seconds, 30 * 3600)
    d, remainder = divmod(remainder, 3600)
    m, s = divmod(remainder, 60)
    return f'{SIGNS[sign]} {d}°{m:02d}′{s:02d}″'

def house(degree, cusps):
    for i, start in enumerate(cusps):
        if (degree-start) % 360 < (cusps[(i+1)%12]-start) % 360:
            return i+1
    raise ValueError('Не удалось определить дом')

def render_chart(snapshot, birth):
    points = snapshot['tochki']
    known = bool(snapshot.get('vremya_izvestno'))
    # Fortune and Vertex depend on the birth angles; a conditional solar time
    # cannot establish them for a person whose birth time is unknown.
    if not known:
        points = {name:point for name,point in points.items() if name not in ('Фортуна','Вертекс')}
    cusps = snapshot.get('kuspidy') if known else None
    if known and (not cusps or len(cusps) != 12):
        raise ValueError('Для карты нужны 12 куспидов')
    if cusps:
        cusps = [float(value) % 360 for value in cusps]
        if not all(isfinite(value) for value in cusps):
            raise ValueError('Некорректный куспид')
        widths = [(cusps[(i+1)%12]-start)%360 for i,start in enumerate(cusps)]
        if min(widths) <= 0 or abs(sum(widths)-360) > .00001:
            raise ValueError('Нарушен порядок куспидов')
    for point in points.values():
        if not isfinite(float(point['градус'])):
            raise ValueError('Некорректная долгота планеты')
    asc = float(cusps[0]) if cusps else 0
    def xy(degree, radius):
        angle = radians(180+asc-degree)
        return 400+radius*cos(angle), 400+radius*sin(angle)
    def line(degree, r1, r2, color='#67708d', width=1):
        x1,y1=xy(degree,r1); x2,y2=xy(degree,r2)
        return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}"/>'
    def label(degree,radius,text,color='#c9c7e5',size=18):
        x,y=xy(degree,radius)
        return f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" dominant-baseline="middle" fill="{color}" font-size="{size}">{escape(str(text))}</text>'
    title = 'Натальная карта: знаки, планеты и дома' if known else 'Космограмма: знаки и планеты без домов'
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" role="img" aria-labelledby="natal-chart-title"><title id="natal-chart-title">{title}</title><rect width="800" height="800" rx="18" fill="#101729"/>']
    for radius in [160,285,340]:
        svg.append(f'<circle cx="400" cy="400" r="{radius}" fill="none" stroke="#424c69"/>')
    for d in range(360):
        svg.append(line(d,334 if d%5 else 328,340))
    for i in range(12):
        svg += [line(i*30,285,340),label(i*30+15,312,ZODIAC[i]+'\ufe0e',['#ff80b5','#efc477','#68c9ee','#a99aff'][i%4],36)]
    if cusps:
        for i,start in enumerate(cusps):
            angular = i in (0,3,6,9)
            svg.append(line(start,160,340,'#e9bd55' if angular else '#59647d',2 if angular else 1))
            svg.append(label(start+(cusps[(i+1)%12]-start)%360/2,270,i+1,size=15))
            svg.append(label(start,365,position(start).split(' ',1)[1],size=11))
            if angular:
                svg.append(label(start,130,{0:'ASC',3:'IC',6:'DSC',9:'MC'}[i],'#f4c85d',20))
    # Aspect list supplied by the same engine; no aspects inferred by the language model.
    coordinates = {name: p['градус'] for name, p in points.items()}
    coordinates.update({'Чёрная Луна': coordinates.get('Лилит'), 'Белая Луна': coordinates.get('Селена')})
    if cusps:
        coordinates.update({'ASC': cusps[0], 'MC': cusps[9]})
    for aspect in snapshot.get('aspekty', []):
        # New natal list draws every direct adopted aspect. Older callers retain
        # the exact-only convention; propagated links are explained in text.
        if not aspect.get('прямой', aspect.get('точный', False)):
            continue
        a,b=aspect['а'],aspect['б']
        if coordinates.get(a) is None or coordinates.get(b) is None:
            continue
        x1,y1=xy(coordinates[a],160); x2,y2=xy(coordinates[b],160)
        color='#f46a85' if aspect['аспект'] in ('квадрат','оппозиция') else '#40cab7'
        svg.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" opacity=".65"/>')
    rows=[]
    placed=[]
    for name,point in points.items():
        if name == 'ТЖ':
            continue  # current age point is not a birth planet
        degree=float(point['градус'])%360
        # Separate nearby symbols radially while retaining their exact longitude.
        radius=225
        for previous in placed:
            if min(abs(degree-previous),360-abs(degree-previous))<8:
                radius-=24
        radius=max(105,radius); placed.append(degree)
        symbol=GLYPHS.get(name,name[:2])
        svg += [line(degree,285,294,'#68c9ee'),label(degree,radius,symbol,'#d1b5fa',25),label(degree,radius-17,'R' if point.get('ретро') else '',size=10)]
        rows.append(f'<tr><td>{escape(symbol)} {escape(name)}</td><td>{position(degree)}</td><td>{house(degree,cusps) if cusps else "—"}</td><td>{"R" if point.get("ретро") else "—"}</td></tr>')
    svg.append('</svg>')
    if cusps:
        for key,index in [('ASC',0),('MC',9),('DSC',6),('IC',3)]:
            rows.append(f'<tr><td>{key}</td><td>{position(cusps[index])}</td><td>—</td><td>—</td></tr>')
    metadata=[]
    for key,title in [('дата','Дата рождения'),('время','Местное время'),('место','Место'),('широта','Широта'),('долгота','Долгота'),('гмт','Смещение UTC на дату рождения')]:
        value=birth.get(key)
        if key=='время' and not known:
            value='не указано'
        if key=='гмт' and value is not None:
            value=f'{float(value):+g} ч'
        metadata.append(f'<p><b>{title}:</b> {escape(str(value if value is not None else "не указано"))}</p>')
    utc=snapshot.get('rozhdenie')
    if utc:
        metadata.append(f'<p><b>{"Момент UTC" if known else "Условный момент расчёта UTC"}:</b> {escape(utc.isoformat() if hasattr(utc,"isoformat") else str(utc))}</p>')
    metadata.append(f'<p><b>Система домов:</b> {"Плацидус" if cusps else "не используется — время неизвестно"}</p>')
    note='' if known else '<p>Время рождения неизвестно: условная космограмма от Солнца. Дома и углы не показаны.</p>'
    heading = 'Натальная карта и положения планет' if known else 'Космограмма и положения планет'
    aspect_note = ('Линии — прямые аспекты в принятых орбисах натала; связи через соединения описаны в тексте.'
                   if any('прямой' in a for a in snapshot.get('aspekty', [])) else
                   'Линии — точные аспекты по правилам расчёта.')
    return f'<section class="razdel natal-visual" id="natal-facts"><h2>{heading}</h2>'+''.join(metadata)+note+''.join(svg)+f'<p>R — ретроградное движение. {aspect_note} Красные — квадрат и оппозиция, зелёные — остальные. Положения построены из числового расчёта.</p><div class="natal-table"><table><thead><tr><th>Планета / точка</th><th>Знак и положение</th><th>Дом</th><th>Движение</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>'

STYLE = '.natal-visual svg{display:block;width:100%;height:auto;margin:24px 0}.natal-table{overflow-x:auto}.natal-table table{width:100%;border-collapse:collapse;font-size:15px}.natal-table th,.natal-table td{text-align:left;padding:9px;border-bottom:1px solid #424c69;white-space:nowrap}.natal-visual p{font-size:14px}@media print{.natal-visual svg{max-height:170mm}.natal-table{overflow:visible}}'
