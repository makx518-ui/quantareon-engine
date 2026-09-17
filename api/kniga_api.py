"""
КНИГА ДНЕЙ — адреса для сайта (16.09.2026). Подключается к api/main.py роутером.

POST /api/kniga/vydat     {klyuch_hozyaina, pochta, tarif: den|shiv, dney, lang}
                          — хозяин (пока) или оплата (потом) выдаёт ключ; письмо с ключом на почту
POST /api/kniga/stranica  {klyuch, iso, lat, lon, tz, muhurta, iching, lang}
                          — страница на сегодня: первый день открывает корень (секунда витрины),
                            дальше — продолжение; готовую отдаёт сразу, иначе ставит в фон → nomer
GET  /api/kniga/status?klyuch      — что с ключом: жив ли, какая страница сегодня, какие есть
GET  /api/kniga/fayl?klyuch&n      — HTML страницы n (только по ключу)
Статус фоновой задачи — общий с картой дня: GET /api/karta-dnya/status?nomer=…

Открыто без пароля движка: наружу уходит только то, что принадлежит ключу.
"""
import os
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse

роутер = APIRouter()
ПАРОЛЬ = os.environ.get("QUANTAREON_PASSWORD", "")
ЗАДАЧИ = None   # словарь задач карты дня из main.py — подставляется при подключении


def _ключ(з):
    return str(з.get("klyuch") or "").strip().upper()


@роутер.post("/api/kniga/vydat")
async def vydat(request: Request):
    from engine import kniga as K
    try:
        з = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    if not ПАРОЛЬ or str(з.get("klyuch_hozyaina") or "") != ПАРОЛЬ:
        return JSONResponse({"ok": False, "reason": "locked"}, status_code=403)
    зап = K.выдать(з.get("pochta") or "", з.get("tarif") or "den", int(з.get("dney") or 1), з.get("lang") or "ru")
    ушло = письмо_с_ключом(зап)
    return {"ok": True, "klyuch": зап["ключ"], "tarif": зап["тариф"], "dney": зап["дней"], "pismo": ушло}


def письмо_с_ключом(зап):
    """17.09 · письмо с ключом — одно на кабинет и на оплату. True — ушло."""
    if not зап.get("почта"):
        return False
    try:
        import pochta as П
        ру = зап["lang"] == "ru"
        тема = "Ваш ключ Квантареона" if ру else "Your Quantareon key"
        текст = (f"Ваш ключ: {зап['ключ']}\n\nВведите его на странице quantareon.com/razbor-ru — и Квантареон "
                 f"начнёт работу над {'книгой дней' if зап['тариф']=='shiv' else 'полным разбором дня'}."
                 f"{' Срок книги — ' + str(зап['дней']) + ' дн.' if зап['тариф']=='shiv' else ''}\n\nХраните ключ: он ваш вход."
                 if ру else
                 f"Your key: {зап['ключ']}\n\nEnter it at quantareon.com/razbor — and Quantareon will start "
                 f"{'your book of days' if зап['тариф']=='shiv' else 'the full reading of the day'}."
                 f"{' The book lasts ' + str(зап['дней']) + ' days.' if зап['тариф']=='shiv' else ''}\n\nKeep the key: it is your entrance.")
        return П.отправить_текст(зап["почта"], тема, текст)
    except Exception as e:
        print(f"книга: письмо с ключом не ушло: {e}")
        return False


@роутер.post("/api/kniga/udalit")
async def udalit(request: Request):
    """16.09 · корзинка на странице покупателей: убрать книгу со всеми её страницами.
    Только из кабинета — адрес закрыт паролем движка (в списке открытых его нет)."""
    from engine import kniga as K, arhiv as A
    try:
        з = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    ключ = _ключ(з)
    if not K.ВИД_КЛЮЧА.match(ключ):
        return JSONResponse({"ok": False, "reason": "bad_key"}, status_code=400)
    убрано = 0
    for путь in A.перечислить(f"{A.АРХИВ}/{ключ}/"):
        if A._убрать(путь):
            убрано += 1
    A._убрать(K._путь(ключ))
    return {"ok": True, "udaleno": убрано}


