"""
КАССА: ПЕРЕВОД ПО СБП ПО НОМЕРУ ТЕЛЕФОНА (17.09.2026). Подключается к api/main.py роутером.

Как устроено:
  1. Страница просит заказ: почта + тариф → движок выдаёт СУММУ-КОД (300, 301, 302 …).
  2. Покупатель переводит ровно эту сумму по СБП по номеру телефона получателя.
  3. На телефоне получателя ловушка читает пуш банка и шлёт сюда текст пуша.
  4. Движок находит заказ с этой суммой → «оплачен» → ключ, письмо, отчёт в Telegram.
  5. Страница спрашивает статус и показывает ключ.

Адреса:
  POST /api/oplata/zakaz    {pochta, tarif: den|shiv7|shiv30, lang}   — открыт
  GET  /api/oplata/status?nomer=                                           — открыт
  POST /api/oplata/push     {sekret, tekst}  — ловушка (MacroDroid); открыт, но без верного секрета отказ
  GET  /api/oplata/spisok                                                  — только кабинет (пароль)
  POST /api/oplata/otmetit  {nomer}  — отметить оплату руками; только кабинет (пароль)

Секреты — в настройках Render: OPLATA_SECRET (пароль ловушки) и TG_TOKEN (токен бота).
Чат для отчётов — ТЕЛЕГРАМ_ЧАТ ниже.
"""
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

# ═══════════════════ НАСТРОЙКИ — ПРАВИТЬ ЗДЕСЬ ═══════════════════
# Данные получателя. Меняются тут и больше нигде: страница берёт их отсюда.
ПОЛУЧАТЕЛЬ = {
    "telefon": "+7 962 881-39-56",               # перевод по СБП по этому номеру
    "bank": "Т-Банк",                            # какой банк выбрать при переводе
    "imya": "Александр Г. (Квантареон)",         # банк покупателя покажет «Александр Г.»
}
# тариф на странице → (цена в рублях, вид ключа, дней)
ТАРИФЫ = {
    "den":    (300,  "den",  1),
    "shiv7":  (1500, "shiv", 7),
    "shiv30": (6000, "shiv", 30),
    # 20.09 · товар-файл: готовый файл вместо системы ключей/страниц (см. вид "fayl" ниже)
    "kniga-kundalini": (700, "fayl", 0),
}
# 20.09 · товары-файлы: тариф → путь к файлу, имя вложения, название для отчёта в Telegram
ТОВАРЫ_ФАЙЛЫ = {
    "kniga-kundalini": {
        "путь": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "ogon_glubin.pdf"),
        "imya": "Ogon-Glubin.pdf",
    },
}
ПОЛОСА = 25          # сколько сумм подряд у тарифа: 300 … 324
ЖИВЁТ_МИНУТ = 60     # сколько заказ ждёт перевод
ЗАПАС_МИНУТ = 30     # после срока перевод ещё узнаётся, а сумма не отдаётся другому
ЗАКАЗОВ_С_АДРЕСА = 3 # одновременно ждущих заказов с одного адреса
ТЕЛЕГРАМ_ЧАТ = "1193315385"  # куда слать отчёты об оплатах (его чат с ботом @Groq_official_bot)
# ═════════════════════════════════════════════════════════════════

роутер = APIRouter()
ЗАМОК = threading.Lock()
ВИД_ПОЧТЫ = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def _путь():
    from engine import arhiv as A
    return f"{A.АРХИВ}/oplata/zakazy.json"


_БАЗА = None   # копия в памяти: движок работает одним процессом, хранилище читаем один раз после запуска


def _читать():
    global _БАЗА
    if _БАЗА is None:
        from engine import arhiv as A
        т = A._взять(_путь())
        _БАЗА = json.loads(т) if т else {"заказы": [], "пуши": [], "чужие": []}
    return _БАЗА


def _писать(база):
    from engine import arhiv as A
    база["заказы"] = база["заказы"][-500:]
    база["пуши"] = база["пуши"][-300:]
    база["чужие"] = база["чужие"][-100:]
    A._положить(_путь(), json.dumps(база, ensure_ascii=False, indent=1))


