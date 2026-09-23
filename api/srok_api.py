"""
ГОРОСКОП НА СРОК — недельный, месячный, годовой (23.09.2026). Подключается к api/main.py роутером.

Схема его 22–23.09: секунда входа на сайт — КОРЕНЬ (натальная карта момента), из него машина
разворачивает срок, умная модель читает его одним сюжетом от точки входа до точки выхода.
    неделя, месяц — engine/razvertka.py · собрать_гороскоп (один прогон, 3–5 минут)
    год          — engine/god_ot_kornya.py · собрать_год (шапка → 12 месяцев → финал)

POST /api/srok/zapustit  {tarif: nedelya|mesyac|god, iso, lat, lon, tz, imya, klyuch}
                         — ставит гороскоп в работу в фоне → {"nomer"}
GET  /api/srok/status?nomer  — этап; готово → имя файла и HTML
GET  /api/srok/fayl?nomer    — готовый файл скачиванием

⚠️ ЗАМОК: пока оплата не подключена, запуск только с хозяйским паролем (поле klyuch) —
иначе открытый адрес отдавал бы платный гороскоп даром. Статус и файл — только по номеру
своей задачи. Оплату подключим потом: запускать будет ключ оплаченного заказа.

СТОРОЖ (23.09, его «чтобы не сорвалось»): каждый заказ — карточка в облаке (R2 через engine/arhiv),
годовой — ещё и полка частей там же. Диск Render при заливке стирается, облако — нет.
    · модель сорвалась — повтор 10/30/90 с (engine/razvertka.спросить)
    · всё равно сорвалось — заказ «ждёт повтора», сторож возобновит через 5, 10, 20, 40, 60… минут
    · сервер перезапустился — сторож при старте находит неоконченные заказы и продолжает их;
      у года готовые части берутся с полки
    · не вышло за все попытки (около четырёх часов) — «сбой» и сообщение хозяину в Telegram
"""
import asyncio
import json
import math
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

роутер = APIRouter()
ПАРОЛЬ = os.environ.get("QUANTAREON_PASSWORD", "")
ТАРИФЫ = {"nedelya": 7, "mesyac": 30, "god": 365}
НАЗВАНИЕ = {"nedelya": "Недельный гороскоп", "mesyac": "Месячный гороскоп", "god": "Годовой гороскоп"}
СРОК_ПО_ТАРИФУ = {"nedelya": "неделя", "mesyac": "месяц", "god": "год"}
ОДНОВРЕМЕННО = 2        # год держит поток долго — больше двух заказов сразу не берём
ПАУЗЫ_СТОРОЖА = (5, 10, 20, 40, 60, 60, 60)   # минуты между возобновлениями; попыток — len + 1
ОБХОД = 300             # сторож обходит заказы раз в 5 минут
ПЕРВЫЙ_ОБХОД = 120      # при заливке старый сервер доживает ещё минуту-две — не хватаем его заказы сразу
АРЕНДА = 600            # «в работе», но карточка не обновлялась 10 минут — значит, работник умер
_НОМЕР = re.compile(r"[0-9a-f]{16}")
ЗАДАЧИ = {}             # в памяти этого запуска: номер → этап, готовность, html
_работают = set()       # номера, над которыми сейчас идёт поток
_замок = threading.Lock()


def _префикс():
    from engine import arhiv as A
    return f"{A.ПАПКА}/srok"


def _в_облако(ключ, текст, тип="application/json; charset=utf-8"):
    """Карточка, метка, итог — только в облако: молчаливый уход на диск Render их потеряет при заливке."""
    from engine import arhiv as A
    к = A._клиент()
    if к is None:          # облака нет вовсе (проверки в песочнице) — диск arhiv
        return A._положить(ключ, текст, тип)
    к.put_object(Bucket=A.БАКЕТ, Key=ключ, Body=текст.encode("utf-8"), ContentType=тип)   # ошибка — наверх


def _карточка(номер):
    from engine import arhiv as A
    т = A._взять(f"{_префикс()}/{номер}/заказ.json")
    try:
        return json.loads(т) if т else None
    except Exception:
        return None


def _записать(номер, к):
    from engine import arhiv as A
    к["обновлён"] = time.time()
    _в_облако(f"{_префикс()}/{номер}/заказ.json", json.dumps(к, ensure_ascii=False))


