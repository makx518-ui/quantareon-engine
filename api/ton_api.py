# -*- coding: utf-8 -*-
"""
ТОН: РАЗОВАЯ ОПЛАТА ЧЕРЕЗ TON-КОШЕЛЁК (27.09.2026)

Английские страницы книг: оплата только TON (СБП к ним не относится — см. oplata_api.ТАРИФЫ_TON).
Окно оплаты как у Оракула: QR + кнопка Tonkeeper; кошелёк сам подставляет адрес, сумму и
комментарий (номер заказа). Покупатель только подтверждает перевод — больше ничего не делает.

КАК СЕРВЕР УЗНАЁТ ОПЛАТУ (один постоянный сторож, раз в 15 секунд):
  1. ПО НОМЕРУ. В комментарии перевода есть номер заказа, получатель — наш кошелёк,
     сумма ≥ 90% (как у Оракула). Работает сутки с момента заказа — по номеру ошибиться нельзя.
  2. ПО СУММЕ. Номера в комментарии нет (стёрли, кошелёк не передал) — узнаём по сумме:
     у каждого заказа своя сумма, отличается на тысячные доли TON (как 700/701/702 ₽ в СБП).
     Перевод ровно на эту сумму, пришедший после создания заказа, — его оплата.
  3. ЗАПАСНОЙ ИСТОЧНИК. TonCenter не ответил — те же переводы спрашиваем у TonAPI.
  4. НЕ УЗНАЛ — СИГНАЛ ВЛАДУ. Пришёл перевод, а заказ не нашёлся (или денег меньше) —
     сообщение в Telegram: сколько, от кого, комментарий, ссылка Tonviewer, кто ждёт оплату.
     Переводы Оракула (тот же кошелёк, комментарий dreamoracle_… / astro_…), копеечный спам
     и переводы старше самого раннего ждущего заказа — молча мимо.
  5. ОДИН ПЕРЕВОД — ОДИН ЗАКАЗ. Разобранные переводы запоминаются, повторно не считаются.

Адреса:
  POST /api/ton/payment-info  {nomer}   — кошелёк, сумма в TON, комментарий
  POST /api/ton/start-poll    {nomer}   — страница зовёт после показа окна: будит сторожа

Статус заказа страница смотрит через /api/oplata/status?nomer= — без изменений.
Секреты — в настройках Render: TON_API_KEY (необязателен, без него у TonCenter лимит жёстче).
"""
import base64
import os
import threading
import time
from datetime import timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import oplata_api as _O

роутер = APIRouter()

# ═══════════════════ НАСТРОЙКИ ═══════════════════
TON_WALLET = "UQAX5fcvi_KsXZZQprUUSilk5YUL2AAyoOPzQoNf1vKS7o4V"
TON_API_KEY = os.getenv("TON_API_KEY", "")
ЦЕНА_USD = _O.ТАРИФЫ_TON      # тариф → цена в USD, один список на всю кассу

ДОПУСК = 0.90          # как у Оракула: по номеру засчитываем перевод ≥ 90% суммы
ШАГ_СТОРОЖА = 15       # секунд между проверками кошелька (как у Оракула)
КУРС_ЖИВЁТ = 300       # секунд держим курс в памяти
ОКНО_ЧАСОВ = 24        # сколько после заказа ещё узнаём его оплату
ШАГ_СУММЫ = 0.001      # на сколько TON отличаются суммы соседних заказов
ШАГОВ_СУММЫ = 300      # не больше 0.3 TON сверху к цене
СПАМ_ДО = 0.1          # переводы меньше этого (копеечная рассылка) — молча мимо
ЧУЖОЕ = ("dreamoracle_", "astro_")   # комментарии Оракула (подписка / астро): тот же кошелёк, не наши
ПОЛЕ_СУММЫ = "ton_ozhidaem"   # сумма в TON, показанная покупателю (пишется в заказ)
ВИДЕЛ = "ton_videl"           # разобранные переводы (хэши) — в той же базе кассы