@роутер.get("/api/kniga/status")
async def status(klyuch: str = ""):
    from engine import kniga as K
    return K.статус(klyuch)


@роутер.get("/api/kniga/fayl")
async def fayl(klyuch: str = "", n: int = 0):
    from engine import kniga as K, arhiv as A
    ст = K.статус(klyuch)
    if not ст.get("ok"):
        return JSONResponse(ст, status_code=404)
    з = K._читать(ст["klyuch"])
    с = K.взять_страницу(з, int(n) if n else (з["страницы"][-1]["n"] if з["страницы"] else 0))
    if not с:
        return JSONResponse({"ok": False, "reason": "no_page"}, status_code=404)
    html = A._взять(с["fayl"]) or ""
    return HTMLResponse(html, headers={"Content-Disposition": f'inline; filename="quantareon-{ст["klyuch"]}-{с["n"]}.html"'})


def письмо_с_файлом(з, n, итог, lang):
    """17.09 · файл страницы на почту. Имя вложения — латиницей (Brevo портит русские имена).
    Не ушло — запасное письмо со ссылкой и ключом, и хозяину сообщение в Telegram. True — файл ушёл."""
    ру = lang == "ru"
    дата = итог["местное"].strftime("%d.%m.%Y")
    ключ = з["ключ"]
    тема = (f"Квантареон · {'страница ' + str(n) if з['тариф']=='shiv' else 'полный разбор дня'} · {дата}"
            if ру else f"Quantareon · {'page ' + str(n) if з['тариф']=='shiv' else 'full reading of the day'} · {дата}")
    имя = f"quantareon-{ключ}-{n}-{итог['местное'].strftime('%Y-%m-%d')}.html"
    ушло = False
    try:
        import pochta as П
        текст = ("Ваш разбор во вложении. Открывается в любом браузере." if ру
                 else "Your reading is attached. Opens in any browser.")
        ушло = bool(П.отправить_файл(з["почта"], тема, текст, имя, итог["html"]))
        if not ушло:
            стр = "https://quantareon.com/razbor-ru" if ру else "https://quantareon.com/razbor"
            запас = (f"Ваш разбор готов, но файл не удалось приложить к письму.\n\n"
                     f"Откройте страницу {стр}, впишите ключ {ключ} в поле «Мой ключ» и нажмите «Открыть книгу». "
                     f"Там же будет кнопка «Скачать файл»." if ру else
                     f"Your reading is ready, but the file could not be attached.\n\n"
                     f"Open {стр}, enter the key {ключ} in the \"My key\" field and press \"Open the book\". "
                     f"The \"Download file\" button will be there.")
            П.отправить_текст(з["почта"], тема, запас)
    except Exception as e:
        print(f"книга: письмо с файлом не ушло: {e}")
    if not ушло:
        try:
            import oplata_api as О
            О._в_телеграм(f"⚠️ Файл разбора не ушёл на почту {з['почта']} (ключ {ключ}, страница {n}). "
                          f"Отправлено письмо со ссылкой на страницу.")
        except Exception as e:
            print(f"книга: Telegram не ответил: {e}")
    return ушло


def _страница_в_фоне(номер, ключ, n, iso, lat, lon, tz, мухурта, ичзин, lang):
    from engine import kniga as K, karta_dnya as КД, arhiv as A
    зд = ЗАДАЧИ[номер]
    try:
        з = K._читать(ключ)
        м = K.момент_страницы(з, n)
        контекст = None
        режим = "полный"
        if n > 1:
            д0 = КД.полочка_дня(м, lat, lon, tz)
            контекст = K.контекст_продолжения(з, n, КД.асц_дня(д0))
            режим = "продолжение"
        итог = КД.собрать_карту(м, lat, lon, tz, мухурта=мухурта, ичзин=ичзин, имя=ключ,
                                этап=lambda т: зд.__setitem__("etap", т), lang=lang, режим=режим, контекст=контекст)
        резюме = ""
        for н, т in итог["razdely"]:
            if "РЕЗЮМЕ" in н.upper() or "SUMMARY" in н.upper():
                резюме = т
        K.записать_страницу(K._читать(ключ), n, м, итог["fayl"], резюме, итог["асц"])
        зд.update({"gotovo": True, "html": итог["html_stranicy"], "fayl": итог["fayl"], "n": n,
                   "imya_fayla": итог["imya_fayla"], "etap": "готово"})
        # письмо с файлом — если у ключа есть почта
        if з.get("почта"):
            письмо_с_файлом(з, n, итог, lang)
    except Exception as e:
        зд.update({"gotovo": True, "oshibka": str(e)[:300], "etap": "ошибка"})


