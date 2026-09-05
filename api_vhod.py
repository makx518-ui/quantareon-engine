# -*- coding: utf-8 -*-
"""
ТОЧКА ВХОДА ДЛЯ САЙТА — окно шлёт данные, машина отдаёт раскладку.

Его порядок 04.09: сперва доделать машину, потом деплой.
Пока лежит в коде готовым.

    POST /api/raschet
    {
      "zakaz": "natal" | "tranzity" | "solyar" | "den" | "sinastriya",
      "data": "30.01.1961", "vremya": "20:56:40" | null,
      "shirota": 54.42985, "dolgota": 70.34136, "gmt": 6,
      "mesto": "с. Советское", "imya": "Влад",
      "god_solyara": 2027 | null,
      "seychas": {"shirota": 56.852, "dolgota": 53.199, "gmt": 4, "mesto": "Ижевск"},
      "partner": { ... те же поля ... }        # только для синастрии
    }
"""
from datetime import datetime, timezone

from engine import dispetcher as D

ЗАКАЗЫ = {"natal": "натал", "tranzity": "ситуация",
          "solyar": "соляр", "den": "день", "sinastriya": "синастрия"}


def _разобрать_дату(строка):
    """'30.01.1961' → (1961, 1, 30)"""
    д, м, г = строка.replace("-", ".").replace("/", ".").split(".")
    return int(г), int(м), int(д)


def _разобрать_время(строка):
    """'20:56:40' или '20:56' или пусто → (час, минута, секунда) или None"""
    if not строка or not строка.strip():
        return None
    части = строка.strip().split(":")
    ч = int(части[0])
    м = int(части[1]) if len(части) > 1 else 0
    с = int(части[2]) if len(части) > 2 else 0
    return ч, м, с


def расчёт(запрос):
    """Главная функция для сайта. Отдаёт словарь с текстом раскладки."""
    заказ = ЗАКАЗЫ.get(запрос.get("zakaz", "natal"), "натал")
    год, месяц, день = _разобрать_дату(запрос["data"])
    время = _разобрать_время(запрос.get("vremya"))
    сейчас = запрос.get("seychas") or {}

    общие = dict(
        год=год, месяц=месяц, день=день,
        широта=float(запрос["shirota"]), долгота=float(запрос["dolgota"]),
        пояс=float(запрос.get("gmt", 0)),
        имя=запрос.get("imya") or "человек",
        место=запрос.get("mesto") or "",
        широта_сейчас=float(сейчас.get("shirota", запрос["shirota"])),
        долгота_сейчас=float(сейчас.get("dolgota", запрос["dolgota"])),
        пояс_сейчас=float(сейчас.get("gmt", запрос.get("gmt", 0))),
    )
    if время:
        общие.update(час=время[0], минута=время[1], секунда=время[2])
    if запрос.get("god_solyara"):
        общие["год_соляра"] = int(запрос["god_solyara"])

    if заказ == "синастрия":
        return _синастрия(запрос, общие)

    итог = D.разобрать(заказ=заказ, **общие)

    # ⚠️ 05.09: каждая карта ложится в архив под именем клиента,
    # со всей кухней расклада — её потом достаёт ученик.
    путь_архива = ""
    try:
        from engine import arhiv
        путь_архива = arhiv.положить_кухню(
            имя_клиента=запрос.get("imya") or "без имени",
            заказ=запрос.get("zakaz", "natal"),
            итог=итог,
            данные_рождения={
                "дата": запрос["data"], "время": запрос.get("vremya") or "не указано",
                "место": запрос.get("mesto") or "", "гмт": запрос.get("gmt"),
                "широта": запрос["shirota"], "долгота": запрос["dolgota"],
            },
            пояс_часов=float(сейчас.get("gmt", запрос.get("gmt", 0))))
        arhiv._в_дневник(запрос.get("imya") or "без имени", путь_архива,
                         datetime.now(timezone.utc))
    except Exception:
        pass

    ответ = {
        "zakaz": запрос.get("zakaz"),
        "vremya_izvestno": итог["время_известно"],
        "sloy1": итог.get("слой1", ""),
        "sloy2": итог.get("слой2", ""),
        "sloy3": итог.get("слой3", ""),
        "shapka": ("Время рождения не указано — карта прочитана от Солнца."
                   if not итог["время_известно"] else ""),
        "arhiv": путь_архива,
    }
    ответ["polnyy_tekst"] = "\n\n".join(
        т for т in (ответ["sloy1"], ответ["sloy2"], ответ["sloy3"]) if т)
    return ответ


