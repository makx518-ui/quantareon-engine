# -*- coding: utf-8 -*-
"""
relief_zhizni.py — РЕЛЬЕФ ЖИЗНИ для натала (28.09.2026).

Перенесено из Dream Oracle: engine_astrofraktal/af_relief.py (relief, render_relief) и
quantareon_bridge.py (_hot_years_details, _receptions) — логика, веса, пороги, флаги
ЛУПА, формат строк — ОДИН В ОДИН. Там это глава VI «ХРОНИКА ЖИЗНИ» натала.

Одна разница — источник положений медленных планет. У Оракула — общий файл
slow_positions.json, посчитанный один раз с 30.01.1961 на 66 лет: у рождённых раньше
1961 года ранние годы выпадают, а с весны 2027 года хроника перестаёт доходить до
«сегодня». Здесь ряд считается под дату рождения КАЖДОГО человека тем же
Swiss Ephemeris, что считает его карту (шаг 10 дней, как у них; ~90 лет — доли секунды).

На вход — «машина» с .flat (точка → абсолютный градус) и .cusps (12 куспидов):
это объект engine/most.Мост, та же, на которой собрана полочка натала.
"""
from datetime import datetime, timedelta, timezone

# у Оракула «Узел» — истинный северный узел (true_north_lunar_node)
МЕДЛЕННЫЕ = [("Юпитер", "JUPITER"), ("Сатурн", "SATURN"), ("Уран", "URANUS"), ("Нептун", "NEPTUNE"),
             ("Плутон", "PLUTO"), ("Хирон", "CHIRON"), ("Узел", "TRUE_NODE")]
ШАГ_ДНЕЙ = 10


def ряд_медленных(рождение_utc, лет):
    """[день_от_рождения, Юпитер, Сатурн, Уран, Нептун, Плутон, Хирон, Узел] каждые 10 дней,
    в полдень UTC — как их build_cache. Возвращает (имена, строки)."""
    from engine import natal as _natal  # noqa: F401 — ставит путь к эфемеридам (в т.ч. файл Хирона)
    import swisseph as swe
    д0 = datetime(рождение_utc.year, рождение_utc.month, рождение_utc.day)
    коды = [getattr(swe, к) for _, к in МЕДЛЕННЫЕ]
    строки, дд = [], 0
    while дд <= лет * 365.25 + 40:
        т = д0 + timedelta(days=дд)
        jd = swe.julday(т.year, т.month, т.day, 12.0)
        строки.append([дд] + [round(swe.calc_ut(jd, к, swe.FLG_SWIEPH)[0][0], 3) for к in коды])
        дд += ШАГ_ДНЕЙ
    return [и for и, _ in МЕДЛЕННЫЕ], строки