def _сейчас():
    return datetime.now(timezone.utc)


def _дата(iso):
    return datetime.fromisoformat(iso)


def _занята(з, сейчас):
    """Сумма занята, пока заказ ждёт — и ещё ЗАПАС_МИНУТ после срока."""
    return з["состояние"] == "ждёт" and _дата(з["до"]) + timedelta(minutes=ЗАПАС_МИНУТ) > сейчас


def _наружу(з):
    сейчас = _сейчас()
    сост = з["состояние"]
    if сост == "ждёт" and з.get("отменён"):
        сост = "отменён"
    elif сост == "ждёт" and _дата(з["до"]) <= сейчас:
        сост = "истёк"
    о = {"ok": True, "nomer": з["номер"], "summa": з["сумма"], "tarif": з["тариф"],
         "sostoyanie": {"ждёт": "zhdet", "оплачен": "oplachen", "истёк": "istek", "отменён": "otmenen"}[сост],
         "do": з["до"], "telefon": ПОЛУЧАТЕЛЬ["telefon"], "bank": ПОЛУЧАТЕЛЬ["bank"],
         "imya": ПОЛУЧАТЕЛЬ["imya"]}
    if сост == "оплачен":
        о["klyuch"] = з.get("ключ", "")
        о["pismo"] = bool(з.get("письмо"))
    return о


def _адрес(request):
    # сайт передаёт адрес покупателя своим заголовком: свой cf-connecting-ip Cloudflare
    # на пути сайт → движок перезаписывает адресом самого сайта
    return (request.headers.get("x-pokupatel-ip") or request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
            or (request.client.host if request.client else "")).strip()


def _секунда_входа(м):
    """18.09 · секунда входа и место с главной — чтобы книга открылась с любого устройства
    (например, на телефоне, куда перешли по коду). Проверяем, остальное отбрасываем."""
    try:
        iso = str(м.get("iso") or "")
        когда = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if когда.tzinfo is None:
            return None
        lat, lon, tz = float(м["lat"]), float(м["lon"]), float(м.get("tz") or 0)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -12 <= tz <= 14):
            return None
        if not (-600 < (_сейчас() - когда).total_seconds() < 86400 * 2):
            return None
        return {"iso": когда.isoformat(), "lat": lat, "lon": lon, "tz": tz}
    except Exception:
        return None


def _новый_заказ(почта, тариф, lang, адрес, секунда=None):
    цена = ТАРИФЫ[тариф][0]
    with ЗАМОК:
        база = _читать()
        сейчас = _сейчас()
        # тот же человек и тот же тариф, заказ ещё ждёт — отдаём его же, новую сумму не занимаем
        for з in reversed(база["заказы"]):
            if з["почта"].lower() == почта.lower() and з["тариф"] == тариф and з["состояние"] == "ждёт" \
                    and _дата(з["до"]) > сейчас:
                return _наружу(з)
        if sum(1 for з in база["заказы"] if з.get("адрес") == адрес and з["состояние"] == "ждёт"
               and _дата(з["до"]) > сейчас) >= ЗАКАЗОВ_С_АДРЕСА:
            return JSONResponse({"ok": False, "reason": "too_many"}, status_code=429)
        # метка устройства и секунда входа нужны только пока заказ ждёт оплату — у остальных стираем
        for старый in база["заказы"]:
            if not _занята(старый, сейчас):
                старый.pop("адрес", None)
                старый.pop("секунда", None)
        занятые = {з["сумма"] for з in база["заказы"] if _занята(з, сейчас)}
        сумма = next((цена + к for к in range(ПОЛОСА) if цена + к not in занятые), None)
        if сумма is None:
            return JSONResponse({"ok": False, "reason": "busy"}, status_code=429)
        з = {"номер": secrets.token_hex(8), "почта": почта, "тариф": тариф, "lang": lang, "сумма": сумма,
             "создан": сейчас.isoformat(), "до": (сейчас + timedelta(minutes=ЖИВЁТ_МИНУТ)).isoformat(),
             "состояние": "ждёт", "адрес": адрес}
        if секунда:
            з["секунда"] = секунда
        база["заказы"].append(з)
        _писать(база)
        return _наружу(з)