_курс = {"цена": None, "когда": 0.0}
_курс_замок = threading.Lock()
_будильник = threading.Event()
_сторож = {"поток": None}
_сторож_замок = threading.Lock()


# ═══════════════════ АДРЕС ═══════════════════
def _адрес_в_hex(адрес):
    """Любой вид адреса (UQ…/EQ…, base64 обоих видов, 0:hex) → 64 hex-символа.
    У Оракула то же (normalize_ton_addr), но там .lower() стоит до декодирования base64."""
    а = (адрес or "").strip()
    if not а:
        return ""
    if ":" in а:
        return а.split(":", 1)[1].lower()
    try:
        сырые = base64.b64decode(а.replace("-", "+").replace("_", "/") + "==")
        if len(сырые) == 36:
            return сырые[2:34].hex()
    except Exception:
        pass
    return а.lower()


_НАШ = _адрес_в_hex(TON_WALLET)


def _это_наш_кошелёк(адрес):
    return bool(адрес) and _адрес_в_hex(адрес) == _НАШ


def _хэш_в_hex(хэш):
    """TonCenter даёт хэш перевода в base64, TonAPI — в hex. Храним и показываем в hex
    (так его понимает Tonviewer), чтобы один перевод из двух источников был одним и тем же."""
    х = (хэш or "").strip()
    if len(х) == 64 and all(с in "0123456789abcdefABCDEF" for с in х):
        return х.lower()
    try:
        сырые = base64.b64decode(х.replace("-", "+").replace("_", "/") + "==")
        if len(сырые) == 32:
            return сырые.hex()
    except Exception:
        pass
    return х


# ═══════════════════ КУРС ═══════════════════
def _из_coingecko():
    о = httpx.get("https://api.coingecko.com/api/v3/simple/price",
                  params={"ids": "the-open-network", "vs_currencies": "usd"}, timeout=8)
    return float(о.json()["the-open-network"]["usd"])


def _из_tonapi():
    о = httpx.get("https://tonapi.io/v2/rates", params={"tokens": "ton", "currencies": "usd"}, timeout=8)
    return float(о.json()["rates"]["TON"]["prices"]["USD"])


def _из_okx():
    о = httpx.get("https://www.okx.com/api/v5/market/ticker", params={"instId": "TON-USDT"}, timeout=8)
    return float(о.json()["data"][0]["last"])


def _из_binance():
    о = httpx.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": "TONUSDT"}, timeout=8)
    return float(о.json()["price"])


ИСТОЧНИКИ_КУРСА = [("CoinGecko", _из_coingecko), ("TonAPI", _из_tonapi),
                   ("OKX", _из_okx), ("Binance", _из_binance)]


def _цена_ton_usd():
    """Живой курс TON→USD. Источники по очереди; ни один не ответил правдоподобно — None.
    Выдуманной запасной цены нет: лучше честный отказ, чем покупатель заплатит не ту сумму."""
    with _курс_замок:
        if _курс["цена"] and time.time() - _курс["когда"] < КУРС_ЖИВЁТ:
            return _курс["цена"]
        for имя, взять in ИСТОЧНИКИ_КУРСА:
            try:
                цена = взять()
                if 0.05 < цена < 500:
                    _курс.update(цена=цена, когда=time.time())
                    return цена
                print(f"тон: {имя} дал странный курс {цена}, пропускаю")
            except Exception as e:
                print(f"тон: курс от {имя} не получен ({type(e).__name__}: {str(e)[:120]})")
        return None


# ═══════════════════ ЗАКАЗЫ ═══════════════════
def _милли(тон):
    """Сумма в тысячных TON целым числом — сравниваем суммы без ошибок дробей."""
    return int(round(float(тон) * 1000))