def рельеф(m, d0, years, names, rows):
    """af_relief.relief — без кэша, на готовом ряду. Код расчёта не менялся."""
    wPh={"Плутон":3,"Нептун":3,"Уран":3,"Сатурн":2.5,"Хирон":2,"Узел":2,"Юпитер":1.5}
    wPl={"Плутон":2.2,"Нептун":2,"Уран":3,"Сатурн":1.5,"Хирон":1.5,"Узел":2.2,"Юпитер":2.5}
    def wT(n): return 3 if n in ("Солнце","Луна","ASC","MC") else (2 if n in ("Меркурий","Венера","Марс","Юпитер","Сатурн") else 1.5)
    H={a:0.0 for a in range(years+1)}; L={a:0.0 for a in range(years+1)}
    logH={a:[] for a in range(years+1)}; logL={a:[] for a in range(years+1)}
    for pi,pl in enumerate(names):
        ser=[(r[0],r[1+pi]) for r in rows]
        for tn,tp in m.flat.items():
            for an,ad,wh,wl in [("☌",0,3,2.4),("☍",180,2.8,0),("□",90,2.5,0),("△",120,1.4,3),("⚹",60,1.0,2.0)]:
                orbs=[(dd,abs(min((p-tp)%360,(tp-p)%360)-ad)) for dd,p in ser]
                for i in range(1,len(orbs)-1):
                    dd,o=orbs[i]
                    if o<=0.4 and o<=orbs[i-1][1] and o<=orbs[i+1][1]:
                        a=int(dd/365.25)
                        if a>years: continue
                        self_hi = 1.5 if (tn==pl and pl in("Уран","Нептун","Плутон")) else 1
                        H[a]+=wPh[pl]*wT(tn)*wh*self_hi/3; logH[a].append((wPh[pl]*wT(tn)*wh/3,f"тр.{pl}{an}{tn}"))
                        if wl and (an!="☌" or pl in("Юпитер","Узел")):
                            bl=2.2 if (tn==pl and an=="△" and pl in("Уран","Нептун","Плутон")) else 1
                            L[a]+=wPl[pl]*wT(tn)*wl*bl/3; logL[a].append((wPl[pl]*wT(tn)*wl/3,f"тр.{pl}{an}{tn}"))
    cusps=getattr(m,'cusps',None) or []
    for A,pa in m.flat.items():
        for B,pb in m.flat.items():
            if A==B: continue
            for an,ad,wh in [("☌",0,3),("☍",180,2.8),("□",90,2.5),("△",120,1.6),("⚹",60,1.2)]:
                need=(pb+ad-pa)%360
                for arc in {need,(360-need)%360}:
                    if 0<arc<years:
                        a=int(arc); v=wT(B)*1.1*(wh/3+0.5)
                        H[a]+=v; logH[a].append((v,f"дир.{A}{an}{B}"))
                        if an in ("△","⚹","☌"): L[a]+=v*0.8; logL[a].append((v*0.8,f"дир.{A}{an}{B}"))
        for h,c in enumerate(cusps,1):
            arc=(c-pa)%360
            if 0<arc<years:
                a=int(arc); H[a]+=4; logH[a].append((4,f"дир.{A}→{h}-й дом"))
    qH=sorted(H.values())[int(len(H)*0.78)]; qL=sorted(L.values())[int(len(L)*0.78)]
    qH=qH or 1e-9; qL=qL or 1e-9   # короткая жизнь (ребёнок): у Оракула деление на ноль
    lines=[]
    for a in range(0,years):
        fl=("ЛУПА!" if (H[a]>=qH and L[a]>=qL) else "ЛУПА-Т" if H[a]>=qH else "ЛУПА-С" if L[a]>=qL else "  ~  " if max(H[a]/qH,L[a]/qL)>=0.6 else "тихо ")
        top=" · ".join(x[1] for x in sorted(set(logH[a]+logL[a]),reverse=True)[:3])
        lines.append({"возраст":a,"годы":f"{d0.year+a}-{d0.year+a+1}","напряж":round(H[a],1),"свет":round(L[a],1),"флаг":fl.strip(),"киты":top})
    return lines


def render_relief(lines, name=""):
    """af_relief.render_relief — как есть."""
    L=[f"╔═══ РЕЛЬЕФ ЖИЗНИ {name} · двухканальный скан (машина: НАТАЛ → РЕЛЬЕФ → тома по флагам) ═══",
       "ВОЗР | ГОДЫ       | НАПРЯЖ | СВЕТ  | ФЛАГ    | КИТЫ ГОДА"]
    for r in lines:
        L.append(f"{r['возраст']:4} | {r['годы']} | {r['напряж']:6} | {r['свет']:5} | {r['флаг']:7} | {r['киты']}")
    L.append("ФЛАГИ: ЛУПА!=яркий в обоих каналах · ЛУПА-Т=тяжёлый · ЛУПА-С=светлый · ~=средний · тихо. Для ЛУПА-лет генерируется ПОЛНЫЙ ТОМ (ленивая подгрузка).")
    return "\n".join(L)


def детали_ярких_лет(m, d0, lines, names, rows):
    """quantareon_bridge._hot_years_details — как есть, но ряд свой (без сдвига кэша)."""
    return "\n\n".join(детали_по_годам(m, d0, lines, names, rows).values())


