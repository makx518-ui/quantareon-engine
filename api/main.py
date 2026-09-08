"""
api/main.py — FastAPI сервер Квантареон (Астро-фрактал)

Три эндпоинта:
  POST /natal    — натальная карта
  POST /cascade  — фрактальный расклад планеты
  GET  /transit  — текущие позиции планет
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import swisseph as swe

# Добавляем корень проекта в path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from engine.natal import calculate_natal, format_natal
from engine.micro_cascade import cascade_from_absolute
from engine.cascade_assembler import assemble
from engine.degree_parser import DegreeDatabase

# ============================================================
# ПРИЛОЖЕНИЕ
# ============================================================

app = FastAPI(
    title="Квантареон — Астро-фрактал",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ПАРОЛЬ И РАЗДАЧА ФРОНТЕНДА  (для Render)
# ============================================================
import os, secrets, time
from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

PASSWORD = os.environ.get("QUANTAREON_PASSWORD", "")   # задаётся в настройках Render
COOKIE   = "qtok"
DAYS     = 180
_VALID   = set()

def _ok(tok):
    return (not PASSWORD) or (tok in _VALID)

LOGIN_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>КВАНТАРЕОН</title>
<style>
  html,body{margin:0;height:100%;background:#0b0d10;color:#e6e1d6;
    font-family:Georgia,serif;display:flex;align-items:center;justify-content:center}
  .box{text-align:center;padding:2rem}
  h1{font-family:Inter,-apple-system,sans-serif;font-size:.85rem;letter-spacing:.28em;font-weight:700;
     background:linear-gradient(100deg,#8a6212,#e8c464 38%,#fff6d5 46%,#e8c464 58%,#8a6212);
     -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
     margin:0 0 2rem}
  input{background:#14171c;border:1px solid #43474f;color:#e6e1d6;padding:.8rem 1rem;
    border-radius:6px;font-size:1rem;width:220px;font-family:Georgia,serif;text-align:center}
  input:focus{outline:none;border-color:#e8bd6a}
  button{margin-top:1rem;display:block;width:100%;background:none;border:1px solid #e8bd6a;
    color:#e8bd6a;padding:.7rem;border-radius:6px;cursor:pointer;font-size:.9rem;
    font-family:Inter,-apple-system,sans-serif;letter-spacing:.1em}
  button:hover{background:rgba(232,189,106,.12)}
  .err{color:#e06050;font-size:.85rem;margin-top:1rem;min-height:1.2em;font-family:Georgia,serif}
</style></head><body>
<div class="box">
  <h1>QUANTAREON.</h1>
  <form method="post" action="/login">
    <input name="p" type="password" placeholder="пароль" autofocus>
    <button type="submit">Войти</button>
  </form>
  <div class="err">__ERR__</div>
</div></body></html>"""

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return LOGIN_HTML.replace("__ERR__", "")

@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    if PASSWORD and form.get("p") != PASSWORD:
        time.sleep(1)
        return HTMLResponse(LOGIN_HTML.replace("__ERR__", "не тот пароль"), status_code=401)
    tok = secrets.token_urlsafe(24); _VALID.add(tok)
    r = RedirectResponse("/", status_code=303)
    sec = request.url.scheme == "https"
    r.set_cookie(COOKIE, tok, max_age=DAYS*86400, httponly=True, samesite="lax", secure=sec)
    return r

# 📊 Адреса счётчика посещений, которые проходную минуют.
# ПОЧЕМУ ЭТО БЕЗОПАСНО:
#   /api/hit  — отметка захода. Её и должен звать сайт от лица любого
#               посетителя, пароля у него нет и быть не может. Ничего не
#               отдаёт наружу: в ответ приходит прозрачная точка 1×1.
#   /stats и /api/stats — просмотр цифр. Пароль движка тут не нужен,
#               потому что у них СВОЯ защита: без верного STATS_KEY
#               отвечают отказом. Проверено — и без ключа, и с чужим.
_СЧЁТЧИК_БЕЗ_ПАРОЛЯ = ("/api/hit", "/stats", "/api/stats")

# ✉️ Адреса отправки писем, которые проходную минуют.
# ПОЧЕМУ ЭТО БЕЗОПАСНО:
#   /api/send-key — сюда стучится Cloudflare, когда покупатель оплатил.
#                   Пароля движка у него нет и быть не может. Зато у самой
#                   страницы СВОЯ защита: без верного MAIL_SECRET отвечает
#                   отказом, и вид почты с ключом проверяется строго.
#   /api/mail-health — проверка, настроено ли всё. Паролей наружу не отдаёт,
#                   только «задано или нет».
_ПОЧТА_БЕЗ_ПАРОЛЯ = ("/api/send-key", "/api/mail-health")


@app.middleware("http")
async def gate(request: Request, call_next):
    p = request.url.path
    if p.startswith(_СЧЁТЧИК_БЕЗ_ПАРОЛЯ) or p.startswith(_ПОЧТА_БЕЗ_ПАРОЛЯ):
        return await call_next(request)
    if p.startswith("/login") or p.startswith("/health") or p.startswith("/chat") or p.startswith("/transcribe") or p.startswith("/tts") or p.startswith("/quantareon-chat.js") or p.startswith("/ws/voice") or p.startswith("/api/greeting") or p.startswith("/api/voice-health") or p.startswith("/api/voice-model") or p.startswith("/api/voice-image-mode"):
        return await call_next(request)
    if not _ok(request.cookies.get(COOKIE)):
        if request.method == "GET" and ("text/html" in request.headers.get("accept","")):
            return RedirectResponse("/login", status_code=303)
        return Response("нужен пароль", status_code=401)
    return await call_next(request)

@app.get("/health")
def health():
    return {"ok": True}

# ============================================================
# 🎙 ГОЛОСОВОЙ КВАНТАРЕОН (перенесён с Амверы 01.08.2026)
# Даёт: WS /ws/voice · GET /api/greeting · GET /api/voice-health · GET+POST /api/voice-model
# ============================================================
try:
    from voice import router as voice_router, warm_greetings
    app.include_router(voice_router)

    @app.on_event("startup")
    async def _warm_voice_greetings():
        await warm_greetings()

    print("🎙 Голосовой Квантареон: подключён")
except Exception as _e:
    print(f"⚠️ Голосовой модуль не подключился: {_e}")

# ============================================================
# 📊 СЧЁТЧИК ПОСЕЩЕНИЙ САЙТА (08.08.2026)
# Даёт: GET /api/hit — тихая отметка захода со страницы сайта
#       GET /stats?key=… — страница со сводкой, только по ключу
#       GET /api/stats?key=… — те же цифры в чистом виде
# Хранит в Cloudflare R2 (там же, где музыка), по файлу на день.
# Ключи: R2_ACCOUNT_ID · R2_ACCESS_KEY · R2_SECRET_KEY · R2_BUCKET · STATS_KEY
# Подключено так же, как голос: если модуль не встанет — движок живёт дальше.
# ============================================================
# Ищем stats.py и в корне, и рядом с этим файлом — чтобы не зависело
# от того, куда он лёг при заливке.
sys.path.insert(0, str(Path(__file__).parent))
try:
    import stats as _stats
    app.include_router(_stats.router)
    print("📊 Счётчик посещений: подключён")
except Exception as _e:
    print(f"⚠️ Счётчик посещений не подключился: {type(_e).__name__}: {_e}")

# ============================================================
# ✉️ ПИСЬМО С КЛЮЧОМ ДЛЯ LUCK FORECAST (20.08.2026)
# Даёт: POST /api/send-key — Cloudflare зовёт сюда после оплаты
#       GET  /api/mail-health — настроено ли всё
# Шлёт через тот же Gmail, что и Оракул, паролем приложения.
# Почему тут, а не на Cloudflare: тот умеет только веб-обращения,
# а обычную почтовую связь — нет. Render умеет.
# Ключи: SMTP_PASS · SMTP_USER · MAIL_SECRET (плюс SMTP_HOST, SMTP_PORT,
# MAIL_FROM — у них есть разумные значения по умолчанию).
# Подключено так же, как счётчик: не встанет — движок живёт дальше.
# ============================================================
try:
    import pochta as _pochta
    app.include_router(_pochta.роутер)
    print("✉️ Отправка ключей: подключена")
except Exception as _e:
    print(f"⚠️ Отправка ключей не подключилась: {type(_e).__name__}: {_e}")


FRONT = ROOT / "frontend"

@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(FRONT / "index.html", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@app.get("/prognoz", response_class=HTMLResponse)
def prognoz_page():
    """Страница режима «Прогноз на день» — отдельная от карты."""
    return FileResponse(FRONT / "prognoz.html", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    })


# ═══════════════════════════════════════════════════════════════════
#  РАСЧЁТ КАРТ И ИСТОРИЯ · добавлено 05.09.2026
#  Одна точка входа на все заказы, архив карт, страница истории.
# ═══════════════════════════════════════════════════════════════════

from api_vhod import (расчёт, карта_файлом, история,
                      отдать, удалить_расчёт, очистить_историю, удалить_файл)


# ── РАСЧЁТ КАРТЫ ────────────────────────────────────────────────
# Одна точка на все заказы: натал, транзиты, соляр, день, синастрия.
# Машина сама решает — есть время или нет, дома или от Солнца.

@app.post("/api/raschet")
async def api_raschet(запрос: dict):
    """Считает карту и кладёт кухню в архив."""
    try:
        return расчёт(запрос)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/karta")
async def api_karta_klientu(тело: dict):
    """Собирает красивый HTML для клиента.
    тело: {"zapros": {...}, "razdely": [["Заголовок","текст"], ...]}"""
    try:
        разделы = [(з, т) for з, т in тело.get("razdely", [])]
        return карта_файлом(тело["zapros"], разделы)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── ИСТОРИЯ ─────────────────────────────────────────────────────

@app.get("/istoriya", response_class=HTMLResponse)
def stranica_istorii():
    """Страница списка карт."""
    return FileResponse(FRONT / "istoriya.html", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    })


@app.get("/api/istoriya")
def api_istoriya():
    """Все расчёты: пара из карты и кухни на каждый."""
    return история()


ВИДЫ_КАРТ = {"natal": "натальная карта", "kosmogramma": "космограмма",
             "solyar": "карта года", "tranzity": "где ты сейчас",
             "den": "прогноз на день", "sinastriya": "синастрия"}


@app.get("/api/karta")
def api_otdat_kartu(f: str = Query(...), skachat: int = Query(0)):
    """HTML карты клиента по относительному пути.
    08.09: skachat=1 — отдать файлом; вид тот же, стили лежат внутри файла,
    поэтому клиент открывает его где угодно и без интернета."""
    т = отдать(f)
    if т is None:
        raise HTTPException(status_code=404, detail="карта не найдена")
    if skachat:
        import re as _re
        from urllib.parse import quote as _q
        куски = f.split("/")
        имя_файла = куски[-1]
        m = _re.match(r"(\d{4})-(\d\d)-(\d\d)_\d\d-\d\d-\d\d_(\w+)\.html", имя_файла)
        if m:
            кто = куски[2] if len(куски) > 2 else "карта"
            вид = ВИДЫ_КАРТ.get(m.group(4), "карта")
            имя_файла = f"{кто} · {вид} · {m.group(3)}.{m.group(2)}.{m.group(1)}.html"
        return Response(content=т, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition":
                                 "attachment; filename*=UTF-8''" + _q(имя_файла)})
    return HTMLResponse(т)


@app.post("/api/prochitat")
async def api_prochitat(тело: dict):
    """08.09 · ЧИТАТЕЛЬ: машина считает, модель оживляет, карта ложится в архив.

    тело: {"zapros": {imya, zakaz, data, vremya, shirota, dolgota, gmt, mesto, seychas:{...}},
           "god_solyara": 2026, "sobrat_kartu": true}
    Возвращает разделы, готовый html и путь в архиве.
    """
    з = тело.get("zapros") or {}
    if not з.get("data"):
        raise HTTPException(status_code=400, detail="нужна дата рождения")
    from engine import chitatel as _ч
    try:
        # 1 · машина считает
        з2 = dict(з)
        if тело.get("god_solyara"):
            з2["god_solyara"] = тело["god_solyara"]
        посчитано = расчёт(з2)
        заказ = з.get("zakaz", "natal")
        без_времени = not (з.get("vremya") or "").strip()
        вид = "kosmogramma" if (заказ == "natal" and без_времени) else заказ
        # 2 · читатель оживляет
        итог = _ч.прочитать(
            посчитано.get("sloy1", ""), посчитано.get("sloy2"), заказ=вид,
            имя=з.get("imya") or "человек",
            данные_рождения={"дата": з.get("data"), "время": з.get("vremya"), "место": з.get("mesto")},
            полочка=посчитано.get("polochka_ii"))
        ответ = {"razdely": итог["razdely"], "razbor": итог["razbor"]}
        # 3 · собрать карту и положить в архив
        if тело.get("sobrat_kartu", True):
            карта = карта_файлом(з, [(з_, т_) for з_, т_ in итог["razdely"]])
            ответ.update({"fayl": карта.get("fayl"), "imya_fayla": карта.get("imya_fayla")})
        return ответ
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"читатель: {e}")