@роутер.post("/api/kniga/stranica")
async def stranica(request: Request):
    from engine import kniga as K, arhiv as A
    try:
        з = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    ст = K.статус(_ключ(з))
    if not ст.get("ok"):
        return JSONResponse(ст, status_code=404)
    зап = K._читать(ст["klyuch"])
    сейчас = datetime.now(timezone.utc)
    if not зап.get("корень"):
        # 16.09 · корень книги — секунда витрины. Сначала по номеру из движка (работает с любого
        # устройства), потом из того, что прислала страница (память браузера, как раньше).
        в = K.взять_витрину(з.get("vitrina")) if з.get("vitrina") else None
        if в:
            зап = K.открыть_корень(зап, в["момент"], в["lat"], в["lon"], в["tz"],
                                   в.get("мухурта", ""), в.get("ичзин", ""))
        if not зап.get("корень") and (з.get("lat") is None or з.get("lon") is None):
            return JSONResponse({"ok": False, "reason": "no_place"}, status_code=400)
        if not зап.get("корень"):
            try:
                iso = str(з.get("iso") or сейчас.isoformat())
                датой = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                lat, lon, tz = float(з["lat"]), float(з["lon"]), float(з.get("tz") or 0)
            except Exception:
                return JSONResponse({"ok": False, "reason": "bad_moment"}, status_code=400)
            # секунда из браузера: не из будущего и не старше двух суток
            if not (-600 < (сейчас - датой).total_seconds() < 86400 * 2):
                return JSONResponse({"ok": False, "reason": "bad_moment"}, status_code=400)
            зап = K.открыть_корень(зап, датой.isoformat(), lat, lon, tz)
    к = зап["корень"]
    n = K.номер_сегодня(зап, сейчас.isoformat())
    if n < 1:
        n = 1
    if зап["тариф"] == "den":
        n = 1          # разовый: одна страница, снимок; открыть свой файл можно и потом
    elif n > зап["дней"]:
        return JSONResponse({"ok": False, "reason": "istek", "dney": зап["дней"]}, status_code=403)
    готовая = K.взять_страницу(зап, n)
    if готовая:
        html = A._взять(готовая["fayl"]) or ""
        return {"ok": True, "gotovo": True, "n": n, "html": html, "fayl": готовая["fayl"]}
    # уже считается?
    for ном, т in ЗАДАЧИ.items():
        if t_key(т) == (ст["klyuch"], n) and not т.get("gotovo"):
            return {"ok": True, "nomer": ном, "n": n}
    if sum(1 for т in ЗАДАЧИ.values() if not т.get("gotovo")) >= 3:
        return JSONResponse({"ok": False, "reason": "busy"}, status_code=429)
    номер = uuid.uuid4().hex[:12]
    ЗАДАЧИ[номер] = {"gotovo": False, "etap": "поставлено в работу", "когда": сейчас.timestamp(),
                     "kniga": (ст["klyuch"], n)}
    # 16.09 · часы и символ дня: что прислала страница (она считает их на сегодня для места
    # корня), иначе — то, что запомнила витрина первого дня
    мухурта = str(з.get("muhurta") or "")[:600] or (к.get("мухурта", "") if n == 1 else "")
    ичзин = str(з.get("iching") or "")[:1500] or (к.get("ичзин", "") if n == 1 else "")
    threading.Thread(target=_страница_в_фоне,
                     args=(номер, ст["klyuch"], n, к["момент"], к["lat"], к["lon"], к["tz"],
                           мухурта, ичзин, зап.get("lang") or "ru"), daemon=True).start()
    return {"ok": True, "nomer": номер, "n": n}


def t_key(т):
    return т.get("kniga")