def детали_по_годам(m, d0, lines, names, rows):
    """То же, но по годам: {возраст: блок деталей} — чтобы хронику длинной жизни
    отдавать читателю частями."""
    cusps=getattr(m,'cusps',None) or []
    ASP=[("☌",0),("⚹",60),("□",90),("△",120),("☍",180)]
    hot=[r for r in lines if "ЛУПА" in r["флаг"]]
    out={}
    for r in hot:
        a=r["возраст"]; lo,hi=a*365.25-8, (a+1)*365.25+8
        ev=[]
        for pi,pl in enumerate(names):
            ser=[(row[0],row[1+pi]) for row in rows if lo-12<=row[0]<=hi+12]
            for tn,tp in m.flat.items():
                for an,ad in ASP:
                    orbs=[(dd,abs(min((p-tp)%360,(tp-p)%360)-ad)) for dd,p in ser]
                    for i in range(1,len(orbs)-1):
                        dd,o=orbs[i]
                        if o<=0.35 and o<=orbs[i-1][1] and o<=orbs[i+1][1] and lo<=dd<=hi:
                            y0,y1,y2=orbs[i-1][1],o,orbs[i+1][1]; den=(y0-2*y1+y2)
                            sh=0.0 if abs(den)<1e-9 else max(-1,min(1,0.5*(y0-y2)/den))
                            dt=d0+timedelta(days=dd+sh*10)
                            ev.append((dd,f"тр.{pl} {an} {tn} · {dt.strftime('%d.%m.%Y')}"))
            for hi_,c in enumerate(cusps,1):
                orbs=[(dd,min(abs((p-c)%360),abs((c-p)%360))) for dd,p in ser]
                for i in range(1,len(orbs)-1):
                    dd,o=orbs[i]
                    if o<=0.8 and o<=orbs[i-1][1] and o<=orbs[i+1][1] and lo<=dd<=hi and pl!="Юпитер":
                        dt=d0+timedelta(days=dd)
                        ev.append((dd,f"⌂ {pl} на куспиде {hi_}-го дома · {dt.strftime('%d.%m.%Y')}"))
        for A,pa in m.flat.items():
            for B,pb in m.flat.items():
                if A==B: continue
                for an,ad in ASP:
                    need=(pb+ad-pa)%360
                    for arc in {need,(360-need)%360}:
                        if a<=arc<a+1:
                            dt=d0+timedelta(days=arc*365.25)
                            ev.append((arc*365.25,f"дир.{A} {an} {B} · точная {dt.strftime('%d.%m.%Y')}"))
            for hh_,c in enumerate(cusps,1):
                arc=(c-pa)%360
                if a<=arc<a+1:
                    dt=d0+timedelta(days=arc*365.25)
                    ev.append((arc*365.25,f"⌂ дир.{A} входит в {hh_}-й дом · {dt.strftime('%d.%m.%Y')} (дом зажжён на год)"))
        ev.sort()
        ch="!" if "!" in r["флаг"] else ("Т" if "Т" in r["флаг"] else "С")
        reg={"!":"перелом двух природ","Т":"тёмный регистр (испытание)","С":"светлый регистр (подъём)"}[ch]
        out[a]=(f"── ГОД возраст {a} ({r['годы']}) · {r['флаг']} · {reg} · напряж {r['напряж']} / свет {r['свет']}\n"
                + "\n".join("   "+e[1] for e in ev[:22]))
    return out


_RULER={"Овен":"Марс","Телец":"Венера","Близнецы":"Меркурий","Рак":"Луна","Лев":"Солнце","Дева":"Меркурий",
"Весы":"Венера","Скорпион":"Плутон","Стрелец":"Юпитер","Козерог":"Сатурн","Водолей":"Уран","Рыбы":"Нептун"}
_ЗНАКИ=["Овен","Телец","Близнецы","Рак","Лев","Дева","Весы","Скорпион","Стрелец","Козерог","Водолей","Рыбы"]