@app.post("/api/karta/sohranit")
async def api_sohranit_kartu(тело: dict):
    """08.09: правка карты прямо в браузере.
    Прежняя версия кладётся рядом с меткой времени — вернуть можно всегда."""
    путь = (тело.get("f") or "").strip()
    html = тело.get("html") or ""
    if not путь or "<html" not in html:
        raise HTTPException(status_code=400, detail="нужен путь и html")
    from engine import arhiv as _arhiv
    старое = отдать(путь)
    if старое is None:
        raise HTTPException(status_code=404, detail="карта не найдена")
    # панель правки в файл не сохраняется ни при каких условиях —
    # клиент не должен получить возможность править свой гороскоп
    import re as _re
    html = _re.sub(r'<div class="pravka">.*?</div>\s*<script>.*?</script>', "", html, flags=_re.S)
    html = _re.sub(r'<div class="pravka">.*?</div>', "", html, flags=_re.S)
    html = html.replace(' contenteditable="true"', "").replace(' contenteditable="false"', "")
    html = html.replace(' class="pravim"', "").replace('<body class="pravim">', "<body>")
    from datetime import datetime as _dt
    метка = _dt.utcnow().strftime("%Y%m%d-%H%M%S")
    было = путь.replace(".html", f"__было-{метка}.html")
    try:
        _arhiv._положить(было, старое, "text/html; charset=utf-8")
        _arhiv._положить(путь, html, "text/html; charset=utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "fayl": путь, "prezhnyaya": было}


@app.get("/api/kuhnya")
def api_otdat_kuhnyu(f: str = Query(...)):
    """Механика расклада — для ученика."""
    т = отдать(f)
    if т is None:
        raise HTTPException(status_code=404, detail="механика не найдена")
    return Response(т, media_type="application/json; charset=utf-8")


@app.get("/istoriya/karta", response_class=HTMLResponse)
def prosmotr_karty(f: str = Query(...)):
    """Карта отдельной страницей — с панелью правки (её нет в файле клиента)."""
    т = отдать(f)
    if т is None:
        raise HTTPException(status_code=404, detail="карта не найдена")
    if 'class="pravka"' not in т:
        from engine.karta_html import ПАНЕЛЬ_ПРАВКИ
        т = т.replace("</body>", ПАНЕЛЬ_ПРАВКИ + "\n</body>")
    return HTMLResponse(т)


@app.get("/istoriya/kuhnya", response_class=HTMLResponse)
def prosmotr_kuhni(f: str = Query(...)):
    """Механика отдельной страницей — простым видом."""
    т = отдать(f)
    if т is None:
        raise HTTPException(status_code=404, detail="механика не найдена")
    экран = ("<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
             "<meta name='viewport' content='width=device-width,initial-scale=1'>"
             "<title>Механика расклада</title><style>"
             "body{background:#0b0f18;color:#d9d2c4;font:13px/1.7 ui-monospace,"
             "Menlo,Consolas,monospace;padding:56px 18px 60px;margin:0}"
             "a.nazad{position:fixed;top:14px;left:16px;padding:7px 13px;"
             "border:1px solid rgba(255,255,255,.16);border-radius:9px;"
             "background:rgba(20,24,36,.85);color:#d9d2c4;text-decoration:none;"
             "font:13px system-ui}a.nazad:hover{color:#E8B23A;"
             "border-color:rgba(232,178,58,.5)}"
             "pre{white-space:pre-wrap;word-break:break-word;max-width:1000px;margin:0 auto}"
             "</style></head><body>"
             "<a class='nazad' href='/istoriya'>← к истории</a><pre>")
    import html as _h
    return HTMLResponse(экран + _h.escape(т) + "</pre></body></html>")


@app.post("/api/istoriya/udalit")
async def api_udalit(тело: dict):
    """Убирает расчёт целиком — и карту, и кухню."""
    return удалить_расчёт(тело.get("id", ""))


@app.post("/api/istoriya/udalit-fayl")
async def api_udalit_fayl(тело: dict):
    """Убирает один файл — карту или механику по отдельности."""
    return удалить_файл(тело.get("fayl", ""))


@app.post("/api/istoriya/ochistit")
async def api_ochistit():
    """Всё под корень."""
    return очистить_историю()


@app.get("/cities.json")
def cities_json():
    """База городов (страна, название, широта, долгота, часовая зона) —
    та же, что на странице мухурты сайта. Нужна окнам ввода прогноза."""
    from fastapi.responses import Response
    п = FRONT / "cities.json"
    if п.exists():
        return Response(content=п.read_text(encoding="utf-8"),
                        media_type="application/json",
                        headers={"Cache-Control": "public, max-age=86400"})
    return Response(content="[]", media_type="application/json")


# Отдача AstroChart.js
@app.get("/astrochart.js")
async def serve_astrochart():
    from fastapi.responses import Response
    js_path = ROOT / "frontend" / "astrochart.js"
    if js_path.exists():
        return Response(content=js_path.read_text(encoding='utf-8'), media_type="application/javascript")
    return Response(content="// astrochart.js not found", media_type="application/javascript")

# Отдача виджета чата
@app.get("/quantareon-chat.js")
async def serve_chat_widget():
    from fastapi.responses import Response
    js_path = ROOT / "quantareon-chat.js"
    if js_path.exists():
        return Response(content=js_path.read_text(encoding='utf-8'), media_type="application/javascript")
    return Response(content="// quantareon-chat.js not found", media_type="application/javascript")


# Главная страница
@app.get("/", response_class=None)
async def index():
    from fastapi.responses import HTMLResponse
    html_path = ROOT / "frontend" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>Квантареон</h1><p>frontend/index.html не найден</p>")


def _crop_svg_to_chart(svg_text, data_only=False, cut_override=None):
    # Вырезает только таблицы из SVG kerykeion (без круга)
    idx = svg_text.find('viewBox=')
    if idx == -1:
        return svg_text
    q = svg_text[idx + 8]  # quote char: ' or "
    s = idx + 9
    e = svg_text.find(q, s)
    if e == -1:
        return svg_text
    vb = svg_text[s:e]
    parts = vb.split()
    if len(parts) != 4:
        return svg_text
    ow = int(float(parts[2]))
    oh = int(float(parts[3]))
    cut = cut_override if cut_override is not None else oh + 20  # правый край круга; режем сразу за ним
    tw = ow - cut
    if tw < 50:
        return ''
    out_h = 295 if data_only else oh  # data_only: только блок данных, без аспектов
    new_vb = str(cut) + ' ' + parts[1] + ' ' + str(tw) + ' ' + str(out_h)
    out = svg_text[:s] + new_vb + svg_text[e:]
    # реальный размер вместо width/height='100%' (иначе SVG раздувается)
    out = out.replace("width='100%'", "width='" + str(tw) + "'", 1)
    out = out.replace("height='100%'", "height='" + str(out_h) + "'", 1)
    return out


# База градусов — загружаем один раз
_db = None


def get_db() -> DegreeDatabase:
    global _db
    if _db is None:
        _db = DegreeDatabase(str(ROOT / "data" / "gradusy_360_baza.txt"))
    return _db


# ============================================================
# ГЕОКОДИНГ (город → координаты + TZ)
# ============================================================

# ===== GeoNames fuzzy геокодер (перенесён из Oracle) =====
import os as _os_geo
_COUNTRY_ISO = {
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ",
    "andorra": "AD", "angola": "AO", "antigua and barbuda": "AG",
    "argentina": "AR", "armenia": "AM", "australia": "AU",
    "austria": "AT", "azerbaijan": "AZ", "bahamas": "BS",
    "bahrain": "BH", "bangladesh": "BD", "barbados": "BB",
    "belarus": "BY", "belgium": "BE", "belize": "BZ",
    "benin": "BJ", "bhutan": "BT", "bolivia": "BO",
    "bolivia, plurinational state of": "BO", "bosnia and herzegovina": "BA", "botswana": "BW",
    "brazil": "BR", "britain": "GB", "brunei darussalam": "BN",
    "bulgaria": "BG", "burkina faso": "BF", "burundi": "BI",
    "cabo verde": "CV", "cambodia": "KH", "cameroon": "CM",
    "canada": "CA", "central african republic": "CF", "chad": "TD",
    "chile": "CL", "china": "CN", "colombia": "CO",
    "comoros": "KM", "congo": "CD", "congo, democratic republic of the": "CD",
    "costa rica": "CR", "croatia": "HR", "cuba": "CU",
    "cyprus": "CY", "czech republic": "CZ", "czechia": "CZ",
    "côte d'ivoire": "CI", "denmark": "DK", "djibouti": "DJ",
    "dominica": "DM", "dominican republic": "DO", "ecuador": "EC",
    "egypt": "EG", "el salvador": "SV", "england": "GB",
    "equatorial guinea": "GQ", "eritrea": "ER", "estonia": "EE",
    "eswatini": "SZ", "ethiopia": "ET", "fiji": "FJ",
    "finland": "FI", "france": "FR", "gabon": "GA",
    "gambia": "GM", "georgia": "GE", "germany": "DE",
    "ghana": "GH", "great britain": "GB", "greece": "GR",
    "grenada": "GD", "guatemala": "GT", "guinea": "GN",
    "guinea-bissau": "GW", "guyana": "GY", "haiti": "HT",
    "honduras": "HN", "hungary": "HU", "iceland": "IS",
    "india": "IN", "indonesia": "ID", "iran": "IR",
    "iran, islamic republic of": "IR", "iraq": "IQ", "ireland": "IE",
    "israel": "IL", "italy": "IT", "jamaica": "JM",
    "japan": "JP", "jordan": "JO", "kazakhstan": "KZ",
    "kenya": "KE", "kiribati": "KI", "korea, democratic people's republic of": "KP",
    "korea, republic of": "KR", "kuwait": "KW", "kyrgyzstan": "KG",
    "lao people's democratic republic": "LA", "laos": "LA", "latvia": "LV",
    "lebanon": "LB", "lesotho": "LS", "liberia": "LR",
    "libya": "LY", "liechtenstein": "LI", "lithuania": "LT",
    "luxembourg": "LU", "madagascar": "MG", "malawi": "MW",
    "malaysia": "MY", "maldives": "MV", "mali": "ML",
    "malta": "MT", "marshall islands": "MH", "mauritania": "MR",
    "mauritius": "MU", "mexico": "MX", "micronesia": "FM",
    "micronesia, federated states of": "FM", "moldova": "MD", "moldova, republic of": "MD",
    "monaco": "MC", "mongolia": "MN", "montenegro": "ME",
    "morocco": "MA", "mozambique": "MZ", "myanmar": "MM",
    "namibia": "NA", "nauru": "NR", "nepal": "NP",
    "netherlands": "NL", "new zealand": "NZ", "nicaragua": "NI",
    "niger": "NE", "nigeria": "NG", "north korea": "KP",
    "north macedonia": "MK", "norway": "NO", "oman": "OM",
    "pakistan": "PK", "palau": "PW", "panama": "PA",
    "papua new guinea": "PG", "paraguay": "PY", "peru": "PE",
    "philippines": "PH", "poland": "PL", "portugal": "PT",
    "qatar": "QA", "romania": "RO", "russia": "RU",
    "russian federation": "RU", "rwanda": "RW", "saint kitts and nevis": "KN",
    "saint lucia": "LC", "saint vincent and the grenadines": "VC", "samoa": "WS",
    "san marino": "SM", "sao tome and principe": "ST", "saudi arabia": "SA",
    "senegal": "SN", "serbia": "RS", "seychelles": "SC",
    "sierra leone": "SL", "singapore": "SG", "slovakia": "SK",
    "slovenia": "SI", "solomon islands": "SB", "somalia": "SO",
    "south africa": "ZA", "south korea": "KR", "south sudan": "SS",
    "spain": "ES", "sri lanka": "LK", "sudan": "SD",
    "suriname": "SR", "sweden": "SE", "switzerland": "CH",
    "syria": "SY", "syrian arab republic": "SY", "tajikistan": "TJ",
    "tanzania": "TZ", "tanzania, united republic of": "TZ", "thailand": "TH",
    "timor-leste": "TL", "togo": "TG", "tonga": "TO",
    "trinidad and tobago": "TT", "tunisia": "TN", "turkmenistan": "TM",
    "tuvalu": "TV", "türkiye": "TR", "uae": "AE",
    "uganda": "UG", "uk": "GB", "ukraine": "UA",
    "united arab emirates": "AE", "united kingdom of great britain and northern ireland": "GB", "united states": "US",
    "united states of america": "US", "uruguay": "UY", "usa": "US",
    "uzbekistan": "UZ", "vanuatu": "VU", "venezuela": "VE",
    "venezuela, bolivarian republic of": "VE", "viet nam": "VN", "vietnam": "VN",
    "yemen": "YE", "zambia": "ZM", "zimbabwe": "ZW",
    "австралия": "AU", "австрия": "AT", "азербайджан": "AZ",
    "албания": "AL", "алжир": "DZ", "америка": "US",
    "англия": "GB", "ангола": "AO", "андорра": "AD",
    "антигуа и барбуда": "AG", "аргентина": "AR", "армения": "AM",
    "афганистан": "AF", "багамские острова": "BS", "бангладеш": "BD",
    "барбадос": "BB", "бахрейн": "BH", "беларусь": "BY",
    "белиз": "BZ", "белоруссия": "BY", "бельгия": "BE",
    "бенин": "BJ", "болгария": "BG", "боливия": "BO",
    "босния и герцеговина": "BA", "ботсвана": "BW", "бразилия": "BR",
    "бруней": "BN", "буркина-фасо": "BF", "бурунди": "BI",
    "бутан": "BT", "вануату": "VU", "великобритания": "GB",
    "венгрия": "HU", "венесуэла": "VE", "восточный тимор": "TL",
    "вьетнам": "VN", "габон": "GA", "гаити": "HT",
    "гайана": "GY", "гамбия": "GM", "гана": "GH",
    "гватемала": "GT", "гвинея": "GN", "гвинея-бисау": "GW",
    "германия": "DE", "гондурас": "HN", "гренада": "GD",
    "греция": "GR", "грузия": "GE", "дания": "DK",
    "джибути": "DJ", "доминика": "DM", "доминиканская республика": "DO",
    "др конго": "CD", "египет": "EG", "замбия": "ZM",
    "зимбабве": "ZW", "израиль": "IL", "индия": "IN",
    "индонезия": "ID", "иордания": "JO", "ирак": "IQ",
    "иран": "IR", "ирландия": "IE", "исландия": "IS",
    "испания": "ES", "италия": "IT", "йемен": "YE",
    "кабо-верде": "CV", "казахстан": "KZ", "камбоджа": "KH",
    "камерун": "CM", "канада": "CA", "катар": "QA",
    "кения": "KE", "кипр": "CY", "киргизия": "KG",
    "кирибати": "KI", "китай": "CN", "китай (китайская народная республика)": "CN",
    "кндр": "KP", "кндр (корейская народно-демократическая республика)": "KP", "колумбия": "CO",
    "коморы": "KM", "коста-рика": "CR", "кот-д’ивуар": "CI",
    "куба": "CU", "кувейт": "KW", "кыргызстан": "KG",
    "лаос": "LA", "латвия": "LV", "лесото": "LS",
    "либерия": "LR", "ливан": "LB", "ливия": "LY",
    "литва": "LT", "лихтенштейн": "LI", "люксембург": "LU",
    "маврикий": "MU", "мавритания": "MR", "мадагаскар": "MG",
    "малави": "MW", "малайзия": "MY", "мали": "ML",
    "мальдивы": "MV", "мальта": "MT", "марокко": "MA",
    "маршалловы острова": "MH", "мексика": "MX", "микронезия": "FM",
    "мозамбик": "MZ", "молдавия": "MD", "молдова": "MD",
    "монако": "MC", "монголия": "MN", "мьянма": "MM",
    "намибия": "NA", "науру": "NR", "непал": "NP",
    "нигер": "NE", "нигерия": "NG", "нидерланды": "NL",
    "никарагуа": "NI", "новая зеландия": "NZ", "норвегия": "NO",
    "оаэ": "AE", "оман": "OM", "пакистан": "PK",
    "палау": "PW", "панама": "PA", "папуа — новая гвинея": "PG",
    "парагвай": "PY", "перу": "PE", "польша": "PL",
    "португалия": "PT", "республика конго": "CG", "республика корея": "KR",
    "россия": "RU", "руанда": "RW", "румыния": "RO",
    "сальвадор": "SV", "самоа": "WS", "сан-марино": "SM",
    "сан-томе и принсипи": "ST", "саудовская аравия": "SA", "северная корея": "KP",
    "северная македония": "MK", "сейшельские острова": "SC", "сенегал": "SN",
    "сент-винсент и гренадины": "VC", "сент-китс и невис": "KN", "сент-люсия": "LC",
    "сербия": "RS", "сингапур": "SG", "сирия": "SY",
    "словакия": "SK", "словения": "SI", "соломоновы острова": "SB",
    "сомали": "SO", "судан": "SD", "суринам": "SR",
    "сша": "US", "сьерра-леоне": "SL", "таджикистан": "TJ",
    "таиланд": "TH", "танзания": "TZ", "того": "TG",
    "тонга": "TO", "тринидад и тобаго": "TT", "тувалу": "TV",
    "тунис": "TN", "туркменистан": "TM", "турция": "TR",
    "уганда": "UG", "узбекистан": "UZ", "украина": "UA",
    "уругвай": "UY", "фиджи": "FJ", "филиппины": "PH",
    "финляндия": "FI", "франция": "FR", "хорватия": "HR",
    "цар": "CF", "чад": "TD", "черногория": "ME",
    "чехия": "CZ", "чили": "CL", "швейцария": "CH",
    "швеция": "SE", "шри-ланка": "LK", "эквадор": "EC",
    "экваториальная гвинея": "GQ", "эмираты": "AE", "эритрея": "ER",
    "эсватини": "SZ", "эстония": "EE", "эфиопия": "ET",
    "юар": "ZA", "южная корея": "KR", "южный судан": "SS",
    "ямайка": "JM", "япония": "JP",
}

def _translit_ru(s: str) -> str:
    """Кириллица → латиница (как в GeoNames). Для поиска мелких пунктов."""
    table = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
        'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
        'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya','-':' ',
    }
    return ''.join(table.get(c, c) for c in s.lower())

def _geonames_api_fuzzy(place_str: str, force_cc: str = None):
    """
    Прямой запрос к GeoNames API.
    Возвращает dict с найденным местом и списком кандидатов, или None.

    БЫЛО: q = raw.split(",")[0].split()[0] — бралось ТОЛЬКО ПЕРВОЕ СЛОВО.
    "Курган тюбе" -> искалось "Курган" -> находился кишлак Куйган в 45 км.
    Теперь ищется полное название.
    """
    _user = _os_geo.environ.get("GEONAMES_USERNAME", "vladm_oracle").strip()
    if not place_str or not _user:
        return None
    try:
        import urllib.request as _urlreq
        import urllib.parse as _urlparse
        import json as _json
        import difflib as _dl

        raw = place_str.strip()
        low = raw.lower()
        country_code = force_cc
        country_phrase = None
        for nm, cc in _COUNTRY_ISO.items():
            if low.endswith(nm):
                country_code = country_code or cc
                country_phrase = nm
                break

        # ИМЯ МЕСТА — всё до запятой целиком, а не первое слово.
        q = raw.split(",")[0].strip()
        for pref in ("с.", "п.", "г.", "пос.", "село", "посёлок", "поселок", "город", "деревня", "ст."):
            if q.lower().startswith(pref):
                q = q[len(pref):].strip()
                break
        if not q:
            return None

        # ОБЛАСТЬ — всё между запятыми, кроме страны
        parts = [p.strip() for p in raw.split(",")[1:]]
        if country_phrase and parts and parts[-1].lower().strip() == country_phrase:
            parts = parts[:-1]
        region_text = " ".join(parts).lower()
        for junk in ["область", "обл.", "обл", "район", "region", "oblast",
                     "край", "округ", "области", "."]:
            region_text = region_text.replace(junk, " ")
        region_text = " ".join(region_text.split())
        region_translit = _translit_ru(region_text) if region_text else ""

        rows = []
        # два захода: сначала точно, потом нечётко
        for fz in ("0.9", "0.6"):
            params = {"q": q, "fuzzy": fz, "maxRows": "20",
                      "featureClass": "P", "username": _user}
            if country_code:
                params["country"] = country_code
            url = "http://api.geonames.org/searchJSON?" + _urlparse.urlencode(params)
            req = _urlreq.Request(url, headers={"User-Agent": "Quantarion/1.0"})
            with _urlreq.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            rows = data.get("geonames") or []
            if rows:
                break
        if not rows:
            return None

        q_tr = (_translit_ru(q) or q).lower()

        def _admin_match(row):
            adm = (row.get("adminName1") or "").lower()
            if not adm or not (region_text or region_translit):
                return False
            for rt in (region_text, region_translit):
                if rt and (rt in adm or adm in rt):
                    return True
            words = (region_text + " " + region_translit).split()
            return any(w in adm for w in words if len(w) > 3)

        def _score(row):
            """Чем больше — тем вернее. Имя важнее населения."""
            nm = (row.get("name") or "").lower()
            best = 0.0
            for cand in {nm, (row.get("toponymName") or "").lower()}:
                if not cand:
                    continue
                best = max(best,
                           _dl.SequenceMatcher(None, q_tr, cand).ratio(),
                           _dl.SequenceMatcher(None, q.lower(), cand).ratio())
            s = best * 100                       # схожесть имени: 0..100
            if _admin_match(row):
                s += 40                          # совпала область
            pop = int(row.get("population") or 0)
            if pop > 0:
                s += min(pop / 5000.0, 10)       # населённость — слабый довесок
            return s

        ranked = sorted(rows, key=_score, reverse=True)
        hit = ranked[0]
        lat = float(hit["lat"])
        lng = float(hit["lng"])

        # Зона: сначала локально (timezonefinder — офлайн, лимитов нет),
        # GeoNames только запасным. Их timezone API упирается в суточный лимит
        # бесплатного аккаунта и молча отдаёт UTC -> GMT+0 вместо +6.
        tz = None
        try:
            from timezonefinder import TimezoneFinder
            tz = TimezoneFinder().timezone_at(lat=lat, lng=lng)
        except Exception:
            tz = None
        if not tz:
            try:
                tz_url = ("http://api.geonames.org/timezoneJSON?"
                          + _urlparse.urlencode({"lat": lat, "lng": lng, "username": _user}))
                tz_req = _urlreq.Request(tz_url, headers={"User-Agent": "Quantarion/1.0"})
                with _urlreq.urlopen(tz_req, timeout=8) as tz_resp:
                    tz_data = _json.loads(tz_resp.read().decode("utf-8"))
                tz = tz_data.get("timezoneId")
            except Exception:
                pass
        tz = tz or "UTC"

        def _brief(r):
            bits = [r.get("name") or "?"]
            if r.get("adminName1"):
                bits.append(r["adminName1"])
            if r.get("countryName"):
                bits.append(r["countryName"])
            return {
                "name": " · ".join(bits),
                "lat": round(float(r["lat"]), 6),
                "lng": round(float(r["lng"]), 6),
                "population": int(r.get("population") or 0),
                "score": round(_score(r), 1),
            }

        return {
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "tz": tz,
            "cc": (hit.get("countryCode") or "").upper(),
            "found": _brief(hit),
            "candidates": [_brief(r) for r in ranked[:6]],
        }
    except Exception:
        return None



