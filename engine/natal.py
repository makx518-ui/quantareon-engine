# -*- coding: utf-8 -*-
"""Расчёт точек космограммы — восстановлено после сброса контейнера."""
import swisseph as swe

ТОЧКИ = [(swe.SUN,"Солнце"),(swe.MOON,"Луна"),(swe.MERCURY,"Меркурий"),(swe.VENUS,"Венера"),
         (swe.MARS,"Марс"),(swe.JUPITER,"Юпитер"),(swe.SATURN,"Сатурн"),(swe.URANUS,"Уран"),
         (swe.NEPTUNE,"Нептун"),(swe.PLUTO,"Плутон"),(swe.CHIRON,"Хирон"),
         (swe.MEAN_APOG,"Лилит"),(swe.TRUE_NODE,"Сев.Узел")]

def _селена(jd):
    """Белая Луна. Опора и ход выверены 05.09 по двум сверкам:
    ZET на дату рождения (10°43'00" Тельца) и его сайт на 05.09.2026
    (24°11'39" Девы). Обе сошлись до нуля секунд."""
    return (87.9580 + (jd - 2447892.5) * 0.1408056) % 360

def calculate_natal(year, month, day, hour, minute, second=0, timezone=0.0,
                    latitude=0.0, longitude=0.0):
    ч = hour + minute/60 + second/3600 - timezone
    jd = swe.julday(year, month, day, ч)
    итог = {}
    for pid, имя in ТОЧКИ:
        # ⚠️ 04.09: без FLG_SPEED движок возвращает скорость нулём —
        # и все точки выглядели стоянками. Скорость надо запрашивать явно.
        флаги = swe.FLG_SWIEPH | swe.FLG_SPEED
        try:
            поз = swe.calc_ut(jd, pid, флаги)[0]
        except Exception:
            try:
                поз = swe.calc_ut(jd, pid, swe.FLG_MOSEPH | swe.FLG_SPEED)[0]
            except Exception:
                continue
        # ⚠️ стоянка определяется НЕ порогом (для Нептуна 0.007°/сут это
        # обычный ход), а фактом разворота: движок сам покажет смену знака.
        # ⚠️ узлы и Лилит — точки вычисляемые, у них знак скорости пляшет
        # по природе. Разворотом это не считается.
        стоянка = False
        if имя in ("Сев.Узел", "Юж.Узел", "Лилит", "Селена"):
            итог[имя] = {"abs_degree": поз[0] % 360, "speed": поз[3],
                         "retrograde": поз[3] < 0, "стоянка": False}
            continue
        try:
            до = swe.calc_ut(jd - 7, pid, флаги)[0][3]
            после = swe.calc_ut(jd + 7, pid, флаги)[0][3]
            стоянка = (до * после < 0) or (до * поз[3] < 0) or (поз[3] * после < 0)
        except Exception:
            pass
        итог[имя] = {"abs_degree": поз[0] % 360, "speed": поз[3],
                     "retrograde": поз[3] < 0, "стоянка": стоянка}
    итог["Юж.Узел"] = {"abs_degree": (итог["Сев.Узел"]["abs_degree"] + 180) % 360,
                       "speed": итог["Сев.Узел"]["speed"],
                       "retrograde": итог["Сев.Узел"]["retrograde"]}
    итог["Селена"] = {"abs_degree": _селена(jd), "speed": 0.1408056, "retrograde": False}
    return {"planets": итог, "jd": jd}