@роутер.post("/api/oplata/zakaz")
async def zakaz(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    почта = str(т.get("pochta") or "").strip()[:200]
    тариф = str(т.get("tarif") or "")
    lang = "en" if str(т.get("lang") or "").startswith("en") else "ru"
    if not ВИД_ПОЧТЫ.match(почта):
        return JSONResponse({"ok": False, "reason": "bad_mail"}, status_code=400)
    if тариф not in ТАРИФЫ:
        return JSONResponse({"ok": False, "reason": "bad_tarif"}, status_code=400)
    if not ПОЛУЧАТЕЛЬ["telefon"]:
        return JSONResponse({"ok": False, "reason": "not_ready"}, status_code=503)
    адрес = hashlib.sha256(_адрес(request).encode()).hexdigest()[:16]
    секунда = _секунда_входа(т.get("moment")) if isinstance(т.get("moment"), dict) else None
    return await run_in_threadpool(_новый_заказ, почта, тариф, lang, адрес, секунда)


def _найти(nomer):
    with ЗАМОК:
        for з in _читать()["заказы"]:
            if з["номер"] == nomer:
                return _наружу(з)
    return None


def _отменить(nomer):
    """18.09 · покупатель передумал. Заказ сразу перестаёт ждать, но сумма ещё ЗАПАС_МИНУТ
    за ним: если перевод всё же ушёл, оплата найдётся и ключ придёт на почту."""
    with ЗАМОК:
        база = _читать()
        з = next((з for з in база["заказы"] if з["номер"] == nomer), None)
        if з is None:
            return None
        if з["состояние"] == "ждёт" and not з.get("отменён"):
            з["отменён"] = True
            з["до"] = _сейчас().isoformat()
            з.pop("адрес", None)
            _писать(база)
        return _наружу(з)


@роутер.post("/api/oplata/otmena")
async def otmena(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    о = await run_in_threadpool(_отменить, str(т.get("nomer") or ""))
    return о or JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)


@роутер.get("/api/oplata/status")
async def status(nomer: str = ""):
    о = await run_in_threadpool(_найти, nomer)
    return о or JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)


@роутер.get("/api/oplata/fayl")
async def fayl(nomer: str = ""):
    """20.09 · товар-файл (книга): скачивание по номеру ОПЛАЧЕННОГО заказа — не по паролю кабинета."""
    о = await run_in_threadpool(_найти, nomer)
    if not о or о.get("sostoyanie") != "oplachen":
        return JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)
    товар = ТОВАРЫ_ФАЙЛЫ.get(о.get("tarif"))
    if not товар or not os.path.isfile(товар["путь"]):
        # 20.09 · КРИТИК: файл не залился при деплое — не ронять ручку голым 500,
        # отдать тот же чистый отказ, что и на остальные случаи кассы
        if товар:
            print(f"касса: файл товара не найден на диске: {товар['путь']}")
        return JSONResponse({"ok": False, "reason": "no_file"}, status_code=404)
    from fastapi.responses import FileResponse
    return FileResponse(товар["путь"], media_type="application/pdf", filename=товар["imya"])


# ─── пуш от ловушки ───────────────────────────────────────────────
_СУММА = re.compile(r"([+]?)\s*(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,](\d{1,2}))?\s*(?:₽|руб|RUB|р\.)", re.I)