def _синастрия(запрос, общие):
    """Две карты. Кода расчёта пока нет — отдаём обе раскладки."""
    п = запрос.get("partner") or {}
    if not п:
        return {"oshibka": "для синастрии нужны данные партнёра"}
    мой = D.разобрать(заказ="натал", **общие)
    гп, мп, дп = _разобрать_дату(п["data"])
    вп = _разобрать_время(п.get("vremya"))
    его = dict(год=гп, месяц=мп, день=дп,
               широта=float(п["shirota"]), долгота=float(п["dolgota"]),
               пояс=float(п.get("gmt", 0)),
               имя=п.get("imya") or "партнёр", место=п.get("mesto") or "")
    if вп:
        его.update(час=вп[0], минута=вп[1], секунда=вп[2])
    партнёр = D.разобрать(заказ="натал", **его)
    путь_архива = ""
    try:
        from engine import arhiv
        путь_архива = arhiv.сохранить_синастрию(
            общие.get("имя", "первый"), его.get("имя", "второй"),
            {"первый": мой, "второй": партнёр,
             "встреча": "(расчёт встречи — см. слой синастрии)"},
            {"дата": запрос["data"], "время": запрос.get("vremya") or "не указано"},
            {"дата": п["data"], "время": п.get("vremya") or "не указано"})
    except Exception:
        pass
    return {
        "zakaz": "sinastriya",
        "arhiv": путь_архива,
        "sloy1": мой["слой1"],
        "sloy1_partner": партнёр["слой1"],
        "vstrecha": "(расчёт встречи двух карт — в работе)",
        "polnyy_tekst": мой["слой1"] + "\n\n" + партнёр["слой1"],
    }


def карта_файлом(запрос, трактовка_по_разделам):
    """Отдаёт клиенту готовый HTML-файл с трактовкой.

    Его правило 05.09: карта и кухня — РАЗДЕЛЬНО. Здесь только текст,
    ни одного термина. Кухня уже лежит в архиве для ученика.

    трактовка_по_разделам: [("Кто ты", "текст..."), ("Что сейчас", "...")]
    """
    from engine import karta_html, arhiv
    имя = запрос.get("imya") or "без имени"
    заказ = запрос.get("zakaz", "natal")
    сейчас = запрос.get("seychas") or {}
    пояс = float(сейчас.get("gmt", запрос.get("gmt", 0)))
    без_времени = not (запрос.get("vremya") or "").strip()

    html = karta_html.карта_клиенту(
        трактовка_по_разделам, имя,
        заказ=("kosmogramma" if заказ == "natal" and без_времени else заказ),
        данные_рождения={"дата": запрос.get("data"),
                         "время": запрос.get("vremya"),
                         "место": запрос.get("mesto")},
        без_времени=без_времени, пояс_часов=пояс)
    путь = arhiv.положить_карту(имя, заказ, html, пояс_часов=пояс)
    return {"html": html, "fayl": путь,
            "imya_fayla": f"{имя} · {karta_html.ЗАГОЛОВКИ.get(заказ, ('карта',))[0].lower()}.html"}


# ═══════════════════════════════════════════════════════════════════
#  ИСТОРИЯ КАРТ — список для страницы, как в Оракуле
# ═══════════════════════════════════════════════════════════════════

ЗНАЧКИ = {"natal": "☉", "tranzity": "⟳", "solyar": "☀",
          "den": "🕐", "sinastriya": "💞"}
НАЗВАНИЯ = {"natal": "НАТАЛ", "tranzity": "ТРАНЗИТЫ", "solyar": "СОЛЯР",
            "den": "ДЕНЬ", "sinastriya": "СИНАСТРИЯ"}