def _открыт(номер, да):
    """Метка неоконченного заказа: сторож смотрит только их, а не все карточки за всё время."""
    from engine import arhiv as A
    ключ = f"{_префикс()}/открытые/{номер}"
    _в_облако(ключ, str(time.time()), "text/plain; charset=utf-8") if да else A._убрать(ключ)


def _в_телеграм(текст):
    try:
        import oplata_api
        return oplata_api._в_телеграм(текст)
    except Exception as e:
        print(f"срок: Telegram недоступен: {type(e).__name__}: {e}")
        return False


# ─── 23.09 · оплата: касса (api/oplata_api.py) ставит сюда оплаченный заказ ─────────────
ЖДАТЬ = {"nedelya": "около пяти минут", "mesyac": "до десяти минут", "god": "около тридцати минут"}
ЖДАТЬ_EN = {"nedelya": "about five minutes", "mesyac": "up to ten minutes", "god": "about thirty minutes"}
НАЗВАНИЕ_EN = {"nedelya": "Weekly horoscope", "mesyac": "Monthly horoscope", "god": "Yearly horoscope"}


def ключ_из_номера(номер):
    """Ключ покупателя — тот же номер заказа, только в виде ключа: QS-XXXX-XXXX-XXXX-XXXX.
    Страница по ключу сама находит номер и открывает гороскоп с любого устройства."""
    return "QS-" + "-".join(номер[i:i + 4] for i in range(0, 16, 4)).upper()


