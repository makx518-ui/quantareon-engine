# -*- coding: utf-8 -*-
"""
Машина-адаптер для WheelEngine (восстановлена по интерфейсу astrofraktal_wheel):
даёт .flat (имя_ru -> abs_pos натала) и .polochka(имя, abs) -> дом/управитель/диспозитор.
Натал: Kerykeion (Placidus, True Node, Mean Lilith) + Белая Луна по формуле Селены
(ref 1990-01-01 = 88.05°, 0.140804°/день — сверено с проектной compute_selena).
"""
from datetime import datetime, timezone
from kerykeion import AstrologicalSubjectFactory

SIGN=["Овен","Телец","Близнецы","Рак","Лев","Дева","Весы","Скорпион","Стрелец","Козерог","Водолей","Рыбы"]
RULER=["Марс","Венера","Меркурий","Луна","Солнце","Меркурий","Венера","Плутон","Юпитер","Сатурн","Уран","Нептун"]

RU = {"sun":"Солнце","moon":"Луна","mercury":"Меркурий","venus":"Венера","mars":"Марс",
      "jupiter":"Юпитер","saturn":"Сатурн","uranus":"Уран","neptune":"Нептун","pluto":"Плутон",
      "chiron":"Хирон","true_north_lunar_node":"Сев.Узел","mean_lilith":"Чёрная Луна"}

SELENA_REF = datetime(1990,1,1,tzinfo=timezone.utc); SELENA_REF_POS=88.05; SELENA_SPEED=0.140804

def selena_abs(dt_utc):
    return (SELENA_REF_POS + (dt_utc-SELENA_REF).total_seconds()/86400.0*SELENA_SPEED) % 360.0

class Machine:
    def __init__(s, name, y,mo,d,hh,mi, lat,lng,tz_str, birth_utc, ss=0):
        s.subj = AstrologicalSubjectFactory.from_birth_data(
            name, y,mo,d,hh,mi, seconds=ss, lat=lat,lng=lng,tz_str=tz_str, online=False)
        s.flat={}
        for attr,ru in RU.items():
            o=getattr(s.subj,attr,None)
            if o is not None: s.flat[ru]=o.abs_pos
        s.flat["ASC"]=s.subj.ascendant.abs_pos
        s.flat["MC"]=s.subj.medium_coeli.abs_pos
        s.flat["Белая Луна"]=selena_abs(birth_utc)
        s.flat["Юж.Узел"]=(s.flat["Сев.Узел"]+180.0)%360.0
        hs=["first","second","third","fourth","fifth","sixth","seventh","eighth","ninth","tenth","eleventh","twelfth"]
        s.cusps=[getattr(s.subj,f"{h}_house").abs_pos for h in hs]

    def house_of(s, ap):
        for i in range(12):
            a=s.cusps[i]; b=s.cusps[(i+1)%12]
            if a<=b:
                if a<=ap<b: return i+1
            else:
                if ap>=a or ap<b: return i+1
        return 12

    def polochka(s, name, ap):
        h=s.house_of(ap)
        return {"дом":h,
                "управитель_дома":RULER[int(s.cusps[h-1]//30)],
                "диспозитор":RULER[int(ap//30)%12]}