def рецепции(m):
    """quantareon_bridge._receptions — как есть."""
    sign_of={n: _ЗНАКИ[int(p//30)] for n,p in m.flat.items()}
    plan=[p for p in ("Солнце","Луна","Меркурий","Венера","Марс","Юпитер","Сатурн","Уран","Нептун","Плутон") if p in sign_of]
    out=[]
    for i,a in enumerate(plan):
        for b in plan[i+1:]:
            if _RULER.get(sign_of[a])==b and _RULER.get(sign_of[b])==a:
                out.append(f"  ⇄ ВЗАИМНАЯ РЕЦЕПЦИЯ: {a} в {sign_of[a]} ↔ {b} в {sign_of[b]} — планеты в знаках друг друга: жемчужина карты, союз функций")
    return "╔═══ РЕЦЕПЦИИ ═══\n"+"\n".join(out) if out else ""


def возрастные_циклы(рождение_местное, сегодня=None):
    from engine import vozrast_cikly as В
    return В.calculate_age_cycles(рождение_местное.strftime("%d.%m.%Y"), today=сегодня).get("text_block", "")


def части_хроники(m, рождение_utc, рождение_местное=None, сегодня=None, лет_в_части=35):
    """Хроника для читателя ЧАСТЯМИ: [(с_возраста, по_возраст, текст)]. Жизнь до 35 лет —
    одна часть; длиннее — по ~35 лет, чтобы поздние годы не сжимались. Возрастные циклы
    идут в последнюю часть (там «сейчас»). Годы — от рождения до текущего +2 (как у Оракула)."""
    местное = рождение_местное or рождение_utc
    d0 = datetime(местное.year, местное.month, местное.day)
    сейчас = сегодня or datetime.now(timezone.utc).replace(tzinfo=None)
    возраст = max(0, int((сейчас - d0).days / 365.25))
    лет = min(возраст + 2, 90)
    names, rows = ряд_медленных(рождение_utc, лет)
    lines = рельеф(m, d0, лет, names, rows)
    дет = детали_по_годам(m, d0, lines, names, rows)
    циклы = возрастные_циклы(местное, сейчас.date())
    частей = max(1, -(-len(lines) // лет_в_части))
    размер = -(-len(lines) // частей)
    итог = []
    for к in range(частей):
        кусок = lines[к * размер:(к + 1) * размер]
        if not кусок:
            continue
        текст = (render_relief(кусок)
                 + "\n\n# ДЕТАЛИ ЯРКИХ ЛЕТ (машина: силы, даты, двери — основа ПОДРОБНОЙ прописи)\n"
                 + "\n\n".join(дет[r["возраст"]] for r in кусок if r["возраст"] in дет))
        if к == частей - 1 and циклы:
            текст += ("\n\n# ВОЗРАСТНЫЕ ЦИКЛЫ — ГДЕ ЧЕЛОВЕК СЕЙЧАС НА ШКАЛЕ ЖИЗНИ "
                      "(средние периоды, даты приблизительные)\n" + циклы)
        итог.append((кусок[0]["возраст"], кусок[-1]["возраст"], текст))
    return итог, возраст


def всё_для_хроники(m, рождение_utc, рождение_местное=None, сегодня=None):
    """Рельеф жизни + детали ярких лет + возрастные циклы — одним текстом для главы ХРОНИКА.
    Годы — от рождения до текущего (+2, как у Оракула; не больше 90)."""
    местное = рождение_местное or рождение_utc
    d0 = datetime(местное.year, местное.month, местное.day)
    сейчас = сегодня or datetime.now(timezone.utc).replace(tzinfo=None)
    возраст = max(0, int((сейчас - d0).days / 365.25))
    лет = min(возраст + 2, 90)
    names, rows = ряд_медленных(рождение_utc, лет)
    lines = рельеф(m, d0, лет, names, rows)
    текст = (render_relief(lines)
             + "\n\n# ДЕТАЛИ ЯРКИХ ЛЕТ (машина: силы, даты, двери — основа ПОДРОБНОЙ прописи)\n"
             + детали_ярких_лет(m, d0, lines, names, rows))
    циклы = возрастные_циклы(местное, сейчас.date())
    if циклы:
        текст += "\n\n# ВОЗРАСТНЫЕ ЦИКЛЫ — ГДЕ ЧЕЛОВЕК СЕЙЧАС НА ШКАЛЕ ЖИЗНИ (средние периоды, даты приблизительные)\n" + циклы
    return текст, lines, возраст