def tz_offset_at(tz_name: str, on_date: Optional[str] = None) -> float:
    """Смещение зоны В УКАЗАННУЮ ДАТУ (не сегодня!).

    on_date: 'ГГГГ-ММ-ДД'. Если не задана — берётся текущий момент.

    ВАЖНО: до 1991 года в СССР действовало декретное время (+1 час к поясу).
    pytz это знает. datetime.now() — нет. Именно поэтому для рождения
    04.03.1959 в Узбекистане верный ответ +6, а не современный +5.
    """
    import pytz, datetime as _dt
    try:
        tz_obj = pytz.timezone(tz_name) if tz_name and tz_name != "UTC" else pytz.UTC
        if on_date:
            y, m, d = (int(x) for x in str(on_date).split("-"))
            off = tz_obj.utcoffset(_dt.datetime(y, m, d, 12, 0))
        else:
            off = _dt.datetime.now(tz_obj).utcoffset()
        return off.total_seconds() / 3600 if off else 0.0
    except Exception:
        return 0.0


_HISTORIC_COUNTRY = {
    # Республики СССР и старые имена -> современная страна.
    # Человек пишет страну как в свидетельстве о рождении, а базы знают только нынешние.
    "казахская сср": "казахстан", "казахская сcр": "казахстан", "казсср": "казахстан",
    "узбекская сср": "узбекистан", "узсср": "узбекистан",
    "рсфср": "россия", "российская сфср": "россия", "российская советская федеративная социалистическая республика": "россия",
    "усср": "украина", "украинская сср": "украина",
    "бсср": "беларусь", "белорусская сср": "беларусь", "белоруссия": "беларусь",
    "киргизская сср": "киргизия", "киргизия": "кыргызстан", "кирг сср": "кыргызстан",
    "таджикская сср": "таджикистан", "туркменская сср": "туркменистан",
    "азербайджанская сср": "азербайджан", "армянская сср": "армения",
    "грузинская сср": "грузия", "молдавская сср": "молдова", "молдавия": "молдова",
    "литовская сср": "литва", "латвийская сср": "латвия", "эстонская сср": "эстония",
    "рф": "россия", "российская федерация": "россия",
    "kazakh ssr": "казахстан", "uzbek ssr": "узбекистан", "russian sfsr": "россия",
    # неразрешимые — страну по ним не определить
    "ссср": None, "cccp": None, "ussr": None, "soviet union": None,
    "советский союз": None, "российская империя": None,
}


def _normalize_country(country: str):
    """Историческое имя страны -> современное.

    Возвращает (страна, примечание).
    Если страну определить нельзя (СССР — это 15 республик), возвращает ('', причина).
    """
    c = (country or "").strip()
    low = c.lower().replace("ё", "е").strip(" .,")
    if not low:
        return "", None
    if low in _HISTORIC_COUNTRY:
        modern = _HISTORIC_COUNTRY[low]
        if modern is None:
            return "", f"«{c}» — это не страна, а союз из 15 республик. Впиши современную: Казахстан, Россия, Узбекистан, Украина…"
        return modern, f"«{c}» -> «{modern}» (историческое название)"
    return c, None


def _strip_place_prefix(name: str) -> str:
    """Убирает 'с.', 'пос.', 'г.', 'зерносовхоз', 'совхоз' и т.п.

    Геокодеры не знают советских хозяйственных названий: «Зерносовхоз Советский»
    не находится, а «Советский» — находится. В базах осталось только имя.
    """
    n = (name or "").strip()
    for _ in range(3):                       # «пос. зерносовхоз Советский»
        low = n.lower()
        cut = None
        for pref in ("зерносовхоз ", "птицесовхоз ", "мясосовхоз ", "плодосовхоз ",
                     "совхоз ", "колхоз ", "госхоз ", "свх ", "клх ", "им. ", "имени ",
                     "с. ", "с.", "c. ", "c.", "п. ", "п.", "г. ", "г.", "д. ", "д.",
                     "ст. ", "ст.", "пос. ", "пос.", "село ", "посёлок ", "поселок ",
                     "город ", "деревня ", "станция ", "аул ", "s. ", "v. "):
            if low.startswith(pref):
                cut = len(pref)
                break
        if cut is None:
            break
        n = n[cut:].strip()
    return n or (name or "").strip()


def _addr_from_admin(a: dict, fallback: str = "") -> str:
    """Строка места из разбора: Село · Район · Область. GeoNames района не знает."""
    bits = [a.get("place"), a.get("district"), a.get("region")]
    bits = [b for b in bits if b]
    return " · ".join(bits) if bits else fallback


def _admin_at(lat: float, lng: float) -> dict:
    """Район/область/страна по координатам (обратный запрос к Nominatim, по-русски).

    GeoNames района НЕ ЗНАЕТ — отдаёт только область. Поэтому после того,
    как он нашёл точку, спрашиваем адрес у Nominatim.
    """
    try:
        from geopy.geocoders import Nominatim
        r = Nominatim(user_agent="quantarion-astrofractal").reverse(
            (lat, lng), language="ru", zoom=13)
        a = (r.raw.get("address") or {}) if r else {}
        return {
            "place": (a.get("village") or a.get("town") or a.get("hamlet")
                      or a.get("city") or ""),
            "district": a.get("county") or "",
            "region": a.get("state") or a.get("region") or "",
            "country": a.get("country") or "",
        }
    except Exception:
        return {}


def _geocode_once(query: str, on_date: Optional[str] = None,
                  expect_cc: Optional[str] = None) -> Optional[dict]:
    """Одна попытка: GeoNames, потом Nominatim.

    expect_cc — ISO-код страны. Находка в ДРУГОЙ стране отбрасывается:
    без этого «Зерносовхоз Советский, СССР» находил улицу 50-летия СССР в Крыму
    и выдавал её с зелёной галкой.
    """
    try:
        fz = _geonames_api_fuzzy(query, force_cc=expect_cc)
        if fz and (not expect_cc or not fz.get("cc") or fz["cc"] == expect_cc):
            return {
                "latitude": fz["lat"],
                "longitude": fz["lng"],
                "timezone_name": fz["tz"] or "UTC",
                "utc_offset": tz_offset_at(fz["tz"], on_date),
                "address": _addr_from_admin(_admin_at(fz["lat"], fz["lng"]), fz["found"]["name"]),
                "admin": _admin_at(fz["lat"], fz["lng"]),
                "candidates": fz["candidates"],
                "source": "geonames",
            }
    except Exception:
        pass
    try:
        from geopy.geocoders import Nominatim
        from timezonefinder import TimezoneFinder
        kw = {"addressdetails": True, "language": "ru"}
        if expect_cc:
            kw["country_codes"] = expect_cc.lower()
        loc = Nominatim(user_agent="quantarion-astrofractal").geocode(query, **kw)
        if not loc:
            return None
        got_cc = ((loc.raw.get("address") or {}).get("country_code") or "").upper()
        if expect_cc and got_cc and got_cc != expect_cc:
            return None
        _a = loc.raw.get("address") or {}
        admin = {
            "place": (_a.get("village") or _a.get("town") or _a.get("hamlet")
                      or _a.get("city") or ""),
            "district": _a.get("county") or "",
            "region": _a.get("state") or _a.get("region") or "",
            "country": _a.get("country") or "",
        }
        tz_name = TimezoneFinder().timezone_at(lat=loc.latitude, lng=loc.longitude)
        return {
            "latitude": round(loc.latitude, 6),
            "longitude": round(loc.longitude, 6),
            "timezone_name": tz_name or "UTC",
            "utc_offset": tz_offset_at(tz_name, on_date),
            "address": _addr_from_admin(admin, loc.address),
            "admin": admin,
            "candidates": [],
            "source": "nominatim",
        }
    except Exception:
        return None


def geocode(city: str, country: str = "", on_date: Optional[str] = None) -> dict:
    """Координаты и пояс по названию.

    city может быть «Село, Район, Область» — уточнения через запятую.
    on_date: 'ГГГГ-ММ-ДД' — дата, НА КОТОРУЮ считать смещение пояса.

    ПРОГРЕССИВНОЕ ОСЛАБЛЕНИЕ: если полный запрос не нашёлся, уточнения
    отбрасываются по одному справа налево. Старое название района
    («Возвышенский» вместо «Магжана Жумабаева») больше не убивает поиск.

    ИСТОРИЧЕСКАЯ СТРАНА: «Казахская ССР» -> «Казахстан». «СССР» — не страна,
    отбрасывается с предупреждением.

    ПРОВЕРКА СТРАНЫ: находка в чужой стране отбрасывается, а не выдаётся.
    """
    country, note = _normalize_country(country)
    cc = _COUNTRY_ISO.get((country or "").lower().strip()) if country else None

    # Страна вписана, но неразрешима («СССР») — ОТКАЗ, а не догадка.
    # Без страны «Зерносовхоз Советский» находит Вилючинск на Камчатке
    # и выдаёт с зелёной галкой. Уверенное враньё хуже честного отказа.
    if note and not country:
        return {"error": note}

    parts = [_strip_place_prefix(p.strip()) for p in (city or "").split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return {"error": "Не указан населённый пункт"}

    tried = []
    for n in range(len(parts), 0, -1):
        q = ", ".join(parts[:n])
        for full in ([f"{q}, {country}", q] if country else [q]):
            tried.append(full)
            r = _geocode_once(full, on_date, expect_cc=cc)
            if r:
                r["query"] = full
                r["dropped"] = parts[n:]      # что пришлось отбросить
                if note:
                    r["note"] = note
                return r
    err = f"'{parts[0]}' не найден"
    if note:
        err += f". {note}"
    return {"error": err}


# ============================================================
# МОДЕЛИ ЗАПРОСОВ
# ============================================================

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., description="Вопрос/реплика читателя")
    essay: Optional[str] = Field(
        None, description="Какое эссе обсуждают: 'light-and-code' (по умолчанию) или 'young-code'"
    )
    lang: Optional[str] = Field(
        None, description="Язык страницы: 'ru' (по умолчанию) или 'en'"
    )
    part: Optional[str] = Field(None, description="Обсуждаемая часть: '1', '2', '3'")
    chapter: Optional[str] = Field(None, description="Заголовок главы, где сейчас читатель")
    history: Optional[list[ChatMessage]] = Field(
        default_factory=list, description="Предыдущие реплики диалога"
    )
    include_full: bool = Field(
        False, description="Подложить полный текст части (дороже по токенам)"
    )


class NatalRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: int = 12
    minute: int = 0
    second: float = 0
    timezone: float = 0
    timezone_str: Optional[str] = None
    latitude: float = 0
    longitude: float = 0
    asc_degree: Optional[float] = Field(
        None, description="Если известен точный ASC (абсолютный градус)"
    )
    city: Optional[str] = None
    country: Optional[str] = None


class CascadeRequest(BaseModel):
    abs_degree: float = Field(
        ..., description="Абсолютная позиция планеты (0-360)"
    )
    levels: int = Field(7, ge=1, le=12)
    include_descriptions: bool = True


# ============================================================
# ЭНДПОИНТЫ
# ============================================================

@app.post("/natal")
async def natal_chart(req: NatalRequest):
    """
    Рассчитать натальную карту.

    Принимает дату/время + координаты (или город).
    Если указан ASC — использует его вместо расчётного.
    """
    lat = req.latitude
    lon = req.longitude
    tz = req.timezone

    # Историческое смещение по именованной зоне (как kerykeion), если передана
    if req.timezone_str:
        try:
            import pytz, datetime as _dt
            _zone = pytz.timezone(req.timezone_str)
            _naive = _dt.datetime(req.year, req.month, req.day, req.hour, req.minute)
            _off = _zone.utcoffset(_naive)
            if _off is not None:
                tz = _off.total_seconds() / 3600.0
        except Exception:
            pass

    # Геокодинг если указан город
    if req.city and (lat == 0 and lon == 0):
        geo = geocode(req.city, req.country or "")
        if "error" in geo:
            raise HTTPException(status_code=400, detail=geo["error"])
        lat = geo["latitude"]
        lon = geo["longitude"]
        tz = geo["utc_offset"]

    try:
        chart = calculate_natal(
            year=req.year, month=req.month, day=req.day,
            hour=req.hour, minute=req.minute, second=req.second,
            timezone=tz,
            latitude=lat, longitude=lon,
        )
        return chart
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cascade")
async def fractal_cascade(req: CascadeRequest):
    """
    Фрактальный расклад одной планеты.
    """
    try:
        if req.include_descriptions:
            db = get_db()
            result = assemble(req.abs_degree, req.levels, db)
        else:
            cascade = cascade_from_absolute(req.abs_degree, req.levels)
            result = {"cascade": cascade}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cascade-full")