# 17.09 · как Т-Банк пишет о поступлении (живой пример):
#   «Пополнение, счет RUB. 10 ₽. Игорь Д. Доступно 10 ₽»
# Берём только пополнения; всё, что после «Доступно / Баланс / Остаток», — остаток счёта, не платёж.
_ПОПОЛНЕНИЕ = re.compile(r"пополнение,\s*сч[её]т", re.I)   # ровно как пишет Т-Банк
# Свои отчёты касса шлёт в Telegram, а ловушка на телефоне видит и их. Такие тексты — не оплата.
_СВОЁ = re.compile(r"✅|❔|🔔|🧾|Квантареон|Пробить чек|ждущего заказа", re.I)
_ОСТАТОК = re.compile(r"доступно|баланс|остаток", re.I)


def суммы_из_текста(текст):
    """Суммы платежа из текста пуша: целые рубли. Копейки не ноль — не наш код, пропускаем.
    Не пополнение — пусто. Остаток счёта отрезается. Сумма со знаком «+» идёт первой."""
    текст = текст or ""
    if _СВОЁ.search(текст):
        return []
    м = _ПОПОЛНЕНИЕ.search(текст)
    if not м:
        return []
    текст = текст[м.start():]          # всё до «Пополнение, счёт» — заголовок уведомления, не платёж
    м = _ОСТАТОК.search(текст)
    if м:
        текст = текст[:м.start()]
    найдено = []
    for знак, рубли, копейки in _СУММА.findall(текст):
        if копейки and int(копейки) != 0:
            continue
        найдено.append((знак != "+", int(re.sub(r"\D", "", рубли))))
    return [с for _, с in sorted(найдено, key=lambda п: п[0])]


def _закрыть(з, как):
    """Заказ оплачен: выдать ключ. Вызывается под замком; письмо шлёт _после_оплаты — уже без замка."""
    цена, вид, дней = ТАРИФЫ[з["тариф"]]
    if вид == "fayl":
        # 20.09 · товар-файл (книга): готовый файл, без системы ключей/страниц K.kniga
        з.pop("секунда", None)
        зап = {"ключ": "QF-" + з["номер"][:8].upper(), "почта": з["почта"], "тариф": з["тариф"],
               "lang": з["lang"], "вид": "fayl"}
    else:
        from engine import kniga as K
        зап = K.выдать(з["почта"], вид, дней, з["lang"])
        с = з.pop("секунда", None)
        if с:
            try:
                зап = K.открыть_корень(зап, с["iso"], с["lat"], с["lon"], с["tz"])
            except Exception as e:
                print(f"касса: корень книги не открылся: {e}")
    з.update({"состояние": "оплачен", "ключ": зап["ключ"], "оплачен": _сейчас().isoformat(), "как": как})
    з.pop("адрес", None)
    return зап


def _письмо_файла_товара(зап):
    """20.09 · товар-файл (книга): PDF вложением на почту. True — ушло."""
    товар = ТОВАРЫ_ФАЙЛЫ.get(зап["тариф"])
    if not товар or not зап.get("почта"):
        return False
    try:
        with open(товар["путь"], "rb") as ф:
            содержимое = ф.read()
    except Exception as e:
        print(f"касса: файл товара не нашёлся ({товар['путь']}): {e}")
        return False
    ру = зап.get("lang") != "en"
    тема = "Ваша книга «Огонь глубин»" if ру else "Your book"
    текст = (f"Спасибо за покупку! Книга «Огонь глубин» — во вложении.\n\n"
             f"Если файл не открылся — скачайте его на странице quantareon.com/kundalini-ru, "
             f"код заказа: {зап['ключ']}." if ру else
             f"Thank you for your purchase! The book is attached.\n\n"
             f"If it did not open — download it at quantareon.com/kundalini-ru, order code: {зап['ключ']}.")
    try:
        import pochta as П
        return bool(П.отправить_файл(зап["почта"], тема, текст, товар["imya"], содержимое))
    except Exception as e:
        print(f"касса: письмо с файлом не ушло: {e}")
        return False


def _после_оплаты(номер, зап):
    """Письмо с ключом/файлом и отчёт в Telegram. Долгое (почта ждёт до 30 с) — поэтому вне замка."""
    if зап.get("вид") == "fayl":
        ушло = _письмо_файла_товара(зап)
    else:
        import kniga_api as KA
        ушло = KA.письмо_с_ключом(зап)
    with ЗАМОК:
        база = _читать()
        з = next((з for з in база["заказы"] if з["номер"] == номер), None)
        if з is None:
            return
        з["письмо"] = ушло
        _писать(база)
        отчёт = _отчёт(з)
    _в_телеграм(отчёт)