def _в_окне(з, сейчас):
    """TON-заказ, по которому ещё может прийти оплата: не оплачен и создан меньше суток назад
    (истёкшие и отменённые тоже: человек мог перевести позже — касса это и обещает)."""
    return (з["тариф"] in ЦЕНА_USD and з["состояние"] == "ждёт"
            and _O._дата(з["создан"]) + timedelta(hours=ОКНО_ЧАСОВ) > сейчас)


def _сумма_заказа(nomer):
    """Сумма в TON для заказа. Уже показывали — та же (записана в заказе). Иначе: цена по живому
    курсу + свой сдвиг в тысячных, чтобы ни у одного TON-заказа за сутки не было такой же суммы.
    Возвращает (причина_отказа, сумма)."""
    with _O.ЗАМОК:
        з = next((з for з in _O._читать()["заказы"] if з["номер"] == nomer), None)
        if з is None:
            return "no_order", None
        if з["тариф"] not in ЦЕНА_USD:
            return "bad_tarif", None
        if з.get(ПОЛЕ_СУММЫ):
            return None, з[ПОЛЕ_СУММЫ]
        тариф = з["тариф"]
    курс = _цена_ton_usd()          # вне замка кассы: биржи могут отвечать секундами
    if not курс:
        return "busy", None
    основа = _милли(ЦЕНА_USD[тариф] / курс)
    with _O.ЗАМОК:
        база = _O._читать()
        з = next((з for з in база["заказы"] if з["номер"] == nomer), None)
        if з is None:
            return "no_order", None
        if з.get(ПОЛЕ_СУММЫ):         # пока считали, соседний запрос уже записал
            return None, з[ПОЛЕ_СУММЫ]
        сейчас = _O._сейчас()
        # сумма не повторяется ни у одного TON-заказа за сутки — даже у оплаченного: иначе поздний
        # перевод без номера по уже закрытому заказу мог бы закрыть чужой
        занятые = {_милли(д[ПОЛЕ_СУММЫ]) for д in база["заказы"]
                   if д is not з and д.get(ПОЛЕ_СУММЫ)
                   and _O._дата(д["создан"]) + timedelta(hours=ОКНО_ЧАСОВ) > сейчас}
        свободная = next((основа + к for к in range(ШАГОВ_СУММЫ) if основа + к not in занятые), None)
        if свободная is None:
            return "busy", None
        з[ПОЛЕ_СУММЫ] = свободная / 1000
        _O._писать(база)
        return None, з[ПОЛЕ_СУММЫ]


def _payment_info(nomer):
    причина, сумма = _сумма_заказа(nomer)
    if причина:
        код = {"no_order": 404, "bad_tarif": 400}.get(причина, 503)
        return JSONResponse({"ok": False, "reason": причина}, status_code=код)
    з = _O._найти(nomer)
    _будильник.set()
    return {"ok": True, "wallet": TON_WALLET, "ton_amount": сумма,
            "usd_amount": ЦЕНА_USD[з["tarif"]], "comment": nomer}


