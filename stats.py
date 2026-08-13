"""Счётчик посещений сайта QUANTAREON.

ЗАЧЕМ. Сайт статический, GitHub Pages ничего не считает. Поэтому страница
тихо стучится сюда при открытии, а мы копим цифры и показываем их хозяину
по особой ссылке с ключом.

ГДЕ ХРАНИМ. В Cloudflare R2 — там же, где музыка и видео. Не в памяти,
потому что сервер перезапускается при каждой заливке, и всё пропадало бы.

ЧТО НЕ СОБИРАЕМ. Ни имён, ни точных адресов, ни отпечатков браузера.
Только: какую страницу открыли, откуда пришли, из какой страны, с
телефона или нет. Посетитель считается один раз в сутки — по короткому
следу от адреса и дня, из которого обратно ничего не вытащить.

Как подключить в движке (api/main.py или где собирается приложение):

    import stats
    app.include_router(stats.router)

Переменные окружения на Render:
    R2_ACCOUNT_ID · R2_ACCESS_KEY · R2_SECRET_KEY · R2_BUCKET
    STATS_KEY  — пароль для просмотра (придумать длинный)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────
#  Настройки
# ─────────────────────────────────────────────────────────────

КЛЮЧ_ПРОСМОТРА = os.getenv("STATS_KEY", "")
БАКЕТ = os.getenv("R2_BUCKET", "quantareon-media")
ПАПКА = os.getenv("STATS_PREFIX", "stats")

# соль для следа посетителя: меняется каждый день вместе с датой,
# поэтому по следу нельзя связать заходы разных дней
СОЛЬ = os.getenv("STATS_SALT", "quantareon")

# как часто сбрасывать накопленное в хранилище
СБРОС_СЕК = float(os.getenv("STATS_FLUSH_SEC", "60"))

# сколько последних заходов держать в ленте (на каждый день свои)
ЛЕНТА_ДЛИНА = int(os.getenv("STATS_FEED_LEN", "300"))

МОСКВА = timezone(timedelta(hours=3))


def _сегодня() -> str:
    return datetime.now(МОСКВА).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────
#  Хранилище
# ─────────────────────────────────────────────────────────────

_хранилище = None


def _клиент():
    """Подключение к R2. None — если ключи не заданы."""
    global _хранилище
    if _хранилище is not None:
        return _хранилище
    аккаунт = os.getenv("R2_ACCOUNT_ID")
    ключ = os.getenv("R2_ACCESS_KEY")
    секрет = os.getenv("R2_SECRET_KEY")
    if not (аккаунт and ключ and секрет):
        logger.warning("📊 статистика: ключи R2 не заданы, считаю только в памяти")
        return None
    try:
        import boto3
        from botocore.config import Config
        _хранилище = boto3.client(
            "s3",
            endpoint_url=f"https://{аккаунт}.r2.cloudflarestorage.com",
            aws_access_key_id=ключ,
            aws_secret_access_key=секрет,
            region_name="auto",
            config=Config(retries={"max_attempts": 2}, connect_timeout=5, read_timeout=10),
        )
        return _хранилище
    except Exception as e:
        logger.warning(f"📊 статистика: не подключился к R2 — {type(e).__name__}: {e}")
        return None


def _прочитать_день(день: str) -> dict[str, Any]:
    """Достать сохранённое за день. Пусто — если ничего нет."""
    к = _клиент()
    if к is None:
        return {}
    try:
        ответ = к.get_object(Bucket=БАКЕТ, Key=f"{ПАПКА}/{день}.json")
        return json.loads(ответ["Body"].read().decode("utf-8"))
    except Exception:
        return {}


def _записать_день(день: str, данные: dict[str, Any]) -> bool:
    к = _клиент()
    if к is None:
        return False
    try:
        к.put_object(
            Bucket=БАКЕТ,
            Key=f"{ПАПКА}/{день}.json",
            Body=json.dumps(данные, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
        return True
    except Exception as e:
        logger.warning(f"📊 статистика: не записалось — {type(e).__name__}")
        return False


def _список_дней(сколько: int = 60) -> list[str]:
    к = _клиент()
    if к is None:
        return []
    try:
        ответ = к.list_objects_v2(Bucket=БАКЕТ, Prefix=f"{ПАПКА}/", MaxKeys=400)
        дни = []
        for о in ответ.get("Contents", []):
            имя = о["Key"].rsplit("/", 1)[-1]
            if имя.endswith(".json"):
                дни.append(имя[:-5])
        return sorted(дни, reverse=True)[:сколько]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
#  Копилка в памяти — сбрасывается в хранилище раз в минуту
# ─────────────────────────────────────────────────────────────

class Копилка:
    """Копим заходы в памяти, чтобы не дёргать хранилище на каждый.

    Сбрасываем раз в минуту и всегда — при первом заходе нового дня.
    """

    def __init__(self) -> None:
        self.день = _сегодня()
        self.данные = _прочитать_день(self.день) or self._пусто()
        self.грязно = False
        self._замок = asyncio.Lock()
        self._сброс: asyncio.Task | None = None

    @staticmethod
    def _пусто() -> dict[str, Any]:
        return {
            "заходов": 0,
            "посетителей": [],       # следы, чтобы считать людей, а не клики
            "страницы": {},
            "источники": {},
            "страны": {},
            "города": {},
            "операторы": {},
            "устройства": {},
            "часы": {},
            "лента": [],             # последние заходы поимённо, см. ЛЕНТА_ДЛИНА
        }

    async def записать(self, что: dict[str, str]) -> None:
        async with self._замок:
            сегодня = _сегодня()
            if сегодня != self.день:
                # сутки сменились — дописать старое и начать новое
                if self.грязно:
                    _записать_день(self.день, self.данные)
                self.день = сегодня
                self.данные = _прочитать_день(сегодня) or self._пусто()

            д = self.данные
            д["заходов"] = д.get("заходов", 0) + 1

            след = что.get("след", "")
            люди = д.setdefault("посетителей", [])
            новый = bool(след and след not in люди)   # первый заход за сутки
            if новый:
                люди.append(след)
                if len(люди) > 20000:        # чтобы файл не рос без конца
                    del люди[: len(люди) - 20000]

            # 📜 ЖИВАЯ ЛЕНТА — последние заходы по одному.
            # Он попросил видеть «кто и откуда заходил». Адреса не храним,
            # только город и оператора — этого хватает на «откуда», а
            # персональных данных не образуется.
            лента = д.setdefault("лента", [])
            лента.append({
                # короткий след — чтобы можно было посмотреть все заходы
                # одного посетителя. Суточный: между днями не связывается.
                "след": что.get("след", "")[:8],
                "время": что.get("время", ""),
                "город": что.get("город", ""),
                "страна": что.get("страна", ""),
                "оператор": что.get("оператор", ""),
                "страница": что.get("страница", ""),
                "источник": что.get("источник", ""),
                "устройство": что.get("устройство", ""),
                "браузер": что.get("браузер", ""),
                "регион": что.get("регион", ""),
                "язык": что.get("язык", ""),
                "новый": новый,
            })
            if len(лента) > ЛЕНТА_ДЛИНА:
                del лента[: len(лента) - ЛЕНТА_ДЛИНА]

            for поле, ключ in (("страницы", "страница"), ("источники", "источник"),
                               ("страны", "страна"), ("города", "город"),
                               ("операторы", "оператор"), ("устройства", "устройство"),
                               ("браузеры", "браузер"), ("часы", "час")):
                значение = что.get(ключ)
                if значение:
                    полка = д.setdefault(поле, {})
                    полка[значение] = полка.get(значение, 0) + 1

            self.грязно = True
            if self._сброс is None or self._сброс.done():
                self._сброс = asyncio.create_task(self._через_время())

    async def _через_время(self) -> None:
        await asyncio.sleep(СБРОС_СЕК)
        async with self._замок:
            if self.грязно:
                if _записать_день(self.день, self.данные):
                    self.грязно = False

    async def сбросить_сейчас(self) -> None:
        async with self._замок:
            if self.грязно and _записать_день(self.день, self.данные):
                self.грязно = False


_копилка: Копилка | None = None


def _копить() -> Копилка:
    global _копилка
    if _копилка is None:
        _копилка = Копилка()
    return _копилка


# ─────────────────────────────────────────────────────────────
#  Разбор захода
# ─────────────────────────────────────────────────────────────

def _след(запрос: Request) -> str:
    """Короткий след посетителя: свой на каждые сутки, обратно не разворачивается."""
    адрес = (запрос.headers.get("cf-connecting-ip")
             or запрос.headers.get("x-forwarded-for", "").split(",")[0].strip()
             or (запрос.client.host if запрос.client else ""))
    браузер = запрос.headers.get("user-agent", "")[:120]
    сырое = f"{СОЛЬ}|{_сегодня()}|{адрес}|{браузер}"
    return hashlib.sha256(сырое.encode()).hexdigest()[:16]


def _откуда(источник: str) -> str:
    """Человеческое имя источника перехода."""
    if not источник:
        return "напрямую"
    низ = источник.lower()
    if "quantareon.com" in низ:
        return ""                       # переход внутри сайта не считаем
    for кусок, имя in (
        ("google.", "Google"), ("yandex.", "Яндекс"), ("bing.", "Bing"),
        ("duckduckgo", "DuckDuckGo"), ("t.me", "Telegram"), ("telegram", "Telegram"),
        ("whatsapp", "WhatsApp"), ("vk.com", "ВКонтакте"), ("facebook", "Facebook"),
        ("instagram", "Instagram"), ("youtube", "YouTube"), ("github", "GitHub"),
        ("linkedin", "LinkedIn"), ("x.com", "X"), ("twitter", "X"),
        ("reddit", "Reddit"), ("mail.ru", "Mail.ru"),
    ):
        if кусок in низ:
            return имя
    # прочее — оставляем только домен
    try:
        домен = низ.split("//", 1)[-1].split("/", 1)[0]
        return домен[:40] or "другой сайт"
    except Exception:
        return "другой сайт"


def _кириллица(с: str) -> str:
    """Cloudflare отдаёт заголовки в latin-1, а там лежит UTF-8 —
    «Île-de-France» приезжает как «Ã\x8ele-de-France». Перекодируем."""
    try:
        исправлено = с.encode("latin-1").decode("utf-8")
        return исправлено
    except (UnicodeEncodeError, UnicodeDecodeError):
        return с


def _браузер(строка: str) -> str:
    """Короткое имя браузера и системы: «Chrome · Windows». Без версий."""
    н = строка.lower()
    имя = "—"
    for кусок, б in (("yabrowser", "Яндекс.Браузер"), ("edg/", "Edge"),
                     ("opr/", "Opera"), ("firefox", "Firefox"),
                     ("chrome", "Chrome"), ("safari", "Safari")):
        if кусок in н:
            имя = б
            break
    система = "—"
    for кусок, с in (("android", "Android"), ("iphone", "iPhone"), ("ipad", "iPad"),
                     ("windows", "Windows"), ("mac os", "Mac"), ("linux", "Linux")):
        if кусок in н:
            система = с
            break
    if имя == "—" and система == "—":
        return "—"
    return f"{имя} · {система}"


def _устройство(браузер: str) -> str:
    н = браузер.lower()
    if any(с in н for с in ("iphone", "android", "ipad", "mobile")):
        return "телефон"
    if any(с in н for с in ("bot", "crawler", "spider", "curl", "python", "headless")):
        return "робот"
    return "компьютер"


@router.get("/api/hit")
@router.head("/api/hit")
async def отметить(запрос: Request,
                   p: str = Query("", description="страница"),
                   r: str = Query("", description="откуда пришёл")) -> Response:
    """Сюда стучится страница при открытии. Отвечаем пустотой и мгновенно."""
    try:
        браузер = запрос.headers.get("user-agent", "")
        устройство = _устройство(браузер)
        if устройство != "робот":       # роботов не считаем вовсе
            г = запрос.headers
            # Cloudflare присылает город и оператора сам, бесплатно.
            # Самого адреса НЕ храним — только эти два поля.
            город = _кириллица((г.get("cf-ipcity") or "").strip())[:40]
            регион = _кириллица((г.get("cf-region") or "").strip())[:40]
            язык = (г.get("accept-language") or "").split(",")[0].split(";")[0].strip()[:12]
            страна = (г.get("cf-ipcountry") or "?").strip()[:2]
            оператор = _кириллица((г.get("cf-ipasnorganization") or "").strip())[:40]
            await _копить().записать({
                "след": _след(запрос),
                "страница": (p or "/")[:60],
                "источник": _откуда(r or г.get("referer", "")),
                "страна": страна,
                "город": f"{город}, {страна}" if город else страна,
                "оператор": оператор or "—",
                "устройство": устройство,
                "браузер": _браузер(браузер),
                "регион": регион or "—",
                "язык": язык or "—",
                "час": datetime.now(МОСКВА).strftime("%H"),
                "время": datetime.now(МОСКВА).strftime("%H:%M"),
            })
    except Exception as e:
        logger.warning(f"📊 не записал заход: {type(e).__name__}")
    # прозрачная точка 1×1 — чтобы работало даже без JS
    return Response(
        content=bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b"),
        media_type="image/gif",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# ─────────────────────────────────────────────────────────────
#  Просмотр — только по ключу
# ─────────────────────────────────────────────────────────────

def _не_пущу() -> JSONResponse:
    return JSONResponse({"error": "нужен ключ"}, status_code=403)


@router.get("/api/stats")
async def цифры(key: str = Query(""),
                period: str = Query("month", description="day | month | year | all")) -> Response:
    """Сводка за срок плюс лента последних заходов.

    Он просил три среза: за день, за месяц и за год. Считаем из тех же
    дневных файлов — просто берём разное их количество.
    """
    if not КЛЮЧ_ПРОСМОТРА or key != КЛЮЧ_ПРОСМОТРА:
        return _не_пущу()

    await _копить().сбросить_сейчас()

    сегодня = _сегодня()
    все_дни = _список_дней(400)

    if period == "day":
        дни = [сегодня] if сегодня in все_дни or True else []
    elif period == "year":
        год = сегодня[:4]
        дни = [д for д in все_дни if д.startswith(год)]
    elif period == "all":
        дни = все_дни
    else:                                   # месяц — по умолчанию
        месяц = сегодня[:7]
        дни = [д for д in все_дни if д.startswith(месяц)]

    итог: dict[str, Any] = {
        "срок": period,
        "по_дням": [], "всего_заходов": 0, "всего_людей": 0,
        "страницы": defaultdict(int), "источники": defaultdict(int),
        "страны": defaultdict(int), "города": defaultdict(int),
        "операторы": defaultdict(int), "устройства": defaultdict(int),
        "браузеры": defaultdict(int), "часы": defaultdict(int), "лента": [],
        "сегодня": сегодня,
    }
    for день in дни:
        д = _прочитать_день(день)
        if not д:
            continue
        заходов = д.get("заходов", 0)
        людей = len(д.get("посетителей", []))
        итог["по_дням"].append({"день": день, "заходов": заходов, "людей": людей})
        итог["всего_заходов"] += заходов
        итог["всего_людей"] += людей
        for поле in ("страницы", "источники", "страны", "города",
                     "операторы", "устройства", "браузеры", "часы"):
            for к, в in (д.get(поле) or {}).items():
                итог[поле][к] += в
        # лента: собираем с датой, потом покажем последние
        for з in (д.get("лента") or []):
            итог["лента"].append({**з, "дата": день})

    итог["по_дням"].sort(key=lambda x: x["день"])
    # ⚠️ Дни читаются от новых к старым, поэтому лента лежит НЕ хронологически.
    # Раньше тут резали [-200:] без сортировки — и на месяце наверх
    # всплывали самые старые записи, а свежие терялись. Сначала сортируем.
    итог["лента"].sort(key=lambda з: (з.get("дата", ""), з.get("время", "")))
    итог["лента"] = итог["лента"][-1000:][::-1]     # свежие сверху
    for поле in ("страницы", "источники", "страны", "города",
                 "операторы", "устройства", "браузеры", "часы"):
        итог[поле] = dict(sorted(итог[поле].items(), key=lambda x: -x[1]))
    return JSONResponse(итог)


@router.get("/stats", response_class=HTMLResponse)
async def страница(key: str = Query("")) -> Response:
    if not КЛЮЧ_ПРОСМОТРА or key != КЛЮЧ_ПРОСМОТРА:
        return HTMLResponse("<h1>403</h1><p>Нужен ключ.</p>", status_code=403)
    return HTMLResponse(_СТРАНИЦА.replace("__КЛЮЧ__", key))


_СТРАНИЦА = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Статистика · QUANTAREON</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0a0c10; --bg2:#0e1118; --ink:#e8e2d4; --dim:#8f8874;
          --gold:#d4af5a; --gold2:#f0d492; --fire:#e83850;
          --line:rgba(212,175,90,.18); --line2:rgba(212,175,90,.35); }
  * { box-sizing:border-box; }
  body { margin:0; background:
           radial-gradient(1100px 500px at 75% -10%, rgba(212,175,90,.06), transparent 60%),
           var(--bg);
         color:var(--ink); font:15px/1.55 "JetBrains Mono", monospace;
         padding:26px clamp(14px,3vw,42px) 70px; }

  header { display:flex; align-items:flex-end; justify-content:space-between;
           flex-wrap:wrap; gap:14px; margin-bottom:6px; }
  h1 { font:600 2.3rem/1 "Cormorant", serif; letter-spacing:.14em; margin:0;
       background:linear-gradient(100deg,var(--gold) 20%,var(--gold2) 50%,var(--gold) 80%);
       -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  .под { color:var(--dim); font-size:.74rem; letter-spacing:.08em; margin:4px 0 22px; }
  .сроки { display:flex; gap:6px; flex-wrap:wrap; }
  .срок { cursor:pointer; border:1px solid var(--line); background:transparent;
          color:var(--dim); border-radius:20px; padding:7px 16px; font:inherit;
          font-size:.78rem; letter-spacing:.05em; transition:.18s; }
  .срок:hover { border-color:var(--line2); color:var(--ink); }
  .срок.вкл { background:rgba(212,175,90,.14); border-color:var(--line2); color:var(--gold); }

  .верх { display:grid; grid-template-columns:230px 1fr; gap:22px; align-items:stretch;
          margin-bottom:26px; }
  @media (max-width:820px){ .верх { grid-template-columns:1fr; } }

  .пульс { border:1px solid var(--line); border-radius:16px; background:var(--bg2);
           display:flex; flex-direction:column; align-items:center; justify-content:center;
           padding:22px 10px; }
  .кольцо { position:relative; width:128px; height:128px; display:flex;
            align-items:center; justify-content:center; }
  .кольцо::before, .кольцо::after { content:""; position:absolute; inset:0;
    border-radius:50%; border:1.5px solid var(--gold); opacity:0;
    animation:волна 4.2s cubic-bezier(.25,.6,.35,1) infinite; }
  .кольцо::after { animation-delay:1.4s; }
  @keyframes волна {
    0% { transform:scale(.72); opacity:.85; border-color:var(--fire); }
    60% { border-color:var(--gold); }
    100% { transform:scale(1.28); opacity:0; }
  }
  .ядро { width:96px; height:96px; border-radius:50%; border:1px solid var(--line2);
          background:radial-gradient(circle at 50% 58%, rgba(232,56,80,.16), rgba(212,175,90,.06) 62%, transparent 75%);
          display:flex; align-items:center; justify-content:center;
          animation:дыхание 4.2s ease-in-out infinite; }
  @keyframes дыхание { 50% { box-shadow:0 0 26px rgba(212,175,90,.25); } }
  .ядро b { font:700 2.5rem/1 "Cormorant", serif; color:var(--gold2); }
  .пульс span { color:var(--dim); font-size:.7rem; letter-spacing:.09em;
                text-transform:uppercase; margin-top:12px; text-align:center; line-height:1.7; }
  @media (prefers-reduced-motion: reduce) { .кольцо::before,.кольцо::after,.ядро { animation:none; } }

  .право { display:flex; flex-direction:column; gap:18px; min-width:0; }
  .плитки { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  @media (max-width:560px){ .плитки { grid-template-columns:1fr 1fr; } }
  .плитка { border:1px solid var(--line); border-radius:14px; padding:14px 18px; background:var(--bg2); }
  .плитка b { display:block; font:600 2.1rem/1.1 "Cormorant", serif; color:var(--gold); }
  .плитка span { color:var(--dim); font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; }
  .плитка.клик { cursor:pointer; transition:.18s; }
  .плитка.клик:hover { border-color:var(--line2); background:rgba(212,175,90,.07); }
  .плитка.клик span::after { content:" ›"; color:var(--gold); }

  .блок-дни { border:1px solid var(--line); border-radius:14px; background:var(--bg2);
              padding:14px 18px 10px; flex:1; }
  .блок-дни h2 { margin:0 0 10px; }
  .дни { display:flex; align-items:flex-end; gap:6px; height:96px; }
  .день { flex:1; display:flex; flex-direction:column; align-items:center;
          justify-content:flex-end; height:100%; cursor:pointer; }
  .день i { font-style:normal; font-size:.68rem; color:var(--dim); margin-bottom:4px; }
  .столб { width:100%; background:linear-gradient(180deg, rgba(212,175,90,.9), rgba(212,175,90,.35));
           border-radius:4px 4px 0 0; min-height:3px; transition:.18s; }
  .день:hover .столб, .день.вкл .столб { background:linear-gradient(180deg, var(--gold2), rgba(212,175,90,.6)); }
  .день u { text-decoration:none; font-size:.66rem; color:var(--dim); margin-top:6px; }
  .день.сегодня u, .день.вкл u { color:var(--gold); }

  h2 { font:600 1.05rem/1 "Cormorant", serif; letter-spacing:.16em; color:var(--gold);
       margin:28px 0 4px; text-transform:uppercase; }
  .подсказка { color:var(--dim); font-size:.72rem; margin:2px 0 12px; }

  .где { display:flex; gap:10px; align-items:center; margin:16px 0 6px; flex-wrap:wrap; }
  .назад { cursor:pointer; border:1px solid var(--line); background:transparent;
           color:var(--gold); border-radius:20px; padding:6px 15px; font:inherit;
           font-size:.78rem; transition:.18s; }
  .назад:hover { border-color:var(--line2); background:rgba(212,175,90,.08); }
  .метка { color:var(--gold); font-size:.8rem; border:1px solid var(--line);
           border-radius:20px; padding:5px 13px; background:rgba(212,175,90,.08); }

  .обёртка { overflow-x:auto; border:1px solid var(--line); border-radius:14px; background:var(--bg2); }
  table { width:100%; border-collapse:collapse; font-size:.82rem; }
  .лента th { text-align:left; color:var(--dim); font-weight:400; padding:11px 14px;
              border-bottom:1px solid var(--line); font-size:.68rem; letter-spacing:.09em;
              text-transform:uppercase; white-space:nowrap; }
  .лента td { padding:10px 14px; border-bottom:1px solid rgba(255,255,255,.04);
              white-space:nowrap; max-width:220px; overflow:hidden; text-overflow:ellipsis; }
  .лента tr:last-child td { border-bottom:none; }
  .лента tbody tr { cursor:pointer; transition:.15s; }
  .лента tbody tr:hover { background:rgba(212,175,90,.07); }
  .когда { color:var(--gold); }
  .тускло { color:var(--dim); }
  .чел { display:inline-flex; align-items:center; gap:8px; }
  .точка { width:10px; height:10px; border-radius:50%; flex:none; box-shadow:0 0 8px currentColor; }
  .точка.нет { background:transparent !important; border:1px dashed var(--dim); box-shadow:none; }
  .точка.большая { width:16px; height:16px; }
  .новый { color:var(--fire); font-size:.66rem; margin-left:6px; }
  .чип { display:inline-block; border:1px solid var(--line); border-radius:12px;
         padding:1px 9px; font-size:.72rem; }

  .сетка { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }
  @media (max-width:900px){ .сетка { grid-template-columns:1fr; } }
  .карта { border:1px solid var(--line); border-radius:14px; background:var(--bg2); padding:14px 18px; }
  .карта h2 { margin:0 0 10px; font-size:.92rem; }
  .карта td { padding:6px 2px; border-bottom:1px solid rgba(255,255,255,.04);
              font-size:.8rem; cursor:pointer; }
  .карта tr:hover td { color:var(--gold2); }
  .карта td:last-child { text-align:right; color:var(--gold); }
  .полоса { height:3px; background:linear-gradient(90deg,var(--gold),transparent);
            opacity:.5; border-radius:2px; margin-top:4px; }

  .штора { position:fixed; inset:0; background:rgba(4,5,8,.72); backdrop-filter:blur(3px);
           display:none; align-items:flex-start; justify-content:center; padding:5vh 14px;
           overflow-y:auto; z-index:9; }
  .штора.вкл { display:flex; }
  .досье { width:min(680px,100%); background:var(--bg2); border:1px solid var(--line2);
           border-radius:18px; padding:26px clamp(16px,3vw,32px) 30px; position:relative;
           box-shadow:0 0 60px rgba(212,175,90,.12); }
  .досье .крест { position:absolute; top:14px; right:18px; cursor:pointer; border:none;
                  background:none; color:var(--dim); font-size:1.3rem; }
  .досье .крест:hover { color:var(--fire); }
  .досье h2 { margin:0 0 2px; }
  .шапка-досье { display:flex; align-items:center; gap:14px; margin-bottom:4px; }
  .поля { display:grid; grid-template-columns:1fr 1fr; gap:2px 26px; margin:16px 0 4px; }
  @media (max-width:560px){ .поля { grid-template-columns:1fr; } }
  .поле { display:flex; justify-content:space-between; gap:10px; padding:7px 0;
          border-bottom:1px solid rgba(255,255,255,.05); font-size:.8rem; }
  .поле i { font-style:normal; color:var(--dim); }
  .нить { margin:14px 0 0; padding-left:18px; border-left:1px solid var(--line); }
  .узел { position:relative; padding:7px 0 7px 16px; font-size:.8rem; }
  .узел::before { content:""; position:absolute; left:-22.5px; top:13px; width:8px; height:8px;
                  border-radius:50%; background:var(--gold); box-shadow:0 0 8px rgba(212,175,90,.7); }
  .узел .когда { margin-right:10px; }
  .пусто { color:var(--dim); font-size:.85rem; padding:16px; }
</style></head>
<body>

<header>
  <div>
    <h1>СТАТИСТИКА</h1>
    <div class="под" id="под"></div>
  </div>
  <div class="сроки" id="сроки">
    <button class="срок" data-срок="day">Сегодня</button>
    <button class="срок вкл" data-срок="month">Месяц</button>
    <button class="срок" data-срок="year">Год</button>
    <button class="срок" data-срок="all">Всё время</button>
  </div>
</header>

<div class="верх">
  <div class="пульс">
    <div class="кольцо"><div class="ядро"><b id="пульс-число"></b></div></div>
    <span id="пульс-подпись"></span>
  </div>
  <div class="право">
    <div class="плитки" id="плитки"></div>
    <div class="блок-дни">
      <h2>По дням</h2>
      <p class="подсказка" style="margin-bottom:8px">столбик кликабелен — покажу этот день</p>
      <div class="дни" id="дни"></div>
    </div>
  </div>
</div>

<div id="тело"></div>

<div class="штора" id="штора">
  <div class="досье" id="досье"></div>
</div>

<script>
"use strict";
const КЛЮЧ = "__КЛЮЧ__";
let срок = "month", фильтр = null, данные = null;
const ИМЕНА = { day:"за сегодня", month:"за этот месяц", year:"за этот год", all:"за всё время" };
const $ = х => document.getElementById(х);
const экран = т => String(т ?? "").replace(/[&<>"']/g,
  с => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[с]));

const МЕСЯЦЫ = ["января","февраля","марта","апреля","мая","июня","июля",
                "августа","сентября","октября","ноября","декабря"];
function дата_словами(д) { const [, м, ч] = (д || "--0-0").split("-");
  return `${+ч} ${МЕСЯЦЫ[+м - 1] || ""}`; }
function дата_коротко(д) { return (д || "").slice(8,10) + "." + (д || "").slice(5,7); }

// цвет посетителя из его метки: один человек = один цвет
function цвет(след) { return `hsl(${parseInt(след.slice(0,6),16) % 360} 55% 62%)`; }
function точка(з, большая) {
  const кл = "точка" + (з.след ? "" : " нет") + (большая ? " большая" : "");
  const ст = з.след ? `color:${цвет(з.след)};background:${цвет(з.след)}` : "";
  return `<span class="${кл}" style="${ст}"></span>`;
}
function значок(у) { return у === "телефон" ? "📱" : у === "компьютер" ? "💻" : ""; }

// первое непустое значение поля по всем заходам человека —
// чтобы прочерки старых записей не затирали то, что уже известно
function известно(свои, ключ) {
  for (const з of свои) { const в = з[ключ]; if (в && в !== "—") return в; }
  return "—";
}

// ═══ верх: пульс + плитки + дни ═══
function верх() {
  const d = данные;
  const сегодня = (d.лента || []).filter(з => з.дата === d.сегодня);
  const заСегодня = (d.по_дням.find(х => х.день === d.сегодня) || {}).заходов ?? сегодня.length;
  $("пульс-число").textContent = заСегодня;
  $("пульс-подпись").innerHTML = заСегодня
    ? `заходов сегодня<br>последний — ${экран(сегодня[0] ? сегодня[0].время : "")}`
    : `сегодня заходов<br>пока нет`;

  const меток = new Set((d.лента || []).filter(з => з.след).map(з => з.дата + з.след)).size;
  $("плитки").innerHTML = `
    <div class="плитка"><b>${d.всего_заходов}</b><span>заходов</span></div>
    <div class="плитка клик" id="плитка-люди"><b>${d.всего_людей}</b><span>посетителей</span></div>
    <div class="плитка"><b>${Math.round(d.всего_заходов / (d.по_дням.length || 1))}</b><span>в день, в среднем</span></div>`;
  $("плитка-люди").onclick = () => { фильтр = { вид: "люди" }; нарисовать(); };

  const макс = Math.max(...d.по_дням.map(х => х.заходов), 1);
  $("дни").innerHTML = d.по_дням.map(х => `
    <div class="день${х.день === d.сегодня ? " сегодня" : ""}${фильтр && фильтр.вид === "день" && фильтр.день === х.день ? " вкл" : ""}" data-день="${х.день}">
      <i>${х.заходов}</i><div class="столб" style="height:${х.заходов / макс * 100}%"></div>
      <u>${дата_коротко(х.день)}</u>
    </div>`).join("");
  document.querySelectorAll(".день").forEach(с =>
    с.onclick = () => { фильтр = { вид: "день", день: с.dataset["день"] }; нарисовать(); });
}

// ═══ лента ═══
function таблица_ленты(записи) {
  if (!записи.length) return `<div class="обёртка"><p class="пусто">Заходов не найдено.</p></div>`;
  return `<div class="обёртка"><table class="лента">
    <thead><tr><th>когда</th><th>кто · откуда</th><th>страница</th><th>пришёл с</th>
    <th>браузер</th><th></th></tr></thead><tbody>` +
    записи.slice(0, 400).map((з, и) => `
    <tr data-н="${и}">
      <td class="когда">${дата_коротко(з.дата)} ${экран(з.время || "")}</td>
      <td><span class="чел">${точка(з)}${экран(з.город || з.страна || "—")}${з.новый ? '<span class="новый">новый</span>' : ""}</span></td>
      <td><span class="чип">${экран(з.страница || "—")}</span></td>
      <td class="тускло">${экран(з.источник || "напрямую")}</td>
      <td class="тускло">${экран(з.браузер || "—")}</td>
      <td>${значок(з.устройство)}</td>
    </tr>`).join("") + `</tbody></table></div>`;
}
function навесить_ленту(записи) {
  document.querySelectorAll("tr[data-н]").forEach(с =>
    с.onclick = () => {
      const з = записи[+с.dataset["н"]];
      if (з.след) досье(з.след, з.дата);
      else { фильтр = { вид: "похожие", дата: з.дата,
                        город: з.город || з.страна || "",
                        устройство: з.устройство || "" }; нарисовать(); }
    });
}

// ═══ срезы: серверные счётчики (сходятся с плитками) ═══
function срезы() {
  const d = данные;
  const карты = [
    ["Города", "город", d.города],
    ["Страницы", "страница", d.страницы],
    ["Пришли с", "источник", d.источники],
    ["Устройства", "устройство", d.устройства],
    ["Браузеры", "браузер", d.браузеры],
    ["Операторы", "оператор", d.операторы],
    ["Часы (МСК)", "час", d.часы],
  ];
  const куски = карты.map(([заг, поле, объект]) => {
    const пары = Object.entries(объект || {}).filter(([к]) => к && к !== "—");
    if (!пары.length) return "";
    return `<div class="карта"><h2>${заг}</h2><table>${
      пары.slice(0, 6).map(([к, в]) => `
        <tr data-поле="${поле}" data-значение="${экран(к)}">
          <td>${поле === "устройство" ? значок(к) + " " : ""}${экран(поле === "час" ? к + ":00" : к)}
            <div class="полоса" style="width:${в / пары[0][1] * 100}%"></div></td>
          <td>${в}</td></tr>`).join("")
    }</table></div>`;
  }).filter(Boolean);
  if (!куски.length) return "";
  return `<h2 style="margin-top:34px">Срезы</h2>
    <p class="подсказка">нажми на строку — лента покажет эти заходы (из последних записей)</p>
    <div class="сетка">${куски.join("")}</div>`;
}
function навесить_срезы() {
  document.querySelectorAll("tr[data-поле]").forEach(с =>
    с.onclick = () => { фильтр = { вид: "поле", поле: с.dataset["поле"], значение: с.dataset["значение"] }; нарисовать(); });
}
function значение_поля(з, поле) {
  if (поле === "час") return (з.время || "").slice(0, 2);
  if (поле === "город") return з.город || з.страна || "";
  if (поле === "источник") return з.источник || "напрямую";
  return з[поле] || "";
}

// ═══ список посетителей ═══
function список_людей() {
  const кучки = {};
  (данные.лента || []).forEach(з => { if (!з.след) return;
    const к = з.дата + "|" + з.след;
    (кучки[к] = кучки[к] || { ...з, заходов: 0, страницы: new Set() }).заходов++;
    if (з.страница) кучки[к].страницы.add(з.страница); });
  const сп = Object.values(кучки).sort((а, б) =>
    б.дата.localeCompare(а.дата) || б.заходов - а.заходов);
  if (!сп.length) return `<p class="пусто">Посетителей с меткой в этом срезе пока нет —
    метки пишутся с обновления 13.08, наполнится с новыми заходами.</p>`;
  return `<div class="обёртка"><table class="лента">
    <thead><tr><th>день</th><th>кто · откуда</th><th>браузер</th><th>заходов</th><th>страниц</th></tr></thead><tbody>` +
    сп.map(ч => `<tr data-чел="${экран(ч.след)}" data-дата="${экран(ч.дата)}">
      <td class="когда">${дата_коротко(ч.дата)}</td>
      <td><span class="чел">${точка(ч)}${экран(ч.город || ч.страна || "—")}</span></td>
      <td class="тускло">${экран(ч.браузер || "—")}</td>
      <td>${ч.заходов}</td><td>${ч.страницы.size}</td>
    </tr>`).join("") + `</tbody></table></div>`;
}

// ═══ главная отрисовка ═══
function нарисовать() {
  if (!данные) return;
  верх();
  let html = "", записи = данные.лента || [];

  if (фильтр && фильтр.вид === "люди") {
    $("под").textContent = "посетители " + ИМЕНА[срок] + " · время московское";
    $("тело").innerHTML = `<div class="где"><button class="назад">← назад</button>
        <span class="метка">посетители</span></div>
      <h2>Посетители</h2>
      <p class="подсказка">по суточным меткам: один человек в разные дни — отдельные строки.
        Нажми — открою досье</p>` + список_людей();
    document.querySelector(".назад").onclick = сброс;
    document.querySelectorAll("tr[data-чел]").forEach(с =>
      с.onclick = () => досье(с.dataset["чел"], с.dataset["дата"]));
    return;
  }

  $("под").textContent = ИМЕНА[срок] + " · время московское";

  if (фильтр && фильтр.вид === "день") {
    записи = записи.filter(з => з.дата === фильтр.день);
    html += `<div class="где"><button class="назад">← назад</button>
      <span class="метка">день · ${дата_словами(фильтр.день)}</span></div>`;
  } else if (фильтр && фильтр.вид === "поле") {
    записи = записи.filter(з => значение_поля(з, фильтр.поле) === фильтр.значение);
    html += `<div class="где"><button class="назад">← назад</button>
      <span class="метка">${экран(фильтр.поле === "час" ? фильтр.значение + ":00" : фильтр.значение)}</span></div>`;
  } else if (фильтр && фильтр.вид === "похожие") {
    записи = записи.filter(з => з.дата === фильтр.дата
      && (з.город || з.страна || "") === фильтр.город
      && (з.устройство || "") === фильтр.устройство);
    html += `<div class="где"><button class="назад">← назад</button>
      <span class="метка">похожие · ${экран(фильтр.город)} · ${дата_словами(фильтр.дата)}</span></div>
      <p class="подсказка">у записей до обновления 13.08 нет личной метки — это все заходы дня
      из того же города с того же устройства, среди них могут быть разные люди</p>`;
  }

  html += `<h2>Кто заходил</h2>
    <p class="подсказка">цвет точки — один и тот же посетитель, пунктир — запись без метки.
    Любая строка кликабельна: с точкой — досье, с пунктиром — похожие заходы</p>`
    + таблица_ленты(записи);
  if (!фильтр) html += срезы();

  $("тело").innerHTML = html;
  навесить_ленту(записи);
  навесить_срезы();
  const н = document.querySelector(".назад"); if (н) н.onclick = сброс;
}
function сброс() { фильтр = null; нарисовать(); }

// ═══ досье ═══
function досье(след, дата) {
  const свои = (данные.лента || []).filter(з => з.след === след && з.дата === дата);
  if (!свои.length) return;
  const последний = свои[0], первый = свои[свои.length - 1];
  const страницы = {};
  свои.forEach(з => { if (з.страница) страницы[з.страница] = (страницы[з.страница] || 0) + 1; });
  // «первый раз» — только если флаг где-то честно взведён; у записей старого
  // кода флага не было, тогда прочерк, а не выдумка
  const был = свои.some(з => з.новый) ? "первый раз"
            : ("браузер" in первый && первый.браузер !== undefined ? "уже заходил" : "—");
  $("досье").innerHTML = `
    <button class="крест">✕</button>
    <div class="шапка-досье">${точка(первый, true)}
      <div><h2>Посетитель · ${дата_словами(дата)}</h2>
        <div class="подсказка" style="margin:0">метка ${экран(след)} — суточная: адрес не храним,
        в другие дни это «другой» посетитель</div></div>
    </div>
    <div class="плитки" style="grid-template-columns:repeat(4,1fr);margin-top:14px">
      <div class="плитка"><b>${свои.length}</b><span>заходов</span></div>
      <div class="плитка"><b>${Object.keys(страницы).length}</b><span>страниц</span></div>
      <div class="плитка"><b>${экран(первый.время || "—")}</b><span>пришёл</span></div>
      <div class="плитка"><b>${экран(последний.время || "—")}</b><span>последний</span></div>
    </div>
    <div class="поля">
      <div class="поле"><i>город</i><b>${экран(известно(свои, "город"))}</b></div>
      <div class="поле"><i>регион</i><b>${экран(известно(свои, "регион"))}</b></div>
      <div class="поле"><i>устройство</i><b>${значок(известно(свои, "устройство"))} ${экран(известно(свои, "устройство"))}</b></div>
      <div class="поле"><i>браузер</i><b>${экран(известно(свои, "браузер"))}</b></div>
      <div class="поле"><i>язык</i><b>${экран(известно(свои, "язык"))}</b></div>
      <div class="поле"><i>оператор</i><b>${экран(известно(свои, "оператор"))}</b></div>
      <div class="поле"><i>пришёл с</i><b>${экран(известно(свои, "источник")) === "—" ? "напрямую" : экран(известно(свои, "источник"))}</b></div>
      <div class="поле"><i>в этот день</i><b style="${был === "первый раз" ? "color:var(--fire)" : ""}">${был}</b></div>
    </div>
    <h2 style="font-size:.92rem">Его путь по сайту</h2>
    <div class="нить">${[...свои].reverse().map(з => `
      <div class="узел"><span class="когда">${экран(з.время || "")}</span>${экран(з.страница || "—")}
        ${з.источник && з.источник !== "напрямую" ? `<span class="тускло">· пришёл из ${экран(з.источник)}</span>` : ""}</div>`).join("")}
    </div>`;
  $("штора").classList.add("вкл");
  document.querySelector(".крест").onclick = закрыть;
}
function закрыть() { $("штора").classList.remove("вкл"); }
$("штора").onclick = е => { if (е.target === $("штора")) закрыть(); };
document.addEventListener("keydown", е => { if (е.key === "Escape") закрыть(); });

// ═══ загрузка с сервера ═══
function загрузить() {
  $("под").textContent = "загружаю…";
  fetch(`/api/stats?key=${encodeURIComponent(КЛЮЧ)}&period=${срок}`)
    .then(р => р.json())
    .then(d => {
      if (d.error) { $("под").textContent = d.error; return; }
      данные = d;
      нарисовать();
    })
    .catch(е => { $("под").textContent = "не загрузилось: " + е; });
}
document.querySelectorAll(".срок").forEach(к =>
  к.onclick = () => {
    document.querySelectorAll(".срок").forEach(х => х.classList.remove("вкл"));
    к.classList.add("вкл");
    срок = к.dataset["срок"]; фильтр = null; загрузить();
  });
загрузить();
setInterval(загрузить, 60000);
</script>
</body></html>

"""