def _в_телеграм(текст):
    токен, чат = os.getenv("TG_TOKEN", ""), os.getenv("TG_CHAT", "") or ТЕЛЕГРАМ_ЧАТ
    if not (токен and чат):
        return False
    try:
        import httpx
        о = httpx.post(f"https://api.telegram.org/bot{токен}/sendMessage",
                       json={"chat_id": чат, "text": текст}, timeout=15)
        return о.status_code == 200
    except Exception as e:
        print(f"касса: Telegram не ответил: {e}")
        return False


def _кто(текст):
    """Имя плательщика из уведомления: «… 300 ₽. Игорь Д. Доступно …» → «Игорь Д.»."""
    м = re.search(r"₽\.\s*(.+?)\s*(?:Доступно|Баланс|Остаток|$)", текст or "", re.I | re.S)
    return (м.group(1).strip()[:60] if м else "")


def _отчёт(з):
    имена = {"den": "разовый день", "shiv7": "книга · 7 дней", "shiv30": "книга · 30 дней",
             "kniga-kundalini": "книга «Огонь глубин»"}
    return (f"✅ Оплата {з['сумма']} ₽ — {имена.get(з['тариф'], з['тариф'])}\n"
            f"Почта: {з['почта']}\nКлюч: {з['ключ']}\n"
            f"Письмо: {'ушло' if з.get('письмо') else 'НЕ ушло — отправь ключ руками'}\n"
            f"Отмечено: {'ловушкой' if з.get('как') == 'пуш' else 'руками в кабинете'}\n"
            f"{('Перевёл: ' + _кто(з['пуш']) + chr(10)) if _кто(з.get('пуш')) else ''}"
            f"🧾 Пробить чек в «Мой налог»: {з['сумма']} ₽")


def _наша_полоса(сумма):
    return any(цена <= сумма < цена + ПОЛОСА for цена, _, _ in ТАРИФЫ.values())