async def full_cascade(req: NatalRequest):
    """
    Полный фрактальный расклад ВСЕХ планет натальной карты.
    Одна кнопка — полный портрет.
    """
    from engine.cascade_assembler import assemble_full_natal

    try:
        chart = await natal_chart(req)
        db = get_db()
        result = assemble_full_natal(chart, levels=4, db=db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transit")
async def current_transit(
    latitude: float = Query(..., ge=-90, le=90, description="Широта места наблюдения"),
    longitude: float = Query(..., ge=-180, le=180, description="Долгота места наблюдения"),
):
    """
    Текущие позиции всех планет + ASC/MC для указанных координат.
    Для синхронизации таймера в реальном времени.

    Координаты ОБЯЗАТЕЛЬНЫ. Раньше по умолчанию подставлялось с. Советское —
    и любой, кто не задал место, молча получал транзит чужого села.
    """
    now = datetime.now(timezone.utc)

    jd = swe.julday(
        now.year, now.month, now.day,
        now.hour + now.minute / 60.0 + now.second / 3600.0
    )

    # Планеты
    planets_ids = [
        (swe.SUN, "Солнце"), (swe.MOON, "Луна"),
        (swe.MERCURY, "Меркурий"), (swe.VENUS, "Венера"),
        (swe.MARS, "Марс"), (swe.JUPITER, "Юпитер"),
        (swe.SATURN, "Сатурн"), (swe.URANUS, "Уран"),
        (swe.NEPTUNE, "Нептун"), (swe.PLUTO, "Плутон"),
        (swe.TRUE_NODE, "Сев.Узел"), (swe.MEAN_APOG, "Лилит"),
        (swe.CHIRON, "Хирон"),
    ]

    planets = {}
    for pid, name in planets_ids:
        try:
            data = swe.calc_ut(jd, pid)[0]
            planets[name] = {
                "abs_degree": round(data[0], 6),
                "speed": round(data[3], 6) if len(data) > 3 else 0,
                "retrograde": data[3] < 0 if len(data) > 3 else False,
            }
        except Exception:
            pass

    # Селена (Белая Луна) — авестийская точка, зависит только от времени
    try:
        from engine.natal import _compute_selena
        planets["Селена"] = {
            "abs_degree": round(_compute_selena(jd), 6),
            "speed": 0,
            "retrograde": False,
        }
    except Exception:
        pass

    # Юж.Узел = Сев.Узел + 180
    if "Сев.Узел" in planets:
        planets["Юж.Узел"] = {
            "abs_degree": round((planets["Сев.Узел"]["abs_degree"] + 180) % 360, 6),
            "speed": 0,
            "retrograde": True,
        }

    # ASC/MC для координат
    try:
        # за полярным кругом Плацидуса нет -> Региомонтан
        _hs = b'P' if abs(latitude) <= 66.5 else b'R'
        cusps, angles = swe.houses(jd, latitude, longitude, _hs)
        asc_mc = {
            "ASC": round(angles[0], 6),
            "MC": round(angles[1], 6),
        }
        # 12 куспидов уже посчитаны Швейцарскими эфемеридами —
        # раньше выбрасывались, теперь едут на карту (живые дома)
        cusps_out = [round(c, 6) for c in cusps[:12]]
        house_system = "P" if _hs == b"P" else "R"
    except Exception:
        asc_mc = {"ASC": 0, "MC": 0}
        cusps_out = []
        house_system = ""

    return {
        "timestamp": now.isoformat(),
        "jd": jd,
        "planets": planets,
        "angles": asc_mc,
        "cusps": cusps_out,
        "house_system": house_system,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }


@app.get("/geocode")
async def geocode_city(city: str, country: str = "", on_date: Optional[str] = None):
    """Определить координаты и TZ по названию города.

    on_date='ГГГГ-ММ-ДД' — вернуть смещение пояса НА ЭТУ ДАТУ (декретное время и т.п.),
    а не текущее. Без неё — как раньше, по сегодняшнему дню.
    """
    result = geocode(city, country, on_date)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/degree/{abs_degree}")
async def degree_info(abs_degree: int):
    """Полное описание градуса (ОБРАЗ, ЭНЕРГЕТИКА, СУТЬ, ШАГ ПУТИ)."""
    db = get_db()
    info = db.get_by_absolute(abs_degree)
    if not info:
        raise HTTPException(status_code=404, detail=f"Градус {abs_degree} не найден")
    return info


# ============================================================
# НОВЫЕ МОДЕЛИ ЗАПРОСОВ
# ============================================================

class HoraryRequest(BaseModel):
    birth_year: int
    birth_month: int
    birth_day: int
    latitude: float = 0
    longitude: float = 0
    timezone: float = 0
    horary_latitude: Optional[float] = None
    horary_longitude: Optional[float] = None
    city: Optional[str] = None
    country: Optional[str] = None


class SynastryRequest(BaseModel):
    chart1: NatalRequest
    chart2: NatalRequest


class KerykeionRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: int = 12
    minute: int = 0
    second: int = 0          # 06.09: секунды рождения доходят до колеса
    timezone_str: str = 'UTC'
    latitude: float = 0
    longitude: float = 0
    solar_year: int = 2026
    tr_lat: float | None = None
    tr_lon: float | None = None
    tr_tz: str | None = None


class КосмограммаЗапрос(BaseModel):
    """Космограмма для прогноза дня: время рождения НЕ спрашивается.

    Если передан день и место «сейчас», Кериткеон строит ДВОЙНУЮ карту:
    космограмма внутри + транзитное кольцо снаружи. Поворот остаётся по Солнцу,
    потому что натал строится на солнечный час.
    """
    year: int
    month: int
    day: int
    latitude: float
    longitude: float
    gmt: float = 0.0          # смещение места рождения от UTC на ту дату
    theme: str = "dark-high-contrast"
    # момент транзита (когда есть — карта двойная)
    t_year: int | None = None
    t_month: int | None = None
    t_day: int | None = None
    t_hour: int = 12
    t_minute: int = 0
    t_lat: float | None = None
    t_lon: float | None = None
    t_gmt: float = 0.0


def _солнечный_час(год, месяц, день, широта, долгота, сдвиг):
    """Момент дня, когда асцендент ровно равен Солнцу.

    Его решение 14.08: Солнце — символический асцендент космограммы.
    Восход не годится (солнце всходит краем диска, расхождение до 3°),
    поэтому ищем точное совпадение: минутный проход + уточнение до секунды.
    """
    import swisseph as _swe
    from datetime import datetime as _dt, timedelta as _td

    def _jd(т):
        return _swe.julday(т.year, т.month, т.day,
                           т.hour + т.minute / 60.0 + т.second / 3600.0)

    def _дуга(a, b):
        d = abs((a - b) % 360)
        return min(d, 360 - d)

    def _разрыв(т):
        j = _jd(т)
        асц = _swe.houses(j, широта, долгота, b'P' if abs(широта) <= 66.5 else b'R')[1][0]
        солнце = _swe.calc_ut(j, _swe.SUN)[0][0]
        return _дуга(асц, солнце)

    т = _dt(год, месяц, день) - _td(hours=сдвиг)     # местная полночь в UTC
    лучший, мин = т, 999.0
    for _ in range(1440):
        d = _разрыв(т)
        if d < мин:
            мин, лучший = d, т
        т += _td(minutes=1)
    низ, верх = лучший - _td(minutes=1), лучший + _td(minutes=1)
    while (верх - низ).total_seconds() > 1:
        a = низ + (верх - низ) / 3
        b = верх - (верх - низ) / 3
        if _разрыв(a) < _разрыв(b):
            верх = b
        else:
            низ = a
    точно = (низ + (верх - низ) / 2).replace(microsecond=0)
    return точно, _разрыв(точно)


# ⚠️ За полярным кругом в полярную ночь солнечного часа НЕ СУЩЕСТВУЕТ:
# Солнце не восходит, часть эклиптики горизонт не пересекает, асцендент
# перепрыгивает через неё. Проверено: Мурманск 15.12.1975 — расхождение 18°.
# В таком случае строим колесо на местный полдень и говорим об этом прямо.
ПОРОГ_СОЛНЕЧНОГО_ЧАСА = 1.0 / 60.0        # одна угловая минута


class СеткаЗапрос(BaseModel):
    """Сетка суток для прогноза: круг от якоря, главы, узлы, куспиды по шагу."""
    year: int; month: int; day: int              # день прогноза
    b_year: int; b_month: int; b_day: int        # дата рождения
    b_lat: float; b_lon: float; b_gmt: float = 0.0
    latitude: float; longitude: float            # место «сейчас»
    gmt: float = 0.0
    anchor: float                                # градус якорного асцендента
    step: int = 2                                # шаг сетки в минутах


def _проверить_вход(широта, долгота, gmt, год, имя):
    """Границы, за которыми числа становятся бессмыслицей.
    ⚠️ Без этой проверки движок принимал широту 200° и считал мусор (найдено ревизией)."""
    if not (-90.0 <= широта <= 90.0):
        raise HTTPException(status_code=400, detail=f"{имя}: широта {широта} вне -90..90")
    if not (-180.0 <= долгота <= 180.0):
        raise HTTPException(status_code=400, detail=f"{имя}: долгота {долгота} вне -180..180")
    if not (-14.0 <= gmt <= 14.0):
        raise HTTPException(status_code=400, detail=f"{имя}: смещение GMT {gmt} вне -14..14")
    if not (1800 <= год <= 2200):
        raise HTTPException(status_code=400, detail=f"{имя}: год {год} вне 1800..2200 (эфемериды)")


@app.get("/solar-hour")
def solar_hour(year: int, month: int, day: int, lat: float, lon: float, gmt: float = 0.0):
    """Солнечный час дня рождения — момент, когда асцендент равен Солнцу.
    Лёгкий вызов: карта строит колесо сама, ей нужен только этот час."""
    from datetime import timedelta as _td
    import swisseph as _swe
    _проверить_вход(lat, lon, gmt, year, "рождение")
    точно, разрыв = _солнечный_час(year, month, day, lat, lon, gmt)
    есть = разрыв <= ПОРОГ_СОЛНЕЧНОГО_ЧАСА
    мест = точно + _td(hours=gmt)
    j = _swe.julday(точно.year, точно.month, точно.day,
                    точно.hour + точно.minute/60 + точно.second/3600)
    return {
        "час": мест.strftime("%H:%M:%S"),
        "часы": мест.hour, "минуты": мест.minute, "секунды": мест.second,
        "солнце": round(_swe.calc_ut(j, _swe.SUN)[0][0], 6),
        "луна": round(_swe.calc_ut(j, _swe.MOON)[0][0], 6),
        "солнце_на_асценденте": есть,
        "оговорка": ("" if есть else "Солнце в этот день не восходит — взят местный полдень"),
        "сборка": "d1",
    }


@app.get("/day-diag")
def day_diag():
    """Что реально лежит на сервере: сборка, модули, функции, время файлов.
    Открыть в браузере — сразу видно, какой файл не долетел."""
    import os, time, importlib
    из = {"сборка": "d1", "модули": {}, "функции": {}}
    for имя in ("engine/day_engine.py", "engine/tzh.py", "engine/muhurta.py",
                "frontend/prognoz.html", "frontend/cities.json", "api/main.py"):
        п = ROOT / имя
        из["модули"][имя] = {
            "есть": п.exists(),
            "размер": (п.stat().st_size if п.exists() else 0),
            "изменён": (time.strftime("%d.%m.%Y %H:%M", time.localtime(п.stat().st_mtime))
                        if п.exists() else "—"),
        }
    try:
        import sys as _s; _s.path.insert(0, str(ROOT))
        d = importlib.import_module("engine.day_engine")
        for ф in ("начало_круга", "главы_круга", "узлы_круга", "медленные",
                  "аспекты_медленных", "космограмма_текстом", "фаза_луны", "БЫСТРЫЕ"):
            из["функции"][ф] = hasattr(d, ф)
    except Exception as e:
        из["функции"]["ошибка_импорта"] = f"{type(e).__name__}: {e}"
    из["всё_на_месте"] = all(м["есть"] for м in из["модули"].values()) and \
                          all(v is True for k, v in из["функции"].items() if k != "ошибка_импорта")
    return из


@app.post("/day-grid")
async def day_grid(req: СеткаЗапрос):
    """Весь круг суток одним ответом: страница потом крутит его без запросов.

    Считает: начало круга (когда АС встал на якорный градус), 12 глав по знакам,
    все узлы (АС и угловые куспиды через точки, орбисы 2°/1°), сетку куспидов
    с заданным шагом, Колесо жизни и окно медитации.
    """
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    # обязательное — без него круга не будет
    from engine.day_engine import (начало_круга, главы_круга, узлы_круга,
                                   куспиды_в, точки_дня, дмс)
    # необязательное: если на сервере старый engine/day_engine.py, эти функции
    # могут отсутствовать — тогда блок просто пометится сбойным, а не рухнет весь ответ
    try:
        from engine.day_engine import медленные, аспекты_медленных
    except Exception:
        медленные = аспекты_медленных = None
    try:
        from engine.day_engine import космограмма_текстом, фаза_луны
    except Exception:
        космограмма_текстом = фаза_луны = None
    from engine.tzh import градус_тж
    from engine.muhurta import окно_медитации
    from engine.natal import calculate_natal

    try:
        _проверить_вход(req.b_lat, req.b_lon, req.b_gmt, req.b_year, "рождение")
        _проверить_вход(req.latitude, req.longitude, req.gmt, req.year, "день и место")
        if not (0.0 <= req.anchor < 360.0):
            raise HTTPException(status_code=400, detail=f"якорь {req.anchor} вне 0..360")
        # космограмма без времени: солнечный час, как в /day-cosmogram
        солн_час, разрыв = _солнечный_час(req.b_year, req.b_month, req.b_day,
                                          req.b_lat, req.b_lon, req.b_gmt)
        мест_рожд = солн_час + _td(hours=req.b_gmt)
        натал = calculate_natal(year=мест_рожд.year, month=мест_рожд.month, day=мест_рожд.day,
                                hour=мест_рожд.hour, minute=мест_рожд.minute,
                                second=мест_рожд.second, timezone=req.b_gmt,
                                latitude=req.b_lat, longitude=req.b_lon)

        день_utc = _dt(req.year, req.month, req.day, 12, 0, tzinfo=_tz.utc) - _td(hours=req.gmt)
        нач = начало_круга(день_utc, req.anchor, req.latitude, req.longitude)
        главы = главы_круга(нач, req.latitude, req.longitude)
        узлы = узлы_круга(нач, натал, req.latitude, req.longitude, шаг_минут=2)

        # сетка куспидов + положения БЫСТРЫХ тел на каждый шаг
        # (Луна за сутки уходит на 13° — если брать её застывшей, вспышки соврут)
        import swisseph as _swe2
        from engine.day_engine import jd as _jd
        БЫСТР = [("транзитный Луна", _swe2.MOON), ("транзитный Солнце", _swe2.SUN),
                 ("транзитный Меркурий", _swe2.MERCURY), ("транзитный Венера", _swe2.VENUS),
                 ("транзитный Марс", _swe2.MARS)]
        сетка = []
        быстрые_по_шагам = []
        т = нач
        конец = нач + _td(hours=24)
        шаг = _td(minutes=max(1, req.step))
        while т <= конец:
            к = куспиды_в(т, req.latitude, req.longitude)
            сетка.append([int((т - нач).total_seconds() // 60)] + [round(x, 4) for x in к])
            j = _jd(т)
            быстрые_по_шагам.append([round(_swe2.calc_ut(j, pid)[0][0], 3) for _, pid in БЫСТР])
            т += шаг

        мест = lambda д: (д + _td(hours=req.gmt)).strftime("%H:%M:%S")

        # ⚠️ Необязательные блоки считаем по отдельности: если один упадёт
        # (старый модуль на сервере, нехватка памяти), остальное всё равно придёт,
        # а сбойный блок будет назван по имени — вместо пустой карты и голого HTTP 500.
        сбои = {}

        def аккуратно(имя, что, запасное=None):
            try:
                return что()
            except Exception as e:
                сбои[имя] = f"{type(e).__name__}: {e}"
                return запасное

        тж = аккуратно("колесо жизни", lambda: градус_тж(
            _dt(req.b_year, req.b_month, req.b_day, 12, tzinfo=_tz.utc) - _td(hours=req.b_gmt), нач),
            {"градус": 0.0, "знак": "—", "эпоха_номер": 0, "годы_эпохи": (0, 0)})
        окно = аккуратно("окно медитации", lambda: окно_медитации(
            req.year, req.month, req.day, req.latitude, req.longitude, req.gmt), {"есть": False, "почему": "не посчиталось"})

        return {
            "начало": мест(нач),
            "начало_utc": нач.isoformat(),
            "якорь": round(req.anchor, 6),
            "шаг_минут": max(1, req.step),
            "главы": [{"знак": г["знак"], "начало": мест(г["начало"]), "конец": мест(г["конец"]),
                       "минут": round((г["конец"] - г["начало"]).total_seconds() / 60),
                       "неполная": г.get("неполная", "")} for г in главы],
            "узлы": [{"время": мест(у["время"]), "минута": int((у["время"] - нач).total_seconds() // 60),
                      "угол": у["угол"], "точка": у["точка"],
                      "градус": round(у["градус_точки"], 4), "градус_текст": дмс(у["градус_точки"]),
                      "орбис": у["орбис"], "окно_минут": у["окно_минут"],
                      "повтор": у.get("повтор", "")} for у in узлы],
            "сетка": сетка,
            "быстрые_имена": [и for и, _ in БЫСТР],
            "быстрые": быстрые_по_шагам,
            "точки": {и: round(г, 4) for и, г in точки_дня(нач + _td(hours=12), натал).items()},
            "медленные": аккуратно("медленные", lambda: _медленный_слой(солн_час, нач, натал),
                                    {"дуга": 0, "лет": 0, "дирекции": [], "прогрессии": [], "аспекты": []}),
            "космограмма": аккуратно("космограмма", lambda: космограмма_текстом(натал) if космограмма_текстом else (_ for _ in ()).throw(ImportError("космограмма_текстом отсутствует — старый engine/day_engine.py")),
                                     {"слои": [], "аспекты": [], "стихии": {}, "кресты": {}}),
            "фаза_луны": аккуратно("фаза луны", lambda: фаза_луны(нач) if фаза_луны else (_ for _ in ()).throw(ImportError("фаза_луны отсутствует — старый engine/day_engine.py")), {"имя": "—", "угол": 0, "смысл": ""}),
            "колесо_жизни": {"аспекты": аккуратно("аспекты колеса", lambda: __import__("importlib")
                                 .import_module("engine.day_engine").аспекты_колеса(
                                     тж["градус"], натал, точки_дня(нач, натал)), []),
                             "градус": тж["градус"], "текст": дмс(тж["градус"]),
                             "знак": тж["знак"], "эпоха": тж["эпоха_номер"],
                             "годы": list(тж["годы_эпохи"])},
            "окно_медитации": ({"начало": окно["окно"]["начало"].strftime("%H:%M"),
                                "конец": окно["окно"]["конец"].strftime("%H:%M"),
                                "восход": окно["восход"].strftime("%H:%M"),
                                "закат": окно["закат"].strftime("%H:%M")}
                               if окно.get("есть") else {"нет": окно.get("почему", "")}),
            "солнечный_час": мест_рожд.strftime("%H:%M:%S"),
            "солнце_на_асценденте": разрыв <= ПОРОГ_СОЛНЕЧНОГО_ЧАСА,
            "сборка": "d1",
            "сбои": сбои,          # пусто — значит всё посчиталось
        }
    except HTTPException:
        raise                      # понятные ошибки входа отдаём как есть (400)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


def _медленный_слой(рождение_utc, момент_utc, натал):
    """Причинный слой для центра карты: дирекции, прогрессии и их связи."""
    import sys as _s
    _s.path.insert(0, str(ROOT))
    from engine.day_engine import медленные, аспекты_медленных, точки_дня, дмс
    м = медленные(рождение_utc, момент_utc, натал)
    асп = аспекты_медленных(м, натал, точки_дня(момент_utc, натал))
    return {
        "дуга": м["дуга"], "лет": м["лет"],
        "дирекции": [{"имя": и, "градус": г, "текст": дмс(г)} for и, г in м["дирекции"].items()],
        "прогрессии": [{"имя": и, "градус": г, "текст": дмс(г)} for и, г in м["прогрессии"].items()],
        "аспекты": асп[:40],
    }


@app.post("/day-cosmogram")
async def day_cosmogram(req: КосмограммаЗапрос):
    """Космограмма для прогноза дня: колесо, повёрнутое Солнцем на асцендент.

    Домовые слои страница прячет сама — дома в прогнозе только динамические.
    Отдаём заодно солнечный час и предупреждение про Луну (она за сутки
    уходит на 13°, и в космограмме она стоит на тот момент — это её место в этой карте).
    """
    from kerykeion import KerykeionChartSVG
    import os, tempfile, swisseph as _swe
    from datetime import timedelta as _td

    try:
        _проверить_вход(req.latitude, req.longitude, req.gmt, req.year, "рождение")
        if req.t_year is not None and req.t_lat is not None:
            _проверить_вход(req.t_lat, req.t_lon, req.t_gmt, req.t_year, "день и место")
        точно, разрыв = _солнечный_час(req.year, req.month, req.day,
                                       req.latitude, req.longitude, req.gmt)
        солнце_на_асценденте = разрыв <= ПОРОГ_СОЛНЕЧНОГО_ЧАСА
        if not солнце_на_асценденте:
            # запасной путь: местный полдень, честно предупреждаем
            from datetime import datetime as _dt2
            точно = _dt2(req.year, req.month, req.day, 12, 0) - _td(hours=req.gmt)
        мест = точно + _td(hours=req.gmt)
        зона = f"Etc/GMT{'-' if req.gmt >= 0 else '+'}{abs(int(req.gmt))}"

        суб = KerykeionRequest(
            year=мест.year, month=мест.month, day=мест.day,
            hour=мест.hour, minute=мест.minute,
            timezone_str=зона, latitude=req.latitude, longitude=req.longitude,
        )
        натал = _make_kerykeion_subject('natal', суб)
        td = tempfile.gettempdir()
        for _s in os.listdir(td):
            if _s.endswith('.svg') and 'Wheel' in _s:
                try: os.remove(os.path.join(td, _s))
                except Exception: pass

        двойная = req.t_year is not None and req.t_lat is not None
        if двойная:
            зона_т = f"Etc/GMT{'-' if req.t_gmt >= 0 else '+'}{abs(int(req.t_gmt))}"
            суб_т = KerykeionRequest(
                year=req.t_year, month=req.t_month, day=req.t_day,
                hour=req.t_hour, minute=req.t_minute, timezone_str=зона_т,
                latitude=req.t_lat, longitude=req.t_lon,
            )
            транзит = _make_kerykeion_subject('Transit', суб_т)
            chart = KerykeionChartSVG(натал, chart_type='Transit', second_obj=транзит,
                                      theme=req.theme, chart_language='RU',
                                      new_output_directory=td)
        else:
            chart = KerykeionChartSVG(натал, chart_type='Natal', theme=req.theme,
                                      chart_language='RU', new_output_directory=td)
        chart.makeWheelOnlySVG()

        svg = None
        for f in os.listdir(td):
            if f.endswith('.svg') and 'Wheel' in f:
                if двойная and 'Transit' not in f: continue
                if not двойная and 'Transit' in f: continue
                with open(os.path.join(td, f), 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                break
        if not svg:
            raise HTTPException(status_code=500, detail="колесо не построилось")

        j = _swe.julday(точно.year, точно.month, точно.day,
                        точно.hour + точно.minute / 60.0 + точно.second / 3600.0)
        солнце = _swe.calc_ut(j, _swe.SUN)[0][0]
        луна = _swe.calc_ut(j, _swe.MOON)[0][0]
        return {
            "svg": svg,
            "солнечный_час": мест.strftime("%H:%M:%S"),
            "солнце": round(солнце, 6),
            "луна": round(луна, 6),
            "расхождение_ас_солнце_сек": round(разрыв * 3600, 1),
            "солнце_на_асценденте": солнце_на_асценденте,
            "двойная": двойная,
            "сборка": "d1",
            "оговорка": ("" if солнце_на_асценденте else
                         "В этот день на этой широте Солнце не восходит — солнечного часа нет. "
                         "Колесо построено на местный полдень, Солнце не на асценденте"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ============================================================
# НОВЫЕ ЭНДПОИНТЫ
# ============================================================

@app.post("/horary")
async def horary_chart(req: HoraryRequest):
    """
    Хорарная ректификация: таймстамп → ASC → натальная карта.
    Клиент нажимает кнопку, движок строит карту.
    """
    from engine.horary import horary_to_natal

    lat = req.latitude
    lon = req.longitude
    tz = req.timezone

    if req.city and (lat == 0 and lon == 0):
        geo = geocode(req.city, req.country or "")
        if "error" in geo:
            raise HTTPException(status_code=400, detail=geo["error"])
        lat = geo["latitude"]
        lon = geo["longitude"]
        tz = geo["utc_offset"]

    try:
        result = horary_to_natal(
            birth_year=req.birth_year,
            birth_month=req.birth_month,
            birth_day=req.birth_day,
            latitude=lat, longitude=lon,
            timezone_offset=tz,
            horary_latitude=req.horary_latitude,
            horary_longitude=req.horary_longitude,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/synastry")
async def synastry(req: SynastryRequest):
    """Синастрия двух карт."""
    from engine.synastry import calculate_synastry

    try:
        c1 = await natal_chart(req.chart1)
        c2 = await natal_chart(req.chart2)
        result = calculate_synastry(c1, c2)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/uran-sync")
async def uran_sync(req: NatalRequest):
    """
    Уран-синхрон: карта клиента синхронизируется
    с Ураном оператора (матрица).
    """
    from engine.synastry import calculate_uran_sync
    from engine.matrix import get_operator_chart

    try:
        client = await natal_chart(req)
        operator = get_operator_chart()
        result = calculate_uran_sync(operator, client)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/operator")
async def operator_raw():
    """Сырые данные оператора для построения запроса.

    ЕДИНСТВЕННЫЙ ИСТОЧНИК ИСТИНЫ. Правится только в engine/matrix.py.
    Фронт обязан брать оператора отсюда, а не держать свою копию цифр.
    """
    from engine.matrix import OPERATOR
    return {
        'year': OPERATOR['year'], 'month': OPERATOR['month'], 'day': OPERATOR['day'],
        'hour': OPERATOR['hour'], 'minute': OPERATOR['minute'], 'second': OPERATOR['second'],
        'timezone': OPERATOR['timezone'],
        'timezone_str': OPERATOR.get('timezone_str'),
        'latitude': OPERATOR['latitude'], 'longitude': OPERATOR['longitude'],
        'name': OPERATOR['name'], 'place': OPERATOR['place'],
    }


@app.get("/matrix")
async def matrix_info():
    """Статус матрицы оператора."""
    from engine.matrix import matrix_status, get_operator_info
    return {
        'status': matrix_status(),
        'info': get_operator_info(),
    }


# ============================================================
# ПОИСК МЕСТА -> координаты + таймзона (перенос из Dream Oracle)
# ============================================================

CITY_COORDS = {
    # ═══ РОССИЯ ═══
    "moscow": (55.7558, 37.6173, "Europe/Moscow"),
    "saint petersburg": (59.9343, 30.3351, "Europe/Moscow"),
    "st petersburg": (59.9343, 30.3351, "Europe/Moscow"),
    "novosibirsk": (55.0084, 82.9357, "Asia/Novosibirsk"),
    "yekaterinburg": (56.8389, 60.6057, "Asia/Yekaterinburg"),
    "ekaterinburg": (56.8389, 60.6057, "Asia/Yekaterinburg"),
    "kazan": (55.7887, 49.1221, "Europe/Moscow"),
    "nizhny novgorod": (56.2965, 43.9361, "Europe/Moscow"),
    "chelyabinsk": (55.1644, 61.4368, "Asia/Yekaterinburg"),
    "samara": (53.1959, 50.1002, "Europe/Samara"),
    "omsk": (54.9885, 73.3242, "Asia/Omsk"),
    "rostov-on-don": (47.2357, 39.7015, "Europe/Moscow"),
    "rostov": (47.2357, 39.7015, "Europe/Moscow"),
    "ufa": (54.7388, 55.9721, "Asia/Yekaterinburg"),
    "krasnoyarsk": (56.0153, 92.8932, "Asia/Krasnoyarsk"),
    "perm": (58.0105, 56.2502, "Asia/Yekaterinburg"),
    "voronezh": (51.6720, 39.1843, "Europe/Moscow"),
    "volgograd": (48.7080, 44.5133, "Europe/Volgograd"),
    "krasnodar": (45.0355, 38.9753, "Europe/Moscow"),
    "saratov": (51.5336, 46.0344, "Europe/Saratov"),
    "tyumen": (57.1522, 65.5272, "Asia/Yekaterinburg"),
    "tolyatti": (53.5303, 49.3461, "Europe/Samara"),
    "izhevsk": (56.8527, 53.2114, "Europe/Samara"),
    "barnaul": (53.3548, 83.7698, "Asia/Barnaul"),
    "vladivostok": (43.1332, 131.9113, "Asia/Vladivostok"),
    "irkutsk": (52.2870, 104.3050, "Asia/Irkutsk"),
    "khabarovsk": (48.4827, 135.0838, "Asia/Vladivostok"),
    "tomsk": (56.4846, 84.9476, "Asia/Tomsk"),
    "kemerovo": (55.3540, 86.0880, "Asia/Novokuznetsk"),
    "novokuznetsk": (53.7596, 87.1216, "Asia/Novokuznetsk"),
    "sochi": (43.5855, 39.7231, "Europe/Moscow"),
    "kaliningrad": (54.7104, 20.4522, "Europe/Kaliningrad"),
    "murmansk": (68.9585, 33.0827, "Europe/Moscow"),
    "arkhangelsk": (64.5399, 40.5152, "Europe/Moscow"),
    "tula": (54.1961, 37.6182, "Europe/Moscow"),
    "yaroslavl": (57.6261, 39.8845, "Europe/Moscow"),
    "vladimir": (56.1290, 40.4066, "Europe/Moscow"),
    "surgut": (61.2500, 73.3856, "Asia/Yekaterinburg"),
    "orenburg": (51.7682, 55.0970, "Asia/Yekaterinburg"),
    "norilsk": (69.3535, 88.1892, "Asia/Krasnoyarsk"),
    "magadan": (59.5683, 150.8089, "Asia/Magadan"),
    "yakutsk": (62.0397, 129.7422, "Asia/Yakutsk"),
    "petropavlovsk-kamchatsky": (53.0452, 158.6511, "Asia/Kamchatka"),
    "simferopol": (44.9521, 34.1024, "Europe/Simferopol"),
    "sevastopol": (44.6167, 33.5254, "Europe/Simferopol"),
    # ═══ КАЗАХСТАН ═══
    "almaty": (43.2220, 76.8512, "Asia/Almaty"),
    "astana": (51.1694, 71.4491, "Asia/Almaty"),
    "nur-sultan": (51.1694, 71.4491, "Asia/Almaty"),
    "shymkent": (42.3417, 69.5901, "Asia/Almaty"),
    "karaganda": (49.8047, 73.1094, "Asia/Almaty"),
    "aktobe": (50.2839, 57.1670, "Asia/Aqtobe"),
    "petropavlovsk": (54.8753, 69.1629, "Asia/Almaty"),
    "pavlodar": (52.2873, 76.9674, "Asia/Almaty"),
    "kostanay": (53.2198, 63.6354, "Asia/Qostanay"),
    "atyrau": (47.1076, 51.9141, "Asia/Atyrau"),
    "aktau": (43.6353, 51.1684, "Asia/Aqtau"),
    "semey": (50.4264, 80.2277, "Asia/Almaty"),
    "ust-kamenogorsk": (49.9718, 82.6059, "Asia/Almaty"),
    "taldykorgan": (45.0174, 78.3738, "Asia/Almaty"),
    "oral": (51.2278, 51.3864, "Asia/Oral"),
    "turkestan": (43.2978, 68.2514, "Asia/Almaty"),
    # ═══ УКРАИНА ═══
    "kyiv": (50.4501, 30.5234, "Europe/Kyiv"),
    "kiev": (50.4501, 30.5234, "Europe/Kyiv"),
    "kharkiv": (49.9935, 36.2304, "Europe/Kyiv"),
    "odessa": (46.4825, 30.7233, "Europe/Kyiv"),
    "dnipro": (48.4647, 35.0462, "Europe/Kyiv"),
    "lviv": (49.8397, 24.0297, "Europe/Kyiv"),
    "zaporizhzhia": (47.8388, 35.1396, "Europe/Kyiv"),
    "donetsk": (48.0159, 37.8029, "Europe/Kyiv"),
    # ═══ БЕЛАРУСЬ ═══
    "minsk": (53.9006, 27.5590, "Europe/Minsk"),
    "gomel": (52.4345, 30.9754, "Europe/Minsk"),
    "grodno": (53.6884, 23.8258, "Europe/Minsk"),
    "brest": (52.0976, 23.7341, "Europe/Minsk"),
    "vitebsk": (55.1904, 30.2049, "Europe/Minsk"),
    "mogilev": (53.8998, 30.3325, "Europe/Minsk"),
    # ═══ ГРУЗИЯ ═══
    "tbilisi": (41.7151, 44.8271, "Asia/Tbilisi"),
    "batumi": (41.6168, 41.6367, "Asia/Tbilisi"),
    "kutaisi": (42.2679, 42.6946, "Asia/Tbilisi"),
    # ═══ АРМЕНИЯ / АЗЕРБАЙДЖАН ═══
    "yerevan": (40.1792, 44.4991, "Asia/Yerevan"),
    "baku": (40.4093, 49.8671, "Asia/Baku"),
    # ═══ СРЕДНЯЯ АЗИЯ ═══
    "tashkent": (41.2995, 69.2401, "Asia/Tashkent"),
    "samarkand": (39.6542, 66.9597, "Asia/Samarkand"),
    "bukhara": (39.7681, 64.4556, "Asia/Samarkand"),
    "bishkek": (42.8746, 74.5698, "Asia/Bishkek"),
    "dushanbe": (38.5598, 68.7740, "Asia/Dushanbe"),
    "ashgabat": (37.9601, 58.3261, "Asia/Ashgabat"),
    # ═══ ПРИБАЛТИКА / МОЛДОВА ═══
    "chisinau": (47.0105, 28.8638, "Europe/Chisinau"),
    "tallinn": (59.4370, 24.7536, "Europe/Tallinn"),
    "riga": (56.9496, 24.1052, "Europe/Riga"),
    "vilnius": (54.6872, 25.2797, "Europe/Vilnius"),
    # ═══ ЕВРОПА ═══
    "london": (51.5074, -0.1278, "Europe/London"),
    "paris": (48.8566, 2.3522, "Europe/Paris"),
    "berlin": (52.5200, 13.4050, "Europe/Berlin"),
    "madrid": (40.4168, -3.7038, "Europe/Madrid"),
    "barcelona": (41.3874, 2.1686, "Europe/Madrid"),
    "rome": (41.9028, 12.4964, "Europe/Rome"),
    "milan": (45.4642, 9.1900, "Europe/Rome"),
    "amsterdam": (52.3676, 4.9041, "Europe/Amsterdam"),
    "brussels": (50.8503, 4.3517, "Europe/Brussels"),
    "vienna": (48.2082, 16.3738, "Europe/Vienna"),
    "zurich": (47.3769, 8.5417, "Europe/Zurich"),
    "geneva": (46.2044, 6.1432, "Europe/Zurich"),
    "prague": (50.0755, 14.4378, "Europe/Prague"),
    "warsaw": (52.2297, 21.0122, "Europe/Warsaw"),
    "budapest": (47.4979, 19.0402, "Europe/Budapest"),
    "bucharest": (44.4268, 26.1025, "Europe/Bucharest"),
    "sofia": (42.6977, 23.3219, "Europe/Sofia"),
    "athens": (37.9838, 23.7275, "Europe/Athens"),
    "lisbon": (38.7223, -9.1393, "Europe/Lisbon"),
    "stockholm": (59.3293, 18.0686, "Europe/Stockholm"),
    "oslo": (59.9139, 10.7522, "Europe/Oslo"),
    "copenhagen": (55.6761, 12.5683, "Europe/Copenhagen"),
    "helsinki": (60.1699, 24.9384, "Europe/Helsinki"),
    "dublin": (53.3498, -6.2603, "Europe/Dublin"),
    "edinburgh": (55.9533, -3.1883, "Europe/London"),
    "munich": (48.1351, 11.5820, "Europe/Berlin"),
    "hamburg": (53.5511, 9.9937, "Europe/Berlin"),
    "frankfurt": (50.1109, 8.6821, "Europe/Berlin"),
    "lyon": (45.7640, 4.8357, "Europe/Paris"),
    "marseille": (43.2965, 5.3698, "Europe/Paris"),
    "nice": (43.7102, 7.2620, "Europe/Paris"),
    "naples": (40.8518, 14.2681, "Europe/Rome"),
    "florence": (43.7696, 11.2558, "Europe/Rome"),
    "venice": (45.4408, 12.3155, "Europe/Rome"),
    "belgrade": (44.7866, 20.4489, "Europe/Belgrade"),
    "zagreb": (45.8150, 15.9819, "Europe/Zagreb"),
    "ljubljana": (46.0569, 14.5058, "Europe/Ljubljana"),
    "bratislava": (48.1486, 17.1077, "Europe/Bratislava"),
    "reykjavik": (64.1466, -21.9426, "Atlantic/Reykjavik"),
    # ═══ ТУРЦИЯ ═══
    "istanbul": (41.0082, 28.9784, "Europe/Istanbul"),
    "ankara": (39.9334, 32.8597, "Europe/Istanbul"),
    "izmir": (38.4192, 27.1287, "Europe/Istanbul"),
    "antalya": (36.8969, 30.7133, "Europe/Istanbul"),
    # ═══ БЛИЖНИЙ ВОСТОК ═══
    "dubai": (25.2048, 55.2708, "Asia/Dubai"),
    "abu dhabi": (24.4539, 54.3773, "Asia/Dubai"),
    "tel aviv": (32.0853, 34.7818, "Asia/Jerusalem"),
    "jerusalem": (31.7683, 35.2137, "Asia/Jerusalem"),
    "riyadh": (24.7136, 46.6753, "Asia/Riyadh"),
    "jeddah": (21.5433, 39.1728, "Asia/Riyadh"),
    "doha": (25.2854, 51.5310, "Asia/Qatar"),
    "beirut": (33.8938, 35.5018, "Asia/Beirut"),
    "amman": (31.9454, 35.9284, "Asia/Amman"),
    "tehran": (35.6892, 51.3890, "Asia/Tehran"),
    "baghdad": (33.3152, 44.3661, "Asia/Baghdad"),
    "cairo": (30.0444, 31.2357, "Africa/Cairo"),
    "kuwait city": (29.3759, 47.9774, "Asia/Kuwait"),
    "muscat": (23.5880, 58.3829, "Asia/Muscat"),
    # ═══ АЗИЯ ═══
    "tokyo": (35.6762, 139.6503, "Asia/Tokyo"),
    "osaka": (34.6937, 135.5023, "Asia/Tokyo"),
    "beijing": (39.9042, 116.4074, "Asia/Shanghai"),
    "shanghai": (31.2304, 121.4737, "Asia/Shanghai"),
    "guangzhou": (23.1291, 113.2644, "Asia/Shanghai"),
    "shenzhen": (22.5431, 114.0579, "Asia/Shanghai"),
    "hong kong": (22.3193, 114.1694, "Asia/Hong_Kong"),
    "seoul": (37.5665, 126.9780, "Asia/Seoul"),
    "busan": (35.1796, 129.0756, "Asia/Seoul"),
    "taipei": (25.0330, 121.5654, "Asia/Taipei"),
    "singapore": (1.3521, 103.8198, "Asia/Singapore"),
    "bangkok": (13.7563, 100.5018, "Asia/Bangkok"),
    "hanoi": (21.0278, 105.8342, "Asia/Ho_Chi_Minh"),
    "ho chi minh city": (10.8231, 106.6297, "Asia/Ho_Chi_Minh"),
    "mumbai": (19.0760, 72.8777, "Asia/Kolkata"),
    "delhi": (28.7041, 77.1025, "Asia/Kolkata"),
    "new delhi": (28.6139, 77.2090, "Asia/Kolkata"),
    "bangalore": (12.9716, 77.5946, "Asia/Kolkata"),
    "chennai": (13.0827, 80.2707, "Asia/Kolkata"),
    "kolkata": (22.5726, 88.3639, "Asia/Kolkata"),
    "hyderabad": (17.3850, 78.4867, "Asia/Kolkata"),
    "karachi": (24.8607, 67.0011, "Asia/Karachi"),
    "lahore": (31.5204, 74.3587, "Asia/Karachi"),
    "islamabad": (33.6844, 73.0479, "Asia/Karachi"),
    "dhaka": (23.8103, 90.4125, "Asia/Dhaka"),
    "colombo": (6.9271, 79.8612, "Asia/Colombo"),
    "kathmandu": (27.7172, 85.3240, "Asia/Kathmandu"),
    "kuala lumpur": (3.1390, 101.6869, "Asia/Kuala_Lumpur"),
    "jakarta": (-6.2088, 106.8456, "Asia/Jakarta"),
    "manila": (14.5995, 120.9842, "Asia/Manila"),
    "ulaanbaatar": (47.8864, 106.9057, "Asia/Ulaanbaatar"),
    # ═══ АФРИКА ═══
    "johannesburg": (-26.2041, 28.0473, "Africa/Johannesburg"),
    "cape town": (-33.9249, 18.4241, "Africa/Johannesburg"),
    "nairobi": (-1.2921, 36.8219, "Africa/Nairobi"),
    "lagos": (6.5244, 3.3792, "Africa/Lagos"),
    "casablanca": (33.5731, -7.5898, "Africa/Casablanca"),
    "tunis": (36.8065, 10.1815, "Africa/Tunis"),
    "algiers": (36.7538, 3.0588, "Africa/Algiers"),
    "addis ababa": (9.0250, 38.7469, "Africa/Addis_Ababa"),
    "dar es salaam": (-6.7924, 39.2083, "Africa/Dar_es_Salaam"),
    "accra": (5.6037, -0.1870, "Africa/Accra"),
    "dakar": (14.7167, -17.4677, "Africa/Dakar"),
    # ═══ СЕВЕРНАЯ АМЕРИКА ═══
    "new york": (40.7128, -74.0060, "America/New_York"),
    "los angeles": (34.0522, -118.2437, "America/Los_Angeles"),
    "chicago": (41.8781, -87.6298, "America/Chicago"),
    "houston": (29.7604, -95.3698, "America/Chicago"),
    "phoenix": (33.4484, -112.0740, "America/Phoenix"),
    "philadelphia": (39.9526, -75.1652, "America/New_York"),
    "san antonio": (29.4241, -98.4936, "America/Chicago"),
    "san diego": (32.7157, -117.1611, "America/Los_Angeles"),
    "dallas": (32.7767, -96.7970, "America/Chicago"),
    "san francisco": (37.7749, -122.4194, "America/Los_Angeles"),
    "seattle": (47.6062, -122.3321, "America/Los_Angeles"),
    "denver": (39.7392, -104.9903, "America/Denver"),
    "boston": (42.3601, -71.0589, "America/New_York"),
    "miami": (25.7617, -80.1918, "America/New_York"),
    "atlanta": (33.7490, -84.3880, "America/New_York"),
    "washington": (38.9072, -77.0369, "America/New_York"),
    "las vegas": (36.1699, -115.1398, "America/Los_Angeles"),
    "detroit": (42.3314, -83.0458, "America/Detroit"),
    "minneapolis": (44.9778, -93.2650, "America/Chicago"),
    "portland": (45.5155, -122.6789, "America/Los_Angeles"),
    "austin": (30.2672, -97.7431, "America/Chicago"),
    "toronto": (43.6532, -79.3832, "America/Toronto"),
    "vancouver": (49.2827, -123.1207, "America/Vancouver"),
    "montreal": (45.5017, -73.5673, "America/Toronto"),
    "calgary": (51.0447, -114.0719, "America/Edmonton"),
    "ottawa": (45.4215, -75.6972, "America/Toronto"),
    "mexico city": (19.4326, -99.1332, "America/Mexico_City"),
    "guadalajara": (20.6597, -103.3496, "America/Mexico_City"),
    "monterrey": (25.6866, -100.3161, "America/Monterrey"),
    "havana": (23.1136, -82.3666, "America/Havana"),
    # ═══ ЮЖНАЯ АМЕРИКА ═══
    "sao paulo": (-23.5505, -46.6333, "America/Sao_Paulo"),
    "rio de janeiro": (-22.9068, -43.1729, "America/Sao_Paulo"),
    "buenos aires": (-34.6037, -58.3816, "America/Argentina/Buenos_Aires"),
    "bogota": (4.7110, -74.0721, "America/Bogota"),
    "lima": (-12.0464, -77.0428, "America/Lima"),
    "santiago": (-33.4489, -70.6693, "America/Santiago"),
    "caracas": (10.4806, -66.9036, "America/Caracas"),
    "medellin": (6.2476, -75.5658, "America/Bogota"),
    "quito": (-0.1807, -78.4678, "America/Guayaquil"),
    "montevideo": (-34.9011, -56.1645, "America/Montevideo"),
    # ═══ ОКЕАНИЯ ═══
    "sydney": (-33.8688, 151.2093, "Australia/Sydney"),
    "melbourne": (-37.8136, 144.9631, "Australia/Melbourne"),
    "brisbane": (-27.4698, 153.0251, "Australia/Brisbane"),
    "perth": (-31.9505, 115.8605, "Australia/Perth"),
    "auckland": (-36.8485, 174.7633, "Pacific/Auckland"),
    "wellington": (-41.2865, 174.7762, "Pacific/Auckland"),
}

CITY_ALIASES = {
    # Кириллица — Россия
    "москва": "moscow", "санкт-петербург": "saint petersburg", "питер": "saint petersburg",
    "спб": "saint petersburg", "новосибирск": "novosibirsk", "екатеринбург": "yekaterinburg",
    "казань": "kazan", "нижний новгород": "nizhny novgorod", "челябинск": "chelyabinsk",
    "самара": "samara", "омск": "omsk", "ростов-на-дону": "rostov-on-don", "ростов": "rostov",
    "уфа": "ufa", "красноярск": "krasnoyarsk", "пермь": "perm", "воронеж": "voronezh",
    "волгоград": "volgograd", "краснодар": "krasnodar", "саратов": "saratov", "тюмень": "tyumen",
    "тольятти": "tolyatti", "ижевск": "izhevsk", "барнаул": "barnaul",
    "владивосток": "vladivostok", "иркутск": "irkutsk", "хабаровск": "khabarovsk",
    "томск": "tomsk", "кемерово": "kemerovo", "новокузнецк": "novokuznetsk",
    "сочи": "sochi", "калининград": "kaliningrad", "мурманск": "murmansk",
    "архангельск": "arkhangelsk", "тула": "tula", "ярославль": "yaroslavl",
    "владимир": "vladimir", "сургут": "surgut", "оренбург": "orenburg",
    "норильск": "norilsk", "магадан": "magadan", "якутск": "yakutsk",
    "петропавловск-камчатский": "petropavlovsk-kamchatsky",
    "симферополь": "simferopol", "севастополь": "sevastopol",
    # Кириллица — Казахстан
    "алматы": "almaty", "алма-ата": "almaty", "астана": "astana", "нур-султан": "nur-sultan",
    "шымкент": "shymkent", "караганда": "karaganda", "актобе": "aktobe",
    "петропавловск": "petropavlovsk", "павлодар": "pavlodar", "костанай": "kostanay",
    "атырау": "atyrau", "актау": "aktau", "семей": "semey", "семипалатинск": "semey",
    "усть-каменогорск": "ust-kamenogorsk", "талдыкорган": "taldykorgan",
    "уральск": "oral", "туркестан": "turkestan",
    # Кириллица — Украина
    "киев": "kyiv", "харьков": "kharkiv", "одесса": "odessa", "днепр": "dnipro",
    "львов": "lviv", "запорожье": "zaporizhzhia", "донецк": "donetsk",
    # Кириллица — Беларусь
    "минск": "minsk", "гомель": "gomel", "гродно": "grodno", "брест": "brest",
    "витебск": "vitebsk", "могилёв": "mogilev", "могилев": "mogilev",
    # Кириллица — Кавказ
    "тбилиси": "tbilisi", "батуми": "batumi", "кутаиси": "kutaisi",
    "ереван": "yerevan", "баку": "baku",
    # Кириллица — Средняя Азия
    "ташкент": "tashkent", "самарканд": "samarkand", "бухара": "bukhara",
    "бишкек": "bishkek", "душанбе": "dushanbe", "ашхабад": "ashgabat",
    # Кириллица — Прибалтика / Молдова
    "кишинёв": "chisinau", "кишинев": "chisinau", "таллин": "tallinn",
    "рига": "riga", "вильнюс": "vilnius",
    # Кириллица — мировые столицы
    "лондон": "london", "париж": "paris", "берлин": "berlin", "мадрид": "madrid",
    "рим": "rome", "амстердам": "amsterdam", "вена": "vienna", "прага": "prague",
    "варшава": "warsaw", "будапешт": "budapest", "бухарест": "bucharest",
    "стамбул": "istanbul", "анкара": "ankara", "дубай": "dubai", "тель-авив": "tel aviv",
    "каир": "cairo", "токио": "tokyo", "пекин": "beijing", "шанхай": "shanghai",
    "сеул": "seoul", "бангкок": "bangkok", "сингапур": "singapore",
    "нью-йорк": "new york", "лос-анджелес": "los angeles", "чикаго": "chicago",
    "торонто": "toronto", "мехико": "mexico city", "сидней": "sydney",
    # Английские варианты
    "ny": "new york", "nyc": "new york", "la": "los angeles", "sf": "san francisco",
    "dc": "washington", "spb": "saint petersburg", "msk": "moscow",
}


def resolve_city(place_str):
    """Резолвит строку места -> (lat, lng, tz_str) или None. Только локальный словарь (офлайн)."""
    if not place_str:
        return None
    clean = place_str.strip().lower()
    for suffix in [" russia", " kazakhstan", " ukraine", " belarus", " georgia",
                   " uzbekistan", " turkey", " germany", " france", " usa",
                   " united states", " uk", " united kingdom", " canada",
                   " china", " japan", " india", " brazil", " spain", " italy",
                   " россия", " казахстан", " украина", " беларусь", " грузия",
                   " узбекистан", " турция", " германия", " франция", " сша",
                   " китай", " япония", " индия", " испания", " италия"]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)].strip()
            break
    if clean in CITY_COORDS:
        return CITY_COORDS[clean]
    if clean in CITY_ALIASES:
        key = CITY_ALIASES[clean]
        if key in CITY_COORDS:
            return CITY_COORDS[key]
    for key in CITY_COORDS:
        if key in clean or clean in key:
            return CITY_COORDS[key]
    for alias, key in CITY_ALIASES.items():
        if alias in clean or clean in alias:
            if key in CITY_COORDS:
                return CITY_COORDS[key]
    return None


@app.get("/resolve-place")
async def resolve_place(q: str = ""):
    """Поиск места -> координаты + таймзона."""
    r = resolve_city(q)
    if r:
        return {"found": True, "lat": r[0], "lng": r[1], "tz_str": r[2]}
    return {"found": False}



# ============================================================
# ОБРАТНЫЙ РАСЧЁТ: известный ASC -> время рождения
# ============================================================

def _find_time_for_asc(target, year, month, day, lat, lng, gmt):
    """По известному ASC (град 0-360) находит local-время дня, когда асцендент = target.
    Возвращает (hour, minute, second) или None."""
    import swisseph as swe

    def asc_at(ut_hour):
        jd = swe.julday(year, month, day, ut_hour)
        _, ascmc = swe.houses(jd, lat, lng, b'P' if abs(lat) <= 66.5 else b'R')
        return ascmc[0]

    target %= 360.0
    prev = None
    prevm = None
    for minute in range(0, 1441):
        h = minute // 60
        m = minute % 60
        a = asc_at(h + m / 60.0 - gmt)
        if prev is not None:
            dt = (a - prev) % 360.0
            dtg = (target - prev) % 360.0
            if 0 < dtg <= dt:
                lo, hi = prevm * 60, minute * 60
                for _ in range(40):
                    mid = (lo + hi) / 2.0
                    am = asc_at(mid / 3600.0 - gmt)
                    if 0 < ((target - prev) % 360.0) <= ((am - prev) % 360.0):
                        hi = mid
                    else:
                        lo = mid
                s = (lo + hi) / 2.0
                return int(s // 3600), int((s % 3600) // 60), int(round(s % 60))
        prev = a
        prevm = minute
    return None


@app.get("/asc-to-time")
async def asc_to_time(asc: float, year: int, month: int, day: int,
                      lat: float, lng: float, gmt: float = 0.0):
    """Известный ASC -> время рождения (карта строится от готового ASC)."""
    r = _find_time_for_asc(asc, year, month, day, lat, lng, gmt)
    if r:
        hh, mm, ss = r
        if ss >= 60:
            ss -= 60; mm += 1
        if mm >= 60:
            mm -= 60; hh += 1
        return {"found": True, "hour": hh % 24, "minute": mm, "second": ss}
    return {"found": False}



def _make_kerykeion_subject(name, req):
    """Создаёт kerykeion Subject из запроса.

    06.09: СЕКУНДЫ. Старый AstrologicalSubject берёт только час и минуту —
    40 секунд рождения выбрасывались, и асцендент колеса уезжал на 6.8′
    от асцендента наших таблиц (они секунды считают). Кериkeion 5 умеет
    секунды через фабрику — берём её, если есть; на старом Кериkeion
    округляем к ближайшей минуте (ошибка не больше 30 с вместо 60).
    """
    сек = int(getattr(req, 'second', 0) or 0)
    try:
        from kerykeion import AstrologicalSubjectFactory
        return AstrologicalSubjectFactory.from_birth_data(
            name, req.year, req.month, req.day, req.hour, req.minute,
            lng=req.longitude, lat=req.latitude, tz_str=req.timezone_str,
            city='calc', nation='XX', online=False, seconds=сек,
        )
    except ImportError:
        from kerykeion import AstrologicalSubject
        from datetime import datetime as _dt, timedelta as _td
        т = _dt(req.year, req.month, req.day, req.hour, req.minute) + _td(seconds=сек)
        if т.second >= 30:
            т += _td(seconds=60 - т.second)
        return AstrologicalSubject(
            name, т.year, т.month, т.day, т.hour, т.minute,
            lng=req.longitude, lat=req.latitude,
            tz_str=req.timezone_str,
            city='calc', nation='XX',
            online=False,
        )


@app.post("/solar")
async def solar_return(req: KerykeionRequest):
    """Соляр (возврат Солнца)."""
    import sys
    sys.path.insert(0, str(ROOT / 'astro'))
    from solar_calculator import calculate_solar_return

    try:
        natal = _make_kerykeion_subject('natal', req)
        solar_req = KerykeionRequest(
            year=req.solar_year, month=req.month, day=req.day,
            hour=12, minute=0,
            timezone_str=req.timezone_str,
            latitude=req.latitude, longitude=req.longitude,
        )
        solar = _make_kerykeion_subject('solar', solar_req)
        result = calculate_solar_return(natal, solar)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/progressions")
async def progressions(req: KerykeionRequest):
    """Вторичные прогрессии."""
    import sys
    sys.path.insert(0, str(ROOT / 'astro'))
    from progressions_calculator import calculate_progressions

    try:
        natal = _make_kerykeion_subject('natal', req)
        solar_req = KerykeionRequest(
            year=req.solar_year, month=req.month, day=req.day,
            hour=12, minute=0,
            timezone_str=req.timezone_str,
            latitude=req.latitude, longitude=req.longitude,
        )
        solar = _make_kerykeion_subject('solar', solar_req)
        result = calculate_progressions(natal, solar)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/directions")
async def directions(req: KerykeionRequest):
    """Солнечные дуги (дирекции)."""
    import sys
    sys.path.insert(0, str(ROOT / 'astro'))
    from solar_arc_calculator import calculate_solar_arc

    try:
        natal = _make_kerykeion_subject('natal', req)
        solar_req = KerykeionRequest(
            year=req.solar_year, month=req.month, day=req.day,
            hour=12, minute=0,
            timezone_str=req.timezone_str,
            latitude=req.latitude, longitude=req.longitude,
        )
        solar = _make_kerykeion_subject('solar', solar_req)
        result = calculate_solar_arc(natal, solar)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transit-aspects")
async def transit_aspects(req: KerykeionRequest):
    """Транзитные активации на год."""
    import sys
    sys.path.insert(0, str(ROOT / 'astro'))
    from transit_activations import calculate_transit_activations

    try:
        natal = _make_kerykeion_subject('natal', req)
        solar_req = KerykeionRequest(
            year=req.solar_year, month=req.month, day=req.day,
            hour=12, minute=0,
            timezone_str=req.timezone_str,
            latitude=req.latitude, longitude=req.longitude,
        )
        solar = _make_kerykeion_subject('solar', solar_req)
        result = calculate_transit_activations(natal, solar, req.solar_year)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profections")
async def profections(req: KerykeionRequest):
    """Профекции."""
    import sys
    sys.path.insert(0, str(ROOT / 'astro'))
    from profections_calculator import calculate_profections

    try:
        natal = _make_kerykeion_subject('natal', req)
        solar_req = KerykeionRequest(
            year=req.solar_year, month=req.month, day=req.day,
            hour=12, minute=0,
            timezone_str=req.timezone_str,
            latitude=req.latitude, longitude=req.longitude,
        )
        solar = _make_kerykeion_subject('solar', solar_req)
        result = calculate_profections(natal, solar)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================
# КАРТА: ТОЛЬКО КРУГ (для реалтайм обновления)
# ============================================================

@app.get("/chart-wheel")
async def chart_wheel_natal():
    """Круг натальной карты (wheel only) — для реалтайм."""
    from kerykeion import AstrologicalSubject, KerykeionChartSVG
    from fastapi.responses import Response
    import os, tempfile

    try:
        subject = AstrologicalSubject(
            'chart', 1961, 1, 30, 20, 57,
            lng=70.34136, lat=54.42985, tz_str='Asia/Almaty',
            city='calc', nation='XX', online=False,
        )
        td = tempfile.gettempdir()
        chart = KerykeionChartSVG(subject, chart_type='Natal',
            theme='dark-high-contrast', chart_language='RU', new_output_directory=td)
        chart.makeWheelOnlySVG()

        for f in os.listdir(td):
            if f.endswith('.svg') and 'Wheel' in f and 'Natal' in f:
                path = os.path.join(td, f)
                with open(path, 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                    svg = svg.replace("width='100%'", "width='550'").replace("height='100%'", "height='550'")
                    return Response(content=svg, media_type="image/svg+xml")
        raise HTTPException(status_code=500, detail="SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




def _дорисовать_тж(svg, req, второй=None, асцендент=None):
    """Ставит Точку Жизни на колесо.

    ⚠️ Его правило 05.09: ТЖ нужна ТОЛЬКО там, где есть прожитое время —
    транзиты и соляр. В натале она всегда в нуле Овна у всех, показывать
    бессмысленно. В синастрии две неподвижные карты — тоже ни к чему.
    """
    try:
        from tochka_zhizni_svg import дорисовать_на_колесе
        from engine.tzh import градус_тж
        from datetime import datetime, timezone
        т = градус_тж(datetime(req.year, req.month, req.day,
                               req.hour, req.minute, tzinfo=timezone.utc),
                      datetime.now(timezone.utc))
        г = т.get("градус") if isinstance(т, dict) else т
        if асцендент is None:
            асцендент = _make_kerykeion_subject('tzh', req).first_house.abs_pos
        return дорисовать_на_колесе(svg, float(г), асцендент=асцендент)
    except Exception:
        return svg

@app.post("/chart-wheel-transit")
async def chart_wheel_transit(req: KerykeionRequest, theme: str = "dark-high-contrast"):
    """Круг натал+транзит (wheel only) — для реалтайм каждую секунду."""
    from kerykeion import AstrologicalSubject, KerykeionChartSVG
    from fastapi.responses import Response
    from datetime import datetime
    import os, tempfile

    try:
        natal = _make_kerykeion_subject('natal', req)
        from datetime import timezone as _tz, timedelta as _td
        now = datetime.now(_tz.utc) + _td(seconds=30)
        _tlat = req.tr_lat if req.tr_lat is not None else req.latitude
        _tlon = req.tr_lon if req.tr_lon is not None else req.longitude
        transit = AstrologicalSubject(
            'Transit', now.year, now.month, now.day,
            now.hour, now.minute,
            lng=_tlon, lat=_tlat,
            tz_str='UTC', city='calc', nation='XX', online=False,
        )
        td = tempfile.gettempdir()
        chart = KerykeionChartSVG(natal, chart_type='Transit', second_obj=transit,
            theme=theme, chart_language='RU', new_output_directory=td)
        chart.makeWheelOnlySVG()

        for f in os.listdir(td):
            if f.endswith('.svg') and 'Wheel' in f and 'Transit' in f:
                path = os.path.join(td, f)
                with open(path, 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                # реальный размер круга из viewBox вместо width/height='100%'
                _v = svg.find('viewBox=')
                if _v != -1:
                    _q = svg[_v + 8]
                    _vb = svg[_v + 9:svg.find(_q, _v + 9)].split()
                    if len(_vb) == 4:
                        _w = str(int(float(_vb[2])))
                        _h = str(int(float(_vb[3])))
                        svg = svg.replace("width='100%'", "width='" + _w + "'", 1)
                        svg = svg.replace("height='100%'", "height='" + _h + "'", 1)
                svg = _дорисовать_тж(svg, req)
                return Response(content=svg, media_type="image/svg+xml")
        raise HTTPException(status_code=500, detail="SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================
# КОЛЕСО ЗАКАЗА · транзиты и соляр одной кнопкой (05.09.2026, вечер)
#   внутри — натал с домами (время есть) или космограмма по солнечному
#   часу (времени нет), снаружи — кольцо момента: «сейчас» для транзитов,
#   возвращение Солнца для соляра. Сверху — Точка Жизни.
#   Старые маршруты не тронуты: это надстройка над ними.
# ============================================================

class КолесоЗаказа(BaseModel):
    zakaz: str = "tranzity"               # tranzity | solyar
    year: int; month: int; day: int
    hour: int = 0; minute: int = 0; second: int = 0
    vremya_izvestno: bool = True          # False → космограмма по солнечному часу
    timezone_str: Optional[str] = None
    gmt: float = 0.0
    latitude: float; longitude: float
    tr_lat: Optional[float] = None        # место «сейчас» (кольцо)
    tr_lon: Optional[float] = None
    god_solyara: Optional[int] = None     # None → действующий год соляра
    theme: str = "dark-high-contrast"
    koltso: bool = True                   # False → только внутренняя карта, без кольца
    tochka_zhizni: bool = True            # False → без Точки Жизни (натал)
    view: str = "wheel"                   # wheel — колесо; tables — таблицы Кериkeion к той же паре карт
    moment_utc: Optional[str] = None      # транзиты на заданный момент (ISO, UTC); None → сейчас


def _действующий_год_соляра(month, day):
    """Год последнего дня рождения: до дня рождения — прошлый год."""
    сег = datetime.now(timezone.utc)
    return сег.year if (сег.month, сег.day) >= (month, day) else сег.year - 1


@app.post("/chart-wheel-zakaz")
async def chart_wheel_zakaz(req: КолесоЗаказа):
    from kerykeion import KerykeionChartSVG
    from datetime import timedelta as _td
    import os, tempfile

    try:
        _проверить_вход(req.latitude, req.longitude, req.gmt, req.year, "рождение")
        зона_р = f"Etc/GMT{'-' if req.gmt >= 0 else '+'}{abs(int(req.gmt))}"

        # ── внутренняя карта ──
        if req.vremya_izvestno:
            суб = KerykeionRequest(
                year=req.year, month=req.month, day=req.day,
                hour=req.hour, minute=req.minute, second=req.second,
                timezone_str=req.timezone_str or зона_р,
                latitude=req.latitude, longitude=req.longitude)
            рождение_utc = datetime(req.year, req.month, req.day, req.hour, req.minute,
                                    req.second, tzinfo=timezone.utc) - _td(hours=req.gmt)
            солнечный_час, солнце_на_асц = "", None
        else:
            точно, разрыв = _солнечный_час(req.year, req.month, req.day,
                                           req.latitude, req.longitude, req.gmt)
            солнце_на_асц = разрыв <= ПОРОГ_СОЛНЕЧНОГО_ЧАСА
            if not солнце_на_асц:
                точно = datetime(req.year, req.month, req.day, 12, 0) - _td(hours=req.gmt)
            мест = точно + _td(hours=req.gmt)
            суб = KerykeionRequest(
                year=мест.year, month=мест.month, day=мест.day,
                hour=мест.hour, minute=мест.minute, second=мест.second,
                timezone_str=зона_р, latitude=req.latitude, longitude=req.longitude)
            рождение_utc = точно.replace(tzinfo=timezone.utc)
            солнечный_час = мест.strftime("%H:%M:%S")
        натал = _make_kerykeion_subject('natal', суб)

        # ── момент кольца ──
        ш = req.tr_lat if req.tr_lat is not None else req.latitude
        д = req.tr_lon if req.tr_lon is not None else req.longitude
        _проверить_вход(ш, д, 0, req.year, "место сейчас")
        сведения = {}
        if req.zakaz == "solyar":
            from engine.situacia import момент_соляра
            год = req.god_solyara or _действующий_год_соляра(req.month, req.day)
            св = момент_соляра(рождение_utc, год)
            момент = св["момент"]
            сведения = {"god": год,
                        "rashozhdenie_sek": св["расхождение_сек"],
                        "moment_utc": момент.strftime("%d.%m.%Y %H:%M:%S")}
            имя_кольца = 'Solar'
        else:
            момент = datetime.now(timezone.utc)
            if req.moment_utc:
                try:
                    момент = datetime.fromisoformat(req.moment_utc.replace("Z", "+00:00"))
                    момент = (момент.astimezone(timezone.utc) if момент.tzinfo else момент.replace(tzinfo=timezone.utc))
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"moment_utc не разобран: {req.moment_utc}")
            сведения = {"moment_utc": момент.strftime("%d.%m.%Y %H:%M:%S")}
            имя_кольца = 'Transit'
        суб_к = KerykeionRequest(
            year=момент.year, month=момент.month, day=момент.day,
            hour=момент.hour, minute=момент.minute, second=момент.second,
            timezone_str='UTC', latitude=ш, longitude=д)
        кольцо = _make_kerykeion_subject(имя_кольца, суб_к)

        # ── колесо ──
        td = tempfile.gettempdir()
        for f in os.listdir(td):
            if f.endswith('.svg') and 'Transit' in f and 'Wheel' in f:
                try: os.remove(os.path.join(td, f))
                except Exception: pass
        if req.koltso:
            chart = KerykeionChartSVG(натал, chart_type='Transit', second_obj=кольцо,
                                      theme=req.theme, chart_language='RU',
                                      new_output_directory=td)
        else:
            for f in os.listdir(td):
                if f.endswith('.svg') and f.startswith('natal') and 'Wheel' in f:
                    try: os.remove(os.path.join(td, f))
                    except Exception: pass
            chart = KerykeionChartSVG(натал, chart_type='Natal', theme=req.theme,
                                      chart_language='RU', new_output_directory=td)
        if req.view == "tables":
            # таблицы Кериkeion к этой же паре карт — тем же обрезом, что у синастрии
            тип = 'Transit' if req.koltso else 'Natal'
            for f in os.listdir(td):
                if f.endswith('.svg') and f.startswith('natal') and 'Wheel' not in f and 'Grid' not in f:
                    try: os.remove(os.path.join(td, f))
                    except Exception: pass
            chart.makeSVG()
            for f in os.listdir(td):
                if f.endswith('.svg') and f.startswith('natal') and 'Wheel' not in f and 'Grid' not in f and (тип + ' Chart') in f:
                    with open(os.path.join(td, f), 'r', encoding='utf-8') as sf:
                        html = _crop_svg_to_chart(sf.read(), cut_override=(595 if req.koltso else None))
                    if not req.vremya_izvestno:
                        html = _спрятать_дома_в_таблицах(html, True)
                    return {"tables": html, "zakaz": req.zakaz, "vremya_izvestno": req.vremya_izvestno, **сведения}
            raise HTTPException(status_code=500, detail="таблицы не построились")
        chart.makeWheelOnlySVG()
        svg = None
        for f in os.listdir(td):
            if f.endswith('.svg') and 'Wheel' in f and f.startswith('natal'):
                if req.koltso and 'Transit' not in f: continue
                if not req.koltso and 'Transit' in f: continue
                with open(os.path.join(td, f), 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                break
        if not svg:
            raise HTTPException(status_code=500, detail="колесо не построилось")
        _v = svg.find('viewBox=')
        if _v != -1:
            _q = svg[_v + 8]
            _vb = svg[_v + 9:svg.find(_q, _v + 9)].split()
            if len(_vb) == 4:
                svg = svg.replace("width='100%'", "width='" + str(int(float(_vb[2]))) + "'", 1)
                svg = svg.replace("height='100%'", "height='" + str(int(float(_vb[3]))) + "'", 1)
        if req.koltso:
            # значки As/Mc/Ds/Ic кольца, которые Кериkeion ставит во внешнем ряду (жёлтые), гасим —
            # углы кольца рисует страница своим цветом (соляр зелёный, транзиты оранжевый)
            import re as _re
            svg = _re.sub(r"(?:<line class='transit-planet-line'[^>]*/>\s*)?(?:<g transform='translate\([^)]*\)'><text[^>]*>[^<]*</text></g>\s*)?<g class='transit-planet-name'[^>]*><g[^>]*><use [^>]*href='#(?:Ascendant|Medium_Coeli|Descendant|Imum_Coeli)' /></g></g>",
                          lambda м: "<g style='display:none'>" + м.group(0) + "</g>", svg)
        if req.tochka_zhizni:
            svg = _дорисовать_тж(svg, суб, асцендент=натал.first_house.abs_pos)

        # Дома и углы кольца (транзитного момента / соляра) — страница рисует их своим красным слоем,
        # как живые дома: Кериkeion кладёт их во внешнее кольцо слишком бледно
        try:
            сведения["kuspidy_koltsa"] = [round(getattr(кольцо, h).abs_pos, 4) for h in
                ('first_house','second_house','third_house','fourth_house','fifth_house','sixth_house',
                 'seventh_house','eighth_house','ninth_house','tenth_house','eleventh_house','twelfth_house')]
        except Exception:
            pass
        # Селена (Белая Луна) — Кериkeion её не рисует, страница дорисует сама: натальная и на момент кольца
        try:
            from engine.natal import _compute_selena as _сел
            import swisseph as _swe2
            _jd = lambda т: _swe2.julday(т.year, т.month, т.day, т.hour + т.minute / 60.0 + т.second / 3600.0)
            сведения["selena_natal"] = round(_сел(_jd(рождение_utc)), 4)
            сведения["selena_koltso"] = round(_сел(_jd(момент)), 4)
        except Exception:
            pass
        return {"svg": svg, "zakaz": req.zakaz,
                "asc_vnutri": round(натал.first_house.abs_pos, 4),   # градус разворота колеса (АС натала / Солнце космограммы) — для слоёв страницы
                "vremya_izvestno": req.vremya_izvestno,
                "solnechnyy_chas": солнечный_час,
                "solnce_na_ascendente": солнце_на_асц,
                **сведения}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chart-wheel-natal")
async def chart_wheel_natal_body(req: KerykeionRequest, theme: str = "dark-high-contrast"):
    """Круг ТОЛЬКО натал (wheel only) из тела запроса — надёжный путь makeWheelOnlySVG, для режима без транзита."""
    from kerykeion import KerykeionChartSVG
    from fastapi.responses import Response
    import os, tempfile

    try:
        natal = _make_kerykeion_subject('natal', req)
        td = tempfile.gettempdir()
        chart = KerykeionChartSVG(natal, chart_type='Natal',
            theme=theme, chart_language='RU', new_output_directory=td)
        chart.makeWheelOnlySVG()

        for f in os.listdir(td):
            if f.endswith('.svg') and 'Wheel' in f and 'Natal' in f and 'Transit' not in f:
                path = os.path.join(td, f)
                with open(path, 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                _v = svg.find('viewBox=')
                if _v != -1:
                    _q = svg[_v + 8]
                    _vb = svg[_v + 9:svg.find(_q, _v + 9)].split()
                    if len(_vb) == 4:
                        _w = str(int(float(_vb[2])))
                        _h = str(int(float(_vb[3])))
                        svg = svg.replace("width='100%'", "width='" + _w + "'", 1)
                        svg = svg.replace("height='100%'", "height='" + _h + "'", 1)
                return Response(content=svg, media_type="image/svg+xml")
        raise HTTPException(status_code=500, detail="SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# КАРТА: ТОЛЬКО ТАБЛИЦЫ (статичные, без круга)
# ============================================================

@app.post("/chart-tables")
async def chart_tables(req: KerykeionRequest, chart_type: str = "Natal", data_only: bool = False, theme: str = "dark-high-contrast"):
    """Таблицы kerykeion без круга — статичные."""
    from kerykeion import AstrologicalSubject, KerykeionChartSVG
    from fastapi.responses import Response
    from datetime import datetime
    import os, tempfile

    try:
        natal = _make_kerykeion_subject('natal', req)
        td = tempfile.gettempdir()

        if chart_type == 'Transit':
            now = datetime.now()
            transit = AstrologicalSubject(
                'Transit', now.year, now.month, now.day,
                now.hour, now.minute,
                lng=req.longitude, lat=req.latitude,
                tz_str=req.timezone_str, city='calc', nation='XX', online=False,
            )
            chart = KerykeionChartSVG(natal, chart_type='Transit', second_obj=transit,
                theme=theme, chart_language='RU', new_output_directory=td)
        else:
            chart = KerykeionChartSVG(natal, chart_type='Natal',
                theme=theme, chart_language='RU', new_output_directory=td)

        chart.makeSVG()

        for f in os.listdir(td):
            if f.endswith('.svg') and 'Wheel' not in f and 'Grid' not in f and (chart_type in f):
                path = os.path.join(td, f)
                with open(path, 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                cropped = _crop_svg_to_chart(svg, data_only=data_only, cut_override=(595 if chart_type == 'Transit' else None))
                return Response(content=cropped, media_type="image/svg+xml")
        raise HTTPException(status_code=500, detail="SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chart-aspects")
async def chart_aspects(req: KerykeionRequest, chart_type: str = "Natal", theme: str = "dark-high-contrast"):
    """Аспектная сетка kerykeion отдельно — для горизонтальной раскладки."""
    from kerykeion import AstrologicalSubject, KerykeionChartSVG
    from fastapi.responses import Response
    from datetime import datetime
    import os, tempfile

    try:
        natal = _make_kerykeion_subject('natal', req)
        td = tempfile.gettempdir()

        if chart_type == 'Transit':
            now = datetime.now()
            transit = AstrologicalSubject(
                'Transit', now.year, now.month, now.day,
                now.hour, now.minute,
                lng=req.longitude, lat=req.latitude,
                tz_str=req.timezone_str, city='calc', nation='XX', online=False,
            )
            chart = KerykeionChartSVG(natal, chart_type='Transit', second_obj=transit,
                theme=theme, chart_language='RU', new_output_directory=td)
        else:
            chart = KerykeionChartSVG(natal, chart_type='Natal',
                theme=theme, chart_language='RU', new_output_directory=td)

        chart.makeAspectGridOnlySVG()

        for f in os.listdir(td):
            if f.endswith('.svg') and 'Aspect Grid' in f and (chart_type in f):
                path = os.path.join(td, f)
                with open(path, 'r', encoding='utf-8') as sf:
                    svg = sf.read()
                # реальный размер из viewBox вместо width/height='100%'
                _v = svg.find('viewBox=')
                if _v != -1:
                    _q = svg[_v + 8]
                    _vb = svg[_v + 9:svg.find(_q, _v + 9)].split()
                    if len(_vb) == 4:
                        _w = str(int(float(_vb[2])))
                        _h = str(int(float(_vb[3])))
                        svg = svg.replace("width='100%'", "width='" + _w + "'", 1)
                        svg = svg.replace("height='100%'", "height='" + _h + "'", 1)
                return Response(content=svg, media_type="image/svg+xml")
        raise HTTPException(status_code=500, detail="Aspect SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chart-svg")
async def chart_svg(req: KerykeionRequest, theme: str = "dark-high-contrast"):
    """
    Генерирует профессиональную SVG-карту через kerykeion.
    Темы: classic (светлая), dark, dark-high-contrast
    """
    from kerykeion import KerykeionChartSVG
    from fastapi.responses import Response
    import os

    try:
        subject = _make_kerykeion_subject('chart', req)
        chart = KerykeionChartSVG(
            subject,
            chart_type='Natal',
            theme=theme,
            chart_language='RU',
            new_output_directory=__import__('tempfile').gettempdir(),
        )
        chart.makeSVG()

        _td = __import__('tempfile').gettempdir()
        svg_path = None
        for f in os.listdir(_td):
            if f.endswith('.svg') and 'Natal' in f:
                svg_path = os.path.join(_td, f)
        if not svg_path:
            raise HTTPException(status_code=500, detail='SVG not generated')

        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()

        return Response(content=_crop_svg_to_chart(svg_content), media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chart-svg-transit")
async def chart_svg_transit(req: KerykeionRequest, theme: str = "dark-high-contrast"):
    """Натал + транзиты SVG."""
    from kerykeion import AstrologicalSubject, KerykeionChartSVG
    from fastapi.responses import Response
    from datetime import datetime
    import os

    try:
        natal = _make_kerykeion_subject('natal', req)

        now = datetime.now()
        transit = AstrologicalSubject(
            'Transit', now.year, now.month, now.day,
            now.hour, now.minute,
            lng=req.longitude, lat=req.latitude,
            tz_str=req.timezone_str,
            city='calc', nation='XX',
            online=False,
        )

        chart = KerykeionChartSVG(
            natal,
            chart_type='Transit',
            second_obj=transit,
            theme=theme,
            chart_language='RU',
            new_output_directory=__import__('tempfile').gettempdir(),
        )
        chart.makeSVG()

        _td = __import__('tempfile').gettempdir()
        for f in os.listdir(_td):
            if f.endswith('.svg') and 'Transit' in f:
                svg_path = os.path.join(_td, f)
                with open(svg_path, 'r', encoding='utf-8') as sf:
                    return Response(content=_crop_svg_to_chart(sf.read()), media_type="text/html")

        raise HTTPException(status_code=500, detail="SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SynastryChartRequest(BaseModel):
    client: KerykeionRequest
    operator: KerykeionRequest
    client_vremya: bool = True        # 06.09: False → космограмма по солнечному часу
    operator_vremya: bool = True




def _спрятать_дома_в_таблицах(html, внутри_без_времени, снаружи_без_времени=False):
    """Таблицы Кериkeion без времени: убираем домов и углы того, чьё время неизвестно.
    Сетки Кериkeion помечены: Main_Houses_Grid (внутренняя карта), Secondary_Houses_Grid
    (внешняя), House_Comparison_Table (планеты кольца по домам внутренней карты);
    строки Асц/МС/ДСЦ/IC — в сетках планет."""
    import re as _re
    def _гасить(узел):
        nonlocal html
        html = html.replace(f"<g kr:node='{узел}'", f"<g kr:node='{узел}' style='display:none'", 1)
    if внутри_без_времени:
        _гасить('Main_Houses_Grid'); _гасить('House_Comparison_Table')
    if снаружи_без_времени:
        _гасить('Secondary_Houses_Grid')
    def _углы(сетка):
        nonlocal html
        а = html.find(f"<g kr:node='{сетка}'")
        if а < 0: return
        б = html.find("<g kr:node=", а + 10)
        кусок = html[а:б]
        кусок = _re.sub(r"<g transform='translate\(0,\d+\)'>(<text[^>]*>(?:Асц|МС|ДСЦ|IC|Asc|MC|DSC|Ic)</text>)",
                        lambda м: м.group(0).replace("<g transform", "<g style='display:none' transform", 1), кусок)
        html = html[:а] + кусок + html[б:]
    if внутри_без_времени: _углы('Main_Planet_Grid')
    if снаружи_без_времени: _углы('Secondary_Planet_Grid')
    return html

# ── 06.09 · синастрия без времени — помощники ─────────────────────────────
def _смещение_часов(tz_str, год, месяц, день):
    """Сдвиг пояса в часах на эту дату (Etc/GMT-6 → +6, Asia/Omsk → по базе зон)."""
    import re as _re
    м = _re.match(r"Etc/GMT([+-])(\d+)$", tz_str or "")
    if м:
        return -float(м.group(2)) if м.group(1) == "+" else float(м.group(2))
    from datetime import datetime as _dt
    try:                                   # pytz стоит в requirements — он первый
        import pytz
        return pytz.timezone(tz_str).utcoffset(_dt(год, месяц, день, 12)).total_seconds() / 3600.0
    except Exception:
        pass
    try:
        from zoneinfo import ZoneInfo
        return _dt(год, месяц, день, 12, tzinfo=ZoneInfo(tz_str)).utcoffset().total_seconds() / 3600.0
    except Exception:
        return 0.0


def _субъект_без_времени(имя, req):
    """Космограмма: субъект Кериkeion на солнечный час дня рождения (Солнце = АС)."""
    from datetime import timedelta as _td
    сдвиг = _смещение_часов(req.timezone_str, req.year, req.month, req.day)
    точно, разрыв = _солнечный_час(req.year, req.month, req.day, req.latitude, req.longitude, сдвиг)
    if разрыв > ПОРОГ_СОЛНЕЧНОГО_ЧАСА:
        точно = datetime(req.year, req.month, req.day, 12, 0) - _td(hours=сдвиг)
    мест = точно + _td(hours=сдвиг)
    зона = f"Etc/GMT{'-' if сдвиг >= 0 else '+'}{abs(int(round(сдвиг)))}"
    суб = KerykeionRequest(year=мест.year, month=мест.month, day=мест.day,
                           hour=мест.hour, minute=мест.minute, second=мест.second,
                           timezone_str=зона, latitude=req.latitude, longitude=req.longitude)
    return _make_kerykeion_subject(имя, суб), мест.strftime("%H:%M:%S")


def _спрятать_дома_в_синастрии(svg, внутри_без_времени, снаружи_без_времени, куспиды_внутри, куспиды_снаружи):
    """Гасит домовые слои того, у кого времени нет.
    Куспиды узнаём по градусу (kr:absoluteposition), номера домов — по прозрачности
    (.6 внутренняя карта, .4 внешняя), буквы As/Ds/Mc/Ic — внутренней, значки углов
    во внешнем кольце — по классу transit-planet-name."""
    import re as _re
    def _близко(г, список):
        return any(min(abs(г - к) % 360, 360 - abs(г - к) % 360) < 0.01 for к in список)
    скрыть = []
    if внутри_без_времени:   скрыть.append(куспиды_внутри)
    if снаружи_без_времени:  скрыть.append(куспиды_снаружи)
    def _куспид(м):
        г = float(м.group(1))
        if any(_близко(г, сп) for сп in скрыть):
            return м.group(0).replace("<g kr:node='Cusp'", "<g kr:node='Cusp' style='display:none'", 1)
        return м.group(0)
    svg = _re.sub(r"<g kr:node='Cusp' kr:absoluteposition='([\d.]+)'[^>]*>", _куспид, svg)
    def _номер(м):
        блок = м.group(0)
        if (внутри_без_времени and "fill-opacity: .6" in блок) or (снаружи_без_времени and "fill-opacity: .4" in блок):
            return блок.replace("<g kr:node='HouseNumber'>", "<g kr:node='HouseNumber' style='display:none'>", 1)
        return блок
    svg = _re.sub(r"<g kr:node='HouseNumber'>.*?</g>", _номер, svg, flags=_re.S)
    if внутри_без_времени:
        def _буква(м):
            тег = м.group(1)
            if "style='" in тег:
                тег = тег.replace("style='", "style='display:none;", 1)
            else:
                тег += " style='display:none'"
            return тег + м.group(2)
        svg = _re.sub(r"(<text[^>]*)(>\s*(?:As|Ds|Mc|Ic)\s*</text>)", _буква, svg)
    if снаружи_без_времени:
        svg = _re.sub(r"(?:<line class='transit-planet-line'[^>]*/>\s*)?(?:<g transform='translate\([^)]*\)'><text[^>]*>[^<]*</text></g>\s*)?<g class='transit-planet-name'[^>]*><g[^>]*><use [^>]*href='#(?:Ascendant|Medium_Coeli|Descendant|Imum_Coeli)' /></g></g>",
                      lambda м: "<g style='display:none'>" + м.group(0) + "</g>", svg)
    return svg

@app.post("/chart-svg-synastry")
async def chart_svg_synastry(req: SynastryChartRequest, theme: str = "dark-high-contrast", view: str = "full"):
    """Синастрия — два натала на одной карте. view: wheel|tables|full."""
    from kerykeion import KerykeionChartSVG
    from fastapi.responses import Response
    import os, tempfile

    try:
        # 06.09, его правило: у кого время есть — тот внутрь с домами и АС; у кого нет —
        # космограмма по солнечному часу без домов; если время только у партнёра — он внутрь.
        сч1 = сч2 = ""
        if req.client_vremya:
            subject1 = _make_kerykeion_subject('оператор', req.client)
        else:
            subject1, сч1 = _субъект_без_времени('оператор', req.client)
        if req.operator_vremya:
            subject2 = _make_kerykeion_subject('клиент', req.operator)
        else:
            subject2, сч2 = _субъект_без_времени('клиент', req.operator)
        внутри = "client"
        if (not req.client_vremya) and req.operator_vremya:
            subject1, subject2 = subject2, subject1
            внутри = "operator"
        внутри_бв = not (req.client_vremya if внутри == "client" else req.operator_vremya)
        снаружи_бв = not (req.operator_vremya if внутри == "client" else req.client_vremya)
        _td = tempfile.gettempdir()
        for _old in os.listdir(_td):
            if _old.endswith('.svg') and 'Synastry' in _old:
                try:
                    os.remove(os.path.join(_td, _old))
                except Exception:
                    pass
        chart = KerykeionChartSVG(
            subject1,
            chart_type='Synastry',
            second_obj=subject2,
            theme=theme,
            chart_language='RU',
            new_output_directory=_td,
        )

        if view == 'wheel':
            chart.makeWheelOnlySVG()
            for f in os.listdir(_td):
                if f.endswith('.svg') and 'Synastry' in f and 'Wheel' in f:
                    with open(os.path.join(_td, f), 'r', encoding='utf-8') as sf:
                        svg = sf.read()
                    _v = svg.find('viewBox=')
                    if _v != -1:
                        _q = svg[_v + 8]
                        _vb = svg[_v + 9:svg.find(_q, _v + 9)].split()
                        if len(_vb) == 4:
                            _w = str(int(float(_vb[2])))
                            _h = str(int(float(_vb[3])))
                            svg = svg.replace("width='100%'", "width='" + _w + "'", 1)
                            svg = svg.replace("height='100%'", "height='" + _h + "'", 1)
                    if внутри_бв or снаружи_бв:
                        _к = lambda с: [getattr(с, h).abs_pos for h in ('first_house','second_house','third_house','fourth_house','fifth_house','sixth_house','seventh_house','eighth_house','ninth_house','tenth_house','eleventh_house','twelfth_house')]
                        svg = _спрятать_дома_в_синастрии(svg, внутри_бв, снаружи_бв, _к(subject1), _к(subject2))
                    return Response(content=svg, media_type="image/svg+xml",
                                    headers={"X-Vnutri": внутри,
                                             "X-Vnutri-Bez-Vremeni": "1" if внутри_бв else "0",
                                             "X-Snaruzhi-Bez-Vremeni": "1" if снаружи_бв else "0",
                                             "X-Solnechnyy-Chas": (сч1 + "|" + сч2)})
        else:
            chart.makeSVG()
            for f in os.listdir(_td):
                if f.endswith('.svg') and 'Synastry' in f and 'Wheel' not in f and 'Grid' not in f:
                    with open(os.path.join(_td, f), 'r', encoding='utf-8') as sf:
                        html = _crop_svg_to_chart(sf.read(), cut_override=595)
                    if внутри_бв or снаружи_бв:
                        html = _спрятать_дома_в_таблицах(html, внутри_бв, снаружи_бв)
                    return Response(content=html, media_type="text/html")

        raise HTTPException(status_code=500, detail="SVG not generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ЗАПУСК
# ============================================================

@app.post("/interpret")
async def interpret(req: NatalRequest, model: str = "anthropic/claude-sonnet-4-6"):
    """
    Полный цикл: натал → фракталы → ИИ трактовка.
    Одна кнопка — полная трактовка.
    """
    from engine.cascade_assembler import assemble_full_natal
    from engine.interpret import interpret_natal

    try:
        chart = await natal_chart(req)
        db = get_db()
        cascade = assemble_full_natal(chart, levels=4, db=db)
        interpretation = await interpret_natal(cascade['markers_text'], model)
        return {
            "interpretation": interpretation,
            "markers": cascade['markers_text'],
            "summary": cascade['summary'],
            "model": model,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interpret-deep")
async def interpret_deep_endpoint(req: NatalRequest):
    """Глубокая трактовка через Opus 4.8 — сценарий души."""
    from engine.cascade_assembler import assemble_full_natal
    from engine.interpret import interpret_deep

    try:
        chart = await natal_chart(req)
        db = get_db()
        cascade = assemble_full_natal(chart, levels=4, db=db)
        interpretation = await interpret_deep(cascade['markers_text'])
        return {
            "interpretation": interpretation,
            "markers": cascade['markers_text'],
            "model": "anthropic/claude-opus-4-8",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    """
    Диалог «Обсудить главу с Квантареоном».
    Публичный (без пароля) — используется виджетом на quantareon.com.
    Защита: ограничение длины истории и вопроса на уровне engine/chat.py.
    """
    from chat import chat_with_quantareon

    history = [m.model_dump() for m in (req.history or [])]
    result = await chat_with_quantareon(
        question=req.question,
        essay=req.essay,
        lang=req.lang,
        part=req.part,
        history=history,
        include_full=req.include_full,
        chapter=req.chapter,
    )
    return result


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...), language: str = "ru"):
    """Речь -> текст для голосового ввода в чате Квантареона. Публичный."""
    from chat import transcribe_audio
    audio = await file.read()
    result = await transcribe_audio(audio, filename=file.filename or "voice.webm",
                                    language=language)
    return result


class TtsRequest(BaseModel):
    text: str = Field(..., description="Текст ответа для озвучки")
    language: str = Field("ru", description="ru — Дмитрий, en — Эндрю")


@app.post("/tts")
async def tts_endpoint(req: TtsRequest):
    """Озвучка ответа Квантареона. Поток mp3: первый кусок играет,
    пока следующие синтезируются. Публичный."""
    from fastapi.responses import StreamingResponse
    from chat import tts_stream

    text = (req.text or "").strip()[:6000]
    if not text:
        from fastapi.responses import Response
        return Response(status_code=400)

    lang = "en" if req.language == "en" else "ru"
    return StreamingResponse(tts_stream(text, language=lang), media_type="audio/mpeg")


@app.websocket("/stt-stream")
async def stt_stream(ws: WebSocket):
    """
    Живое распознавание речи: браузер шлёт сырой звук (PCM 16 кГц),
    мы перекладываем его в Deepgram и возвращаем текст по мере речи.
    """
    import asyncio, json
    from chat import open_deepgram

    await ws.accept()
    lang = ws.query_params.get("lang", "ru")

    dg = await open_deepgram(lang)
    if dg is None:
        await ws.send_json({"type": "error", "error": "deepgram_unavailable"})
        await ws.close()
        return

    # Явно подтверждаем браузеру: Deepgram на связи, можно слать звук
    await ws.send_json({"type": "ready"})

    async def pump_from_deepgram():
        """Текст от Deepgram — в браузер."""
        try:
            async for raw in dg:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("type") != "Results":
                    continue
                alts = (data.get("channel") or {}).get("alternatives") or []
                if not alts:
                    continue
                text = (alts[0].get("transcript") or "").strip()
                if not text:
                    continue
                await ws.send_json({
                    "type": "transcript",
                    "text": text,
                    "final": bool(data.get("is_final")),
                })
        except Exception:
            pass

    async def keepalive():
        """Deepgram рвёт молчащее соединение — держим его живым."""
        try:
            while True:
                await asyncio.sleep(5)
                await dg.send(json.dumps({"type": "KeepAlive"}))
        except Exception:
            pass

    task_dg = asyncio.create_task(pump_from_deepgram())
    task_ka = asyncio.create_task(keepalive())

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            chunk = msg.get("bytes")
            if chunk:
                await dg.send(chunk)
            elif msg.get("text") == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await dg.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass
        task_ka.cancel()
        task_dg.cancel()
        try:
            await dg.close()
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# статика — в самом конце, чтоб не перебивала эндпоинты
app.mount("/", StaticFiles(directory=str(FRONT), html=True), name="front")