@роутер.post("/api/ton/payment-info")
async def payment_info(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    return await run_in_threadpool(_payment_info, str(т.get("nomer") or ""))


# ═══════════════════ ПЕРЕВОДЫ: TonCenter, запасной TonAPI ═══════════════════
def _из_toncenter():
    заголовки = {"X-API-Key": TON_API_KEY} if TON_API_KEY else {}
    о = httpx.get("https://toncenter.com/api/v2/getTransactions",
                  params={"address": TON_WALLET, "limit": 50}, headers=заголовки, timeout=10)
    данные = о.json()
    if not данные.get("ok"):
        raise RuntimeError(f"toncenter: {str(данные)[:150]}")
    итог = []
    for tx in данные.get("result", []):
        вход = tx.get("in_msg") or {}
        итог.append({"hash": _хэш_в_hex((tx.get("transaction_id") or {}).get("hash", "")),
                     "utime": int(tx.get("utime") or 0),
                     "nano": int(вход.get("value") or 0),
                     "comment": вход.get("message", "") or вход.get("comment", "") or "",
                     "to": вход.get("destination", "") or "",
                     "from": вход.get("source", "") or ""})
    return итог


def _из_tonapi_переводы():
    о = httpx.get(f"https://tonapi.io/v2/blockchain/accounts/{TON_WALLET}/transactions",
                  params={"limit": 50}, timeout=10)
    данные = о.json()
    if "transactions" not in данные:
        raise RuntimeError(f"tonapi: {str(данные)[:150]}")
    итог = []
    for tx in данные["transactions"]:
        вход = tx.get("in_msg") or {}
        тело = вход.get("decoded_body") or {}
        итог.append({"hash": _хэш_в_hex(tx.get("hash", "")),
                     "utime": int(tx.get("utime") or 0),
                     "nano": int(вход.get("value") or 0),
                     "comment": (тело.get("text") if isinstance(тело, dict) else "") or "",
                     "to": (вход.get("destination") or {}).get("address", ""),
                     "from": (вход.get("source") or {}).get("address", "")})
    return итог


def _переводы():
    """Последние входящие переводы. TonCenter не ответил — TonAPI. Оба упали — исключение
    (сторож его поймает и попробует через 15 секунд)."""
    try:
        return _из_toncenter()
    except Exception as e:
        print(f"тон: TonCenter не ответил ({type(e).__name__}: {str(e)[:120]}) — спрашиваю TonAPI")
        return _из_tonapi_переводы()


# ═══════════════════ СВЕРКА ═══════════════════
def _разобрать(заказы, переводы, видел):
    """Чистая сверка без побочных действий.
    заказы: [{"nomer","summa","sozdan_ts"}] — TON-заказы в окне; видел: множество хэшей.
    Возвращает (оплаты [(номер, сведения)], сигналы [текст], новые_хэши)."""
    оплаты, сигналы, новые = [], [], set()
    ждут = {з["nomer"]: з for з in заказы}
    # тревожить только переводами, пришедшими не раньше чем за час до самого раннего ждущего заказа
    с_какого = min((з["sozdan_ts"] for з in заказы), default=0) - 3600
    for tx in переводы:
        х = tx["hash"]
        if not х or х in видел or х in новые:
            continue
        if tx["nano"] <= 0 or not _это_наш_кошелёк(tx["to"]):
            новые.add(х)          # исходящие / служебные — не входящие деньги
            continue
        тон = tx["nano"] / 1e9
        коммент = tx["comment"]
        сведения = {"from": tx["from"] or "—", "ton_summa": round(тон, 3), "hash": х}
        # 1. по номеру заказа в комментарии
        номер = next((н for н in ждут if н in коммент), None)
        if номер:
            з = ждут[номер]
            if тон >= з["summa"] * ДОПУСК:
                оплаты.append((номер, {**сведения, "po": "по номеру заказа"}))
                del ждут[номер]
            else:
                сигналы.append(f"⚠️ По заказу {номер} пришло {тон:g} TON, а ждали {з['summa']:g} — "
                               f"меньше, книгу не выдал.\n" + _подробности(tx))
            новые.add(х)
            continue
        if any(коммент.lower().startswith(ч) for ч in ЧУЖОЕ):
            новые.add(х)          # оплата Оракула — не наша
            continue
        # 2. по сумме: ровно сумма заказа, перевод пришёл после создания заказа
        подходят = [з for з in ждут.values()
                    if _милли(з["summa"]) * 1_000_000 == tx["nano"] and tx["utime"] >= з["sozdan_ts"] - 60]
        if len(подходят) == 1:
            номер = подходят[0]["nomer"]
            оплаты.append((номер, {**сведения, "po": "по сумме (номера в комментарии не было)"}))
            del ждут[номер]
            новые.add(х)
            continue
        # 3. не узнали
        новые.add(х)
        if тон >= СПАМ_ДО and tx["utime"] >= с_какого:
            сигналы.append(f"❔ Пришло {тон:g} TON, заказ не узнан.\n" + _подробности(tx))
    return оплаты, сигналы, новые


def _подробности(tx):
    return (f"Комментарий: {tx['comment'] or '— нет —'}\n"
            f"От: {tx['from'] or '—'}\n"
            f"Проверить: https://tonviewer.com/transaction/{tx['hash']}")


def _ждущие_для_сигнала(заказы):
    if not заказы:
        return "Ждущих TON-заказов нет."
    строки = [f"• {з['nomer']} — {з['pochta']} — {з['summa']:g} TON" for з in заказы[-10:]]
    return ("Ждут оплату:\n" + "\n".join(строки) +
            "\nЕсли это чья-то оплата — отметь этот заказ оплаченным в кабинете, книга уйдёт сама.")


def _круг_сторожа():
    from api.maintenance import enabled
    if enabled():
        return 0
    """Один проход. Возвращает, сколько TON-заказов в окне (0 — к TonCenter даже не ходили)."""
    сейчас = _O._сейчас()
    with _O.ЗАМОК:
        база = _O._читать()
        заказы = [{"nomer": з["номер"], "summa": з[ПОЛЕ_СУММЫ], "pochta": з["почта"],
                   "sozdan_ts": _O._дата(з["создан"]).timestamp()}
                  for з in база["заказы"] if з.get(ПОЛЕ_СУММЫ) and _в_окне(з, сейчас)]
        первый_раз = ВИДЕЛ not in база
        видел = set(база.get(ВИДЕЛ, []))
    if not заказы:
        return 0
    переводы = _переводы()
    оплаты, сигналы, новые = _разобрать(заказы, переводы, видел)
    if первый_раз:
        сигналы = []   # первый запуск: старые переводы кошелька (Оракул, личные) — не тревожим
    for номер, сведения in оплаты:
        print(f"тон: заказ {номер} оплачен ({сведения['ton_summa']} TON, {сведения['po']})")
        _O._отметить(номер, как="TON", ton_info=сведения)
    if новые or первый_раз:
        # запоминаем разобранное только ПОСЛЕ отметки: упадём посередине — перевод разберётся снова,
        # а оплаченный заказ уже не ждёт, так что двойной выдачи не будет
        with _O.ЗАМОК:
            база = _O._читать()
            база[ВИДЕЛ] = (list(база.get(ВИДЕЛ, [])) + sorted(новые - set(база.get(ВИДЕЛ, []))))[-500:]
            _O._писать(база)
    if сигналы:
        ещё_ждут = [з for з in заказы if з["nomer"] not in {н for н, _ in оплаты}]
        хвост = _ждущие_для_сигнала(ещё_ждут)
        for с in сигналы:
            _O._в_телеграм(с + "\n\n" + хвост)
    return len(заказы)


# ═══════════════════ СТОРОЖ ═══════════════════
def _сторож_цикл():
    time.sleep(10)   # дать серверу подняться
    while True:
        try:
            _круг_сторожа()
        except Exception as e:
            print(f"тон: сторож споткнулся: {type(e).__name__}: {str(e)[:150]}")
        _будильник.wait(ШАГ_СТОРОЖА)
        _будильник.clear()


def _поднять_сторожа():
    with _сторож_замок:
        п = _сторож["поток"]
        if п and п.is_alive():
            return
        п = threading.Thread(target=_сторож_цикл, name="ton-storozh", daemon=True)
        _сторож["поток"] = п
        п.start()
        print("💎 тон: сторож кошелька поднят")


def _start_poll(nomer):
    з = _O._найти(nomer)
    if not з:
        return JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)
    _поднять_сторожа()
    _будильник.set()
    return {"ok": True, "already": з["sostoyanie"] == "oplachen"}


@роутер.post("/api/ton/start-poll")
async def start_poll(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    return await run_in_threadpool(_start_poll, str(т.get("nomer") or ""))


# сторож поднимается вместе с сервером — после перезапуска Render проверка идёт сама
if os.getenv("TON_STOROZH_OFF") != "1":
    _поднять_сторожа()
