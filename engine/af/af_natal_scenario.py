# -*- coding: utf-8 -*-
"""
СЦЕНАРИЙ-СКРИПТ НАТАЛА (его порядок): машина выдаёт натал чётко, как ядро-потенциал,
классика, но с грамотно вплетёнными градусами; ИЗНУТРИ НАРУЖУ; управители домов;
аспекты — на каждом конце: планета·знак·дом·градус·код; что аспект несёт.
Затем (отдельным прибором) — разворот созревания ядра по Колесу.
"""
from collections import Counter
import kod360, micro_cascade
from af_portret import all_portraits, portrait_line, CHAR, SIGN, RULER

NAT={"соединение":"СЛИЯНИЕ — силы срастаются в одну","секстиль":"ВОЗМОЖНОСТЬ — открытая дверь",
     "квадрат":"ЗАДАЧА — напряжение, требующее работы","трин":"ДАР — лёгкий поток",
     "оппозиция":"ОСЬ — качели к осознанию"}
ASP=[("соединение",0,6),("оппозиция",180,6),("трин",120,5),("квадрат",90,5),("секстиль",60,4)]
SLOI=[("ЯДРО — кто он (дух · душа · зачем пришёл)",["Солнце","Луна","Сев.Узел","Юж.Узел"]),
      ("ОСИ — личность и цель",["ASC","MC"]),
      ("КОНТУР ЛИЧНОСТИ — ум · любовь · воля",["Меркурий","Венера","Марс"]),
      ("СОЦИАЛЬНЫЕ — рост · форма",["Юпитер","Сатурн"]),
      ("ВЫСШИЕ — прорыв · туман · глубина · рана",["Уран","Нептун","Плутон","Хирон"]),
      ("КАРМИКА-ТОЧКИ — тень · благодать",["Чёрная Луна","Белая Луна"])]

def natal_aspects(flat):
    out=[]; names=list(flat)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            if {a,b}=={"Сев.Узел","Юж.Узел"}: continue
            d=abs(flat[a]-flat[b])%360; d=min(d,360-d)
            for an,ad,orb in ASP:
                if abs(d-ad)<=orb: out.append((an,round(abs(d-ad),2),a,b)); break
    return sorted(out,key=lambda x:x[1])

def _end(m,name):
    ap=m.flat[name]; c=kod360.code_by_abs(ap)
    return f"{name} ({CHAR.get(name,name)}) — {SIGN[int(ap//30)]} {int(ap%30)+1}°, дом {m.house_of(ap)}, [{c['tag']}]"

def fractal4(name, ap):
    r=micro_cascade.cascade_from_absolute(ap,4)
    lv=[f"{SIGN[int(ap//30)]} {int(ap%30)+1}° [{kod360.code_by_abs(ap)['tag']}]"]
    for x in r['cascade'][:3]:
        try: tag=kod360.load()[(x['sign_index']+1 if 'sign_index' in x else 1, x['sabian'])]['tag']
        except Exception: tag='—'
        lv.append(f"{x['sign_name']} {x['sabian']}° [{tag}]")
    return f"{name}: " + " → ".join(lv)

def render_natal(m):
    P=all_portraits(m); L=["█"*70,"█ НАТАЛЬНЫЙ РАСКЛАД · ядро-потенциал (изнутри наружу, градусы вплетены)","█"*70]
    for title,names in SLOI:
        L.append(f"\n╔══ {title} ══")
        for n in names:
            if n in P and P[n]: L.append("  "+portrait_line(P[n]))
    L.append("\n╔══ УПРАВИТЕЛИ ДОМОВ ══")
    for h in range(1,13):
        r=RULER[int(m.cusps[h-1]//30)]
        L.append(f"  дом {h:>2} ({SIGN[int(m.cusps[h-1]//30)]} на куспиде) → управитель {r}: стоит в {SIGN[int(m.flat[r]//30)]}, дом {m.house_of(m.flat[r])}")
    L.append("\n╔══ АСПЕКТЫ (на каждом конце: планета·знак·дом·градус·код; что несёт) ══")
    for an,orb,a,b in natal_aspects(m.flat):
        L.append(f"\n  ▶ {a} {an} {b} · орб {orb}°")
        L.append(f"     {_end(m,a)}")
        L.append(f"     {_end(m,b)}")
        L.append(f"     НЕСЁТ: {NAT[an]}: «{CHAR.get(a,a).split(',')[0]}» ↔ «{CHAR.get(b,b).split(',')[0]}»")
    L.append("\n╔══ ФРАКТАЛЫ 4 УРОВНЯ (светила и углы) ══")
    for n in ["Солнце","Луна","ASC","MC"]:
        L.append("  "+fractal4(n, m.flat[n]))
    L.append("\n╔══ СИНТЕЗ-ПОЛОЧКА (машинные факты для истории ИИ) ══")
    el=Counter(); wet={"Рак","Скорпион","Рыбы"}
    for n,ap in m.flat.items(): el.update([SIGN[int(ap//30)]])
    voda=sum(v for k,v in el.items() if k in wet)
    L.append(f"  точек в воде: {voda} из {len(m.flat)}; знаки-лидеры: {', '.join(f'{k}×{v}' for k,v in el.most_common(3))}")
    cores=Counter(micro_cascade.cascade_from_absolute(ap,1)['cascade'][0]['sabian'] for ap in m.flat.values())
    L.append(f"  ИИ читает сверху вниз и пишет ФИЛЬМ: рассказ души + разворот (эталоны: rasskaz_dushi / traktovka_natal_etalon)")
    return "\n".join(L)