def поставить_оплаченный(номер, тариф, секунда, почта, lang="ru"):
    """Оплачено → карточка в облако и в работу. Места нет — «в очереди»: заказ начнётся, как только
    закончится текущий (или на обходе сторожа). Повторный вызов с тем же номером ничего не ломает."""
    if тариф not in ТАРИФЫ or not _НОМЕР.fullmatch(номер or "") or not секунда:
        raise ValueError(f"плохой оплаченный заказ: {тариф} {номер} {bool(секунда)}")
    if _карточка(номер):
        return
    момент = datetime.fromisoformat(str(секунда["iso"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    пояс = float(секунда.get("tz") or 0)
    пояс = int(пояс) if пояс == int(пояс) else пояс
    к = {"tarif": тариф, "момент": момент.replace(microsecond=0).isoformat(),
         "ш": round(float(секунда["lat"]), 2), "д": round(float(секунда["lon"]), 2), "пояс": пояс,
         "имя": "гость", "почта": почта, "lang": lang, "оплачен": True,
         "состояние": "в очереди", "попыток": 0, "создан": time.time()}
    _записать(номер, к)
    _открыт(номер, True)
    ЗАДАЧИ[номер] = {"gotovo": False, "etap": "в очереди — начну, как только закончу предыдущий гороскоп",
                     "когда": time.time(), "tarif": тариф}
    _пустить(номер, к)


def письмо_ключа(почта, ключ, тариф, lang="ru"):
    """Сразу после оплаты: ключ и когда ждать файл. True — ушло."""
    try:
        import pochta as П
        if lang == "en":
            тема = "Your Quantareon key"
            текст = (f"Thank you for your purchase! Your key: {ключ}\n\n{НАЗВАНИЕ_EN[тариф]} is already being written — "
                     f"it takes {ЖДАТЬ_EN[тариф]}. The finished horoscope will come to this email as a file. "
                     f"You can also open and download it at quantareon.com/razbor — enter the key in the «My key» box.\n\n"
                     f"Keep the key: it is your entrance.")
        else:
            тема = "Ваш ключ Квантареона"
            текст = (f"Спасибо за покупку! Ваш ключ: {ключ}\n\n{НАЗВАНИЕ[тариф]} уже пишется — это {ЖДАТЬ[тариф]}. "
                     f"Готовый гороскоп придёт на эту почту файлом. Его также можно открыть и скачать на странице "
                     f"quantareon.com/razbor-ru — введите ключ в окне «Мой ключ».\n\nХраните ключ: это ваш вход.")
        return bool(П.отправить_текст(почта, тема, текст))
    except Exception as e:
        print(f"срок: письмо с ключом не ушло: {e}")
        return False


def _письмо_готово(к, имя_файла, html):
    """Готовый гороскоп — файлом на почту покупателя. True — ушло."""
    try:
        import pochta as П
        if к.get("lang") == "en":
            тема = f"{НАЗВАНИЕ_EN[к['tarif']]} · Quantareon"
            текст = (f"Your {НАЗВАНИЕ_EN[к['tarif']].lower()} is ready — it is attached to this letter. "
                     f"Open the file in any browser.\n\nQuantareon")
        else:
            тема = f"{НАЗВАНИЕ[к['tarif']]} · Квантареон"
            текст = (f"Ваш {НАЗВАНИЕ[к['tarif']].lower()} готов — он во вложении к этому письму. "
                     f"Откройте файл в любом браузере.\n\nКвантареон")
        return bool(П.отправить_файл(к["почта"], тема, текст, имя_файла, html))
    except Exception as e:
        print(f"срок: письмо с гороскопом не ушло: {e}")
        return False


def _в_фоне(номер, к):
    """Один заход работы над заказом. Любой исход — в карточку и в задачу."""
    зд = ЗАДАЧИ.setdefault(номер, {"gotovo": False, "когда": time.time()})
    зд.update({"gotovo": False, "etap": "в работе"})
    try:
        if к.get("состояние") != "в работе":   # возобновлённый заказ — снова «в работе» в облаке
            к["состояние"] = "в работе"
            _записать(номер, к)
        from engine import razvertka as R, god_ot_kornya as G
        пульс = {"когда": time.time()}

        def этап(т):
            зд["etap"] = т
            if time.time() - пульс["когда"] > 60:   # аренда: карточка свежая — заказ жив, сторож не трогает
                пульс["когда"] = time.time()
                try:
                    _записать(номер, к)
                except Exception as e:
                    print(f"срок {номер}: пульс не записался: {e}")
        момент = datetime.fromisoformat(к["момент"])
        if к["tarif"] == "god":
            итог = G.собрать_год(момент, к["ш"], к["д"], к["пояс"], имя=к["имя"], этап=этап,
                                 полка=G.ПолкаОблако(f"{_префикс()}/{номер}/полка"))
        else:
            итог = R.собрать_гороскоп(момент, к["ш"], к["д"], к["пояс"], ТАРИФЫ[к["tarif"]], имя=к["имя"], этап=этап)
        мест = R._мест(момент, к["пояс"])
        имя_файла = f"{НАЗВАНИЕ[к['tarif']]} · {мест.strftime('%d.%m.%Y')} · Квантареон.html"
        from engine import arhiv as A
        _в_облако(f"{_префикс()}/{номер}/итог.html", итог["html"], "text/html; charset=utf-8")
        к.update({"состояние": "готово", "имя_файла": имя_файла, "ошибка": ""})
        _записать(номер, к)
        _открыт(номер, False)
        if к.get("почта") and not к.get("письмо"):   # оплаченный заказ: файл — покупателю на почту
            к["письмо"] = _письмо_готово(к, имя_файла, итог["html"])
            try:
                _записать(номер, к)
            except Exception as e:
                print(f"срок {номер}: отметка письма не записалась: {e}")
            _в_телеграм(f"📜 {НАЗВАНИЕ[к['tarif']]} готов · ключ {ключ_из_номера(номер)}\nПочта: {к['почта']}\n"
                        f"Письмо с файлом: {'ушло' if к['письмо'] else 'НЕ ушло — отправь файл руками'}")
        зд.update({"gotovo": True, "html": итог["html"], "imya_fayla": имя_файла, "etap": "готово"})
        try:   # копия в общий архив карт, как у карты дня
            A.положить_карту(к["имя"], R.ЗАКАЗ_СРОКА[СРОК_ПО_ТАРИФУ[к["tarif"]]], итог["html"],
                             момент=момент, пояс_часов=к["пояс"])
        except Exception as e:
            print(f"срок: в архив карт не легло: {type(e).__name__}: {e}")
    except BaseException as e:   # любой сбой — в карточку: сторож решит, повторять ли
        ош = f"{type(e).__name__}: {e}"[:300]
        print(f"срок {номер}: сбой {ош}")
        к["попыток"] = к.get("попыток", 0) + 1
        к["ошибка"] = ош
        if к["попыток"] > len(ПАУЗЫ_СТОРОЖА):
            к["состояние"] = "сбой"
            зд.update({"gotovo": True, "oshibka": ош, "etap": "ошибка"})
            _в_телеграм(f"⚠️ {НАЗВАНИЕ.get(к.get('tarif'), 'Гороскоп')} {номер} не собрался за "
                        f"{к['попыток']} попыток.\nПоследняя ошибка: {ош}")
        else:
            пауза = ПАУЗЫ_СТОРОЖА[к["попыток"] - 1]
            к["состояние"] = "ждёт повтора"
            к["повтор_после"] = time.time() + пауза * 60
            зд.update({"gotovo": False, "etap": f"сбой связи, продолжу через {пауза} мин"})
        try:
            _записать(номер, к)
            if к["состояние"] == "сбой":   # метку снимаем ПОСЛЕ карточки: умрём между ними — сторож увидит «сбой»
                _открыт(номер, False)
        except Exception as e2:
            print(f"срок {номер}: карточка не записалась: {e2}")
    finally:
        with _замок:
            _работают.discard(номер)
        # место освободилось — оплаченные заказы в очереди не ждут обхода сторожа (5 минут)
        threading.Thread(target=_обход, daemon=True).start()


def _пустить(номер, к):
    """Запустить поток по заказу, если он ещё не идёт и есть место. → запущен ли."""
    with _замок:
        if номер in _работают or len(_работают) >= ОДНОВРЕМЕННО:
            return False
        _работают.add(номер)
    threading.Thread(target=_в_фоне, args=(номер, к), daemon=True).start()
    return True


def _обход():
    """Сторож: неоконченные заказы из облака — продолжить. «В работе» без живого потока значит,
    что сервер перезапускался посреди работы."""
    try:
        from engine import arhiv as A
        номера = [к.split("/")[-1] for к in A.перечислить(_префикс() + "/открытые/")]
        номера = [н for н in номера if _НОМЕР.fullmatch(н)]
    except Exception as e:
        print(f"сторож: список заказов недоступен: {e}")
        return
    сейчас = time.time()
    for номер in номера:
        if номер in _работают:
            continue
        к = _карточка(номер)
        if not к:
            continue
        с = к.get("состояние")
        if с == "в работе":
            if сейчас - к.get("обновлён", 0) < АРЕНДА:
                continue   # работник, возможно, жив в другом процессе (заливка с перекрытием) — ждём аренду
            # работник умер посреди заказа (перезапуск, нехватка памяти) — это тоже попытка:
            # иначе заказ, который роняет процесс, перезапускался бы вечно
            к["попыток"] = к.get("попыток", 0) + 1
            if к["попыток"] > len(ПАУЗЫ_СТОРОЖА):
                к["состояние"], к["ошибка"] = "сбой", к.get("ошибка") or "работник умирал на каждой попытке"
                try:
                    _записать(номер, к)
                    _открыт(номер, False)
                except Exception as e:
                    print(f"сторож: {номер} не записался: {e}")
                _в_телеграм(f"⚠️ {НАЗВАНИЕ.get(к.get('tarif'), 'Гороскоп')} {номер} не собрался: работник умирал на каждой попытке.")
                continue
        if с in ("в работе", "в очереди") or (с == "ждёт повтора" and сейчас >= к.get("повтор_после", 0)):
            if _пустить(номер, к):
                print(f"сторож: продолжаю заказ {номер} ({к.get('tarif')}, попыток {к.get('попыток', 0)})")


def _сторож():
    time.sleep(ПЕРВЫЙ_ОБХОД)
    while True:
        try:
            _обход()
        except Exception as e:
            print(f"сторож: обход сорвался: {e}")
        time.sleep(ОБХОД)


threading.Thread(target=_сторож, daemon=True, name="сторож-сроков").start()


@роутер.post("/api/srok/zapustit")
async def zapustit(request: Request):
    try:
        з = await request.json()
        тариф = str(з.get("tarif") or "")
        ш = round(float(з.get("lat")), 2)
        д = round(float(з.get("lon")), 2)
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    if тариф not in ТАРИФЫ:
        return JSONResponse({"ok": False, "reason": "bad_tarif"}, status_code=400)
    if not ПАРОЛЬ or not secrets.compare_digest(str(з.get("klyuch") or "").encode(), ПАРОЛЬ.encode()):
        await asyncio.sleep(1)   # как у /login: подбор пароля через этот адрес — не быстрее раза в секунду
        return JSONResponse({"ok": False, "reason": "locked"}, status_code=403)
    if not (math.isfinite(ш) and math.isfinite(д)) or abs(ш) > 90 or abs(д) > 180:
        return JSONResponse({"ok": False, "reason": "bad_coords"}, status_code=400)
    try:
        пояс = float(з.get("tz") or 0)
        if not math.isfinite(пояс) or abs(пояс) > 14:
            пояс = 0
        пояс = int(пояс) if пояс == int(пояс) else пояс
    except (TypeError, ValueError):
        пояс = 0
    iso = з.get("iso")
    try:
        момент = (datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc)
                  if iso else datetime.now(timezone.utc))
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_time"}, status_code=400)
    # чистка памяти: готовые задачи старше суток (в облаке карточка и итог остаются)
    сейчас = time.time()
    for н in [н for н, т in ЗАДАЧИ.items() if т.get("gotovo") and сейчас - т.get("когда", 0) > 86400]:
        ЗАДАЧИ.pop(н, None)
    номер = uuid.uuid4().hex[:16]
    к = {"tarif": тариф, "момент": момент.replace(microsecond=0).isoformat(), "ш": ш, "д": д, "пояс": пояс,
         "имя": str(з.get("imya") or "гость")[:40], "состояние": "в работе", "попыток": 0,
         "создан": сейчас}
    with _замок:   # место бронируем сразу: сторож не перехватит свежий заказ, двое не займут одно место
        if len(_работают) >= ОДНОВРЕМЕННО:
            return JSONResponse({"ok": False, "reason": "busy"}, status_code=429)
        _работают.add(номер)
    ЗАДАЧИ[номер] = {"gotovo": False, "etap": "поставлено в работу", "когда": сейчас, "tarif": тариф}
    try:   # карточка и метка — до начала работы: перезапуск их не потеряет
        _записать(номер, к)
        _открыт(номер, True)
    except Exception as e:   # облако не приняло карточку — без неё сторож заказ не спасёт, не берём
        print(f"срок {номер}: карточка не записалась: {e}")
        with _замок:
            _работают.discard(номер)
        ЗАДАЧИ.pop(номер, None)
        return JSONResponse({"ok": False, "reason": "busy"}, status_code=503)
    threading.Thread(target=_в_фоне, args=(номер, к), daemon=True).start()
    return {"ok": True, "nomer": номер, "tarif": тариф}


def _из_облака(номер):
    """Задачи нет в памяти (сервер перезапускался) — смотрим карточку в облаке."""
    к = _карточка(номер)
    if not к:
        return None
    с = к.get("состояние")
    if с == "готово":
        from engine import arhiv as A
        html = A._взять(f"{_префикс()}/{номер}/итог.html") or ""
        if html:   # в память не кладём: книга года большая, а чистка памяти идёт только при новых заказах
            return {"gotovo": True, "html": html, "imya_fayla": к.get("имя_файла"), "etap": "готово"}
    if с == "сбой":
        return {"gotovo": True, "oshibka": к.get("ошибка", "сбой")}
    if с == "в очереди":
        return {"gotovo": False, "etap": "в очереди — начну, как только закончу предыдущий гороскоп"}
    return {"gotovo": False, "etap": "продолжаю после перерыва" if с == "в работе" else "сбой связи, скоро продолжу"}


@роутер.get("/api/srok/status")
def status(nomer: str = Query(...)):
    if not _НОМЕР.fullmatch(nomer or ""):
        return JSONResponse({"ok": False, "reason": "no_task"}, status_code=404)
    зд = ЗАДАЧИ.get(nomer) or _из_облака(nomer)
    if зд is None:
        return JSONResponse({"ok": False, "reason": "no_task"}, status_code=404)
    if not зд.get("gotovo"):
        return {"ok": True, "gotovo": False, "etap": зд.get("etap", "")}
    if зд.get("oshibka"):
        return {"ok": True, "gotovo": True, "oshibka": зд["oshibka"]}
    return {"ok": True, "gotovo": True, "imya_fayla": зд.get("imya_fayla"), "html": зд.get("html", "")}


@роутер.get("/api/srok/fayl")
def fayl(nomer: str = Query(...)):
    from urllib.parse import quote as _q
    if not _НОМЕР.fullmatch(nomer or ""):
        return JSONResponse({"ok": False, "reason": "not_ready"}, status_code=404)
    зд = ЗАДАЧИ.get(nomer) or _из_облака(nomer)
    if not зд or not зд.get("gotovo") or not зд.get("html"):
        return JSONResponse({"ok": False, "reason": "not_ready"}, status_code=404)
    return Response(content=зд["html"], media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + _q(зд["imya_fayla"])})