def история():
    """Все расчёты — пара из карты и кухни на каждый.
    Его правило 05.09: одна карточка на расчёт, внутри две ссылки."""
    import os, json, re
    from engine import arhiv
    расчёты = {}
    if not os.path.isdir(arhiv.АРХИВ):
        return {"raschety": []}
    for клиент in os.listdir(arhiv.АРХИВ):
        корень = os.path.join(arhiv.АРХИВ, клиент)
        if not os.path.isdir(корень):
            continue
        # карты клиента
        пк = os.path.join(корень, "карты")
        if os.path.isdir(пк):
            for ф in os.listdir(пк):
                м = re.match(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2})_(\w+)\.html", ф)
                if not м:
                    continue
                ключ = f"{клиент}|{м.group(1)}"
                з = расчёты.setdefault(ключ, {"imya": клиент.replace("_", " "),
                                              "id": ключ, "zakaz_kod": м.group(2)})
                з["fayl_karty"] = os.path.relpath(os.path.join(пк, ф), arhiv.КОРЕНЬ)
        # кухня
        пх = os.path.join(корень, "кухня")
        if os.path.isdir(пх):
            for ф in os.listdir(пх):
                м = re.match(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2})\.json", ф)
                if not м:
                    continue
                ключ = f"{клиент}|{м.group(1)}"
                з = расчёты.setdefault(ключ, {"imya": клиент.replace("_", " "), "id": ключ})
                путь = os.path.join(пх, ф)
                з["fayl_kuhni"] = os.path.relpath(путь, arhiv.КОРЕНЬ)
                try:
                    д = json.load(open(путь, encoding="utf-8"))
                    з["zakaz_kod"] = з.get("zakaz_kod") or д.get("заказ", "natal")
                    з["rozhdenie"] = д.get("данные_рождения", {}).get("дата", "")
                except Exception:
                    pass
    итог = []
    for ключ, з in расчёты.items():
        когда = ключ.split("|")[1]
        г, м_, д_, ч, мин = когда[:4], когда[5:7], когда[8:10], когда[11:13], когда[14:16]
        код = з.get("zakaz_kod", "natal")
        з["data"] = f"{д_}.{м_}.{г} {ч}:{мин}"
        з["zakaz"] = НАЗВАНИЯ.get(код, код.upper())
        з["znachok"] = ЗНАЧКИ.get(код, "✦")
        з.setdefault("rozhdenie", "")
        з.setdefault("fayl_karty", "")
        з.setdefault("fayl_kuhni", "")
        з["_sort"] = когда
        итог.append(з)
    итог.sort(key=lambda x: x["_sort"], reverse=True)
    for з in итог:
        з.pop("_sort", None)
    return {"raschety": итог}


def отдать(отн_путь):
    """Файл по относительному пути — карта или кухня."""
    import os
    from engine import arhiv
    путь = os.path.normpath(os.path.join(arhiv.КОРЕНЬ, отн_путь))
    if not путь.startswith(os.path.normpath(arhiv.КОРЕНЬ)) or not os.path.exists(путь):
        return None
    return open(путь, encoding="utf-8").read()


def удалить_расчёт(ид):
    """Убирает расчёт целиком — и карту, и кухню."""
    import os, re
    from engine import arhiv
    if "|" not in ид:
        return {"udaleno": 0}
    клиент, когда = ид.split("|", 1)
    убрано = 0
    for под, конец in (("карты", ".html"), ("кухня", ".json")):
        папка = os.path.join(arhiv.АРХИВ, клиент, под)
        if not os.path.isdir(папка):
            continue
        for ф in os.listdir(папка):
            if ф.startswith(когда) and ф.endswith(конец):
                os.remove(os.path.join(папка, ф))
                убрано += 1
    return {"udaleno": убрано}


def очистить_историю():
    """Всё под корень. Спрашивается дважды на странице."""
    import shutil, os
    from engine import arhiv
    if os.path.isdir(arhiv.АРХИВ):
        shutil.rmtree(arhiv.АРХИВ)
    return {"ochischeno": True}