def _разобрать_пуш(текст, когда):
    отпечаток = hashlib.sha256(f"{текст}|{когда}".encode()).hexdigest()[:20]
    минута = int(_сейчас().timestamp() // 60)
    суммы = суммы_из_текста(текст)
    найден = зап = None
    сообщение = None
    with ЗАМОК:
        база = _читать()
        # старый вид записи — просто строка; новый — [отпечаток, минута]
        недавние = [п for п in база["пуши"] if isinstance(п, list) and минута - п[1] < 10]
        if any(п[0] == отпечаток for п in недавние):
            return {"ok": True, "povtor": True}
        база["пуши"] = недавние + [[отпечаток, минута]]
        сейчас = _сейчас()
        for сумма in суммы:
            ждут = [з for з in база["заказы"] if з["сумма"] == сумма and _занята(з, сейчас)]
            if ждут:
                найден = min(ждут, key=lambda з: з["создан"])
                break
        if найден:
            найден["пуш"] = текст[:200]
            зап = _закрыть(найден, "пуш")
        elif суммы and _наша_полоса(суммы[0]):
            # похоже на покупателя, который ошибся суммой или опоздал — хозяину стоит взглянуть.
            # Прочие поступления на счёт (личные переводы) не храним и никуда не шлём.
            база["чужие"].append({"когда": сейчас.isoformat(), "текст": текст[:200]})
            сообщение = (f"❔ Пришло {суммы[0]} ₽, ждущего заказа с такой суммой нет — "
                         f"возможно, покупатель ошибся суммой или опоздал.\nПеревёл: {_кто(текст) or 'не указано'}")
        _писать(база)
    if найден:
        _после_оплаты(найден["номер"], зап)
    elif сообщение:
        _в_телеграм(сообщение)
    return {"ok": True, "nayden": bool(найден), "summy": суммы}


def _тело_ловушки(сырое):
    """Телефон подставляет текст уведомления как есть: в нём бывают переносы строк и кавычки,
    которые ломают JSON. Разбираем терпимо, чтобы не потерять оплату."""
    текст = сырое.decode("utf-8", "replace")
    try:
        return json.loads(текст)
    except Exception:
        pass
    try:
        return json.loads(текст.replace("\r", " ").replace("\n", " "))
    except Exception:
        pass
    с = re.search(r'"sekret"\s*:\s*"([^"]*)"', текст)
    т = re.search(r'"tekst"\s*:\s*"(.*)"\s*[,}]', текст, re.S)
    if not с or not т:
        return None
    return {"sekret": с.group(1), "tekst": т.group(1).replace("\n", " ")}


@роутер.post("/api/oplata/push")
async def push(request: Request):
    """Два вида запроса от телефона:
      1) пароль в адресе (…/push?k=ПАРОЛЬ), в теле — просто текст уведомления. Так настроен MacroDroid:
         фигурные скобки у него служебные и JSON в теле он портит;
      2) JSON {sekret, tekst} — как раньше."""
    секрет = os.getenv("OPLATA_SECRET", "")
    сырое = await request.body()
    пароль_в_адресе = request.query_params.get("k") or request.headers.get("x-kassa")
    т = _тело_ловушки(сырое)
    if пароль_в_адресе:
        if not isinstance(т, dict) or "tekst" not in т:
            т = {"tekst": сырое.decode("utf-8", "replace").strip()}
        т["sekret"] = пароль_в_адресе
    if not isinstance(т, dict):
        показ = re.sub(r'("sekret"\s*:\s*")[^"]*', r'\1***', сырое[:160].decode("utf-8", "replace"))
        print(f"касса: ловушка прислала непонятное тело: {показ!r}")
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    if not секрет or not secrets.compare_digest(str(т.get("sekret") or "").encode(), секрет.encode()):
        return JSONResponse({"ok": False, "reason": "locked"}, status_code=403)
    текст = str(т.get("tekst") or "")[:1000]
    когда = str(т.get("vremya") or "")[:40]
    return await run_in_threadpool(_разобрать_пуш, текст, когда)


# ─── кабинет (за паролем движка) ─────────────────────────────────
@роутер.get("/api/oplata/proverka-tg")
async def proverka_tg():
    """Проверка связи с Telegram: открыть в браузере после входа в движок."""
    if not os.getenv("TG_TOKEN"):
        return {"ok": False, "otvet": "На Render не задан TG_TOKEN"}
    ушло = await run_in_threadpool(_в_телеграм, "🔔 Проверка связи: касса Квантареона на месте. Сюда будут приходить отчёты об оплатах.")
    return {"ok": ушло, "otvet": "Сообщение отправлено — загляни в Telegram" if ушло
            else "Telegram не принял сообщение: проверь токен и что ты нажимал Start у бота"}


def _список():
    with ЗАМОК:
        база = _читать()
        return {"ok": True, "zakazy": [_наружу(з) | {"pochta": з["почта"], "sozdan": з["создан"]}
                                       for з in reversed(база["заказы"][-100:])],
                "chuzhie": list(reversed(база["чужие"][-20:]))}


@роутер.get("/api/oplata/spisok")
async def spisok():
    return await run_in_threadpool(_список)


def _отметить(nomer):
    with ЗАМОК:
        база = _читать()
        з = next((з for з in база["заказы"] if з["номер"] == nomer), None)
        if not з:
            return JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)
        if з["состояние"] == "оплачен":
            return _наружу(з)
        зап = _закрыть(з, "руками")
        _писать(база)
    _после_оплаты(nomer, зап)
    return _найти(nomer)


@роутер.post("/api/oplata/otmetit")
async def otmetit(request: Request):
    """Перевод пришёл, а ловушка промолчала — отметить руками."""
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    return await run_in_threadpool(_отметить, str(т.get("nomer") or ""))
