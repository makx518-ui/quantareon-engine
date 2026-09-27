# -*- coding: utf-8 -*-
"""
ТОН: РАЗОВАЯ ОПЛАТА ЧЕРЕЗ TON-КОШЕЛЁК (27.09.2026)

Для покупателей вне России — СБП им недоступен, поэтому на английских страницах
вместо неё TON: QR-код + ссылка на Tonkeeper, как у Оракула (main.py Дримов),
механика взята оттуда почти один в один.

Заказ создаётся как обычно, через уже существующий /api/oplata/zakaz (тариф
kniga-kundalini-en / kniga-telepat-en) — тут это НЕ трогаем. Дальше, вместо
ловушки банковского пуша (СБП), сам сервер спрашивает TonCenter, не пришёл ли
на кошелёк перевод с комментарием = номер заказа. Нашёл — вызывает ту же самую
oplata_api._отметить(), что и кабинет при ручной отметке: письмо с файлом,
отчёт в телеграм — эта часть вообще не переписывается, берётся готовая.

Адреса:
  POST /api/ton/payment-info  {nomer}   — кошелёк, сумма в TON (курс живой), комментарий
  POST /api/ton/start-poll    {nomer}   — запустить проверку прихода перевода (до 30 минут)

Статус заказа страница по-прежнему смотрит через /api/oplata/status?nomer= —
он не меняется: как только сюда придёт подтверждение, тот статус сам покажет "oplachen".

Секреты — в настройках Render: TON_API_KEY (необязателен, но без него лимит запросов у TonCenter жёстче).
"""
import os
import threading
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

роутер = APIRouter()

# ═══════════════════ НАСТРОЙКИ ═══════════════════
TON_WALLET = "UQAX5fcvi_KsXZZQprUUSilk5YUL2AAyoOPzQoNf1vKS7o4V"
TON_API_KEY = os.getenv("TON_API_KEY", "")

# тариф → цена в USD (те же товары, что уже проданы по СБП внутри России — только для нерезидентов)
ЦЕНА_USD = {
    "kniga-kundalini-en": 10.0,
    "kniga-telepat-en": 10.0,
}

_опросы = {}   # nomer -> Thread (пока идёт проверка — не запускаем вторую на тот же заказ)
_ЗАМОК = threading.Lock()


def _цена_ton_usd():
    """Живой курс TON→USD (CoinGecko). Сеть недоступна — запасное значение, как у Оракула."""
    try:
        о = httpx.get("https://api.coingecko.com/api/v3/simple/price",
                      params={"ids": "the-open-network", "vs_currencies": "usd"}, timeout=10)
        return float(о.json()["the-open-network"]["usd"])
    except Exception as e:
        print(f"тон: курс не получен, беру запасной ({e})")
        return 3.0


def _нормализовать_адрес(адрес):
    """TonCenter отдаёт адрес то в raw, то в разных base64-представлениях —
    сверяем по последним символам после унификации набора символов."""
    return (адрес or "").strip().replace("-", "+").replace("_", "/")[-48:]


def _payment_info(nomer):
    import oplata_api as O
    з = O._найти(nomer)
    if not з:
        return JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)
    цена_usd = ЦЕНА_USD.get(з["tarif"])
    if цена_usd is None:
        return JSONResponse({"ok": False, "reason": "bad_tarif"}, status_code=400)
    курс = _цена_ton_usd()
    сумма_ton = round(цена_usd / курс, 3)
    return {"ok": True, "wallet": TON_WALLET, "ton_amount": сумма_ton, "usd_amount": цена_usd,
            "comment": nomer}


@роутер.post("/api/ton/payment-info")
async def payment_info(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    return await run_in_threadpool(_payment_info, str(т.get("nomer") or ""))


def _проверить_и_закрыть(nomer, ожидаемый_ton):
    """Фоновый поток: каждые 15 сек проверяет кошелёк через TonCenter. Ищет перевод с нужным
    комментарием и суммой ≥90% ожидаемой (запас на курс/комиссию — как у Оракула). Таймаут 30 минут."""
    import oplata_api as O
    попыток = 120   # 120 × 15 сек = 30 минут
    минимум = ожидаемый_ton * 0.90
    свой_адрес = _нормализовать_адрес(TON_WALLET)
    for _ in range(попыток):
        з = O._найти(nomer)
        if not з or з["sostoyanie"] != "zhdet":
            return   # оплачен другим путём, отменён или истёк — прекращаем опрос
        try:
            заголовки = {"X-API-Key": TON_API_KEY} if TON_API_KEY else {}
            о = httpx.get("https://toncenter.com/api/v2/getTransactions",
                          params={"address": TON_WALLET, "limit": 30}, headers=заголовки, timeout=10)
            данные = о.json()
            if данные.get("ok"):
                for tx in данные.get("result", []):
                    вход = tx.get("in_msg", {})
                    комментарий = вход.get("message", "") or вход.get("comment", "")
                    if nomer not in комментарий:
                        continue
                    if _нормализовать_адрес(вход.get("destination", "")) != свой_адрес:
                        continue
                    сумма_tx = int(вход.get("value", 0) or 0) / 1e9
                    if сумма_tx < минимум:
                        continue
                    хэш = (tx.get("transaction_id") or {}).get("hash", "")
                    сведения = {"from": вход.get("source", "") or "—", "ton_summa": round(сумма_tx, 3),
                                "hash": хэш}
                    O._отметить(nomer, как="TON", ton_info=сведения)
                    return
        except Exception as e:
            print(f"тон: опрос {nomer} споткнулся: {e}")
        time.sleep(15)


def _start_poll(nomer):
    import oplata_api as O
    з = O._найти(nomer)
    if not з:
        return JSONResponse({"ok": False, "reason": "no_order"}, status_code=404)
    if з["sostoyanie"] == "oplachen":
        return {"ok": True, "already": True}
    цена_usd = ЦЕНА_USD.get(з["tarif"])
    if цена_usd is None:
        return JSONResponse({"ok": False, "reason": "bad_tarif"}, status_code=400)
    with _ЗАМОК:
        живой = _опросы.get(nomer)
        if живой and живой.is_alive():
            return {"ok": True, "already": True}
        курс = _цена_ton_usd()
        ожидаемый = round(цена_usd / курс, 3)
        поток = threading.Thread(target=_проверить_и_закрыть, args=(nomer, ожидаемый), daemon=True)
        _опросы[nomer] = поток
        поток.start()
    return {"ok": True}


@роутер.post("/api/ton/start-poll")
async def start_poll(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    return await run_in_threadpool(_start_poll, str(т.get("nomer") or ""))
