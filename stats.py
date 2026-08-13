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
            if след and след not in люди:
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
                "новый": что.get("новый", False),
            })
            if len(лента) > ЛЕНТА_ДЛИНА:
                del лента[: len(лента) - ЛЕНТА_ДЛИНА]

            for поле, ключ in (("страницы", "страница"), ("источники", "источник"),
                               ("страны", "страна"), ("города", "город"),
                               ("операторы", "оператор"), ("устройства", "устройство"),
                               ("часы", "час")):
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
            город = (г.get("cf-ipcity") or "").strip()[:40]
            страна = (г.get("cf-ipcountry") or "?").strip()[:2]
            оператор = (г.get("cf-ipasnorganization") or "").strip()[:40]
            await _копить().записать({
                "след": _след(запрос),
                "страница": (p or "/")[:60],
                "источник": _откуда(r or г.get("referer", "")),
                "страна": страна,
                "город": f"{город}, {страна}" if город else страна,
                "оператор": оператор or "—",
                "устройство": устройство,
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
        "часы": defaultdict(int), "лента": [],
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
                     "операторы", "устройства", "часы"):
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
                 "операторы", "устройства", "часы"):
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
<meta name="robots" content="noindex, nofollow">
<title>Статистика · QUANTAREON</title>
<style>
  :root { --bg:#0a0c10; --ink:#e8e2d4; --dim:#9a927f; --gold:#d4af5a;
          --line:rgba(212,175,90,.2); --fire:#c0562e; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font: 15px/1.55 system-ui, -apple-system, sans-serif; padding: 22px 16px 60px; }
  h1 { font-size:1.4rem; font-weight:500; color:var(--gold); margin:0 0 4px;
       letter-spacing:.1em; }
  .под { color:var(--dim); font-size:.82rem; margin-bottom:20px; }

  .сроки { display:flex; gap:8px; margin-bottom:22px; flex-wrap:wrap; }
  .срок { cursor:pointer; border:1px solid var(--line); background:transparent;
          color:var(--dim); border-radius:9px; padding:7px 15px; font:inherit;
          font-size:.85rem; transition:.15s; }
  .срок:hover { border-color:rgba(212,175,90,.45); color:var(--ink); }
  .срок.вкл { background:rgba(212,175,90,.16); border-color:rgba(212,175,90,.5);
              color:var(--gold); }

  .плитки { display:flex; flex-wrap:wrap; gap:11px; margin-bottom:24px; }
  .плитка { flex:1 1 130px; border:1px solid var(--line); border-radius:12px;
            padding:13px 15px; background:rgba(255,255,255,.03); }
  .плитка b { display:block; font-size:1.8rem; font-weight:600; color:var(--gold);
              font-variant-numeric:tabular-nums; }
  .плитка span { color:var(--dim); font-size:.78rem; }

  h2 { font-size:.88rem; font-weight:500; color:var(--gold); margin:24px 0 9px;
       letter-spacing:.06em; }
  table { width:100%; border-collapse:collapse; font-size:.9rem; }
  td { padding:6px 4px; border-bottom:1px solid rgba(255,255,255,.05);
       vertical-align:top; }
  td:last-child { text-align:right; color:var(--gold); font-variant-numeric:tabular-nums;
                  white-space:nowrap; }
  .полоса { height:3px; background:var(--gold); opacity:.32; border-radius:2px;
            margin-top:4px; }

  .дни { display:flex; align-items:flex-end; gap:2px; height:110px; margin-top:6px; }
  .день { flex:1; background:var(--gold); opacity:.45; border-radius:2px 2px 0 0;
          min-height:2px; position:relative; }
  .день:hover { opacity:1; }
  .день em { position:absolute; bottom:100%; left:50%; transform:translateX(-50%);
             font-style:normal; font-size:.7rem; color:var(--dim); white-space:nowrap;
             opacity:0; pointer-events:none; }
  .день:hover em { opacity:1; }

  /* лента заходов */
  .лента { width:100%; border-collapse:collapse; font-size:.82rem; }
  .лента th { text-align:left; color:var(--dim); font-weight:400; padding:6px 8px 6px 0;
              border-bottom:1px solid var(--line); white-space:nowrap; font-size:.76rem;
              letter-spacing:.04em; }
  .лента td { padding:7px 8px 7px 0; border-bottom:1px solid rgba(255,255,255,.05);
              text-align:left; color:var(--ink); white-space:nowrap;
              overflow:hidden; text-overflow:ellipsis; max-width:190px; }
  .лента td.когда { color:var(--gold); font-variant-numeric:tabular-nums; }
  .лента td.тускло { color:var(--dim); }
  .новый { color:var(--fire); font-size:.7rem; margin-left:5px; }
  .обёртка { overflow-x:auto; -webkit-overflow-scrolling:touch; }

  .клик { cursor:pointer; }
  .клик:hover td { background:rgba(212,175,90,.07); }
  .подсказка { color:var(--dim); font-size:.74rem; margin:2px 0 8px; }
  .назад { cursor:pointer; border:1px solid var(--line); background:transparent;
           color:var(--gold); border-radius:9px; padding:6px 14px; font:inherit;
           font-size:.82rem; margin:14px 0 4px; }
  .назад:hover { border-color:rgba(212,175,90,.5); }
  .день { cursor:pointer; }
  .день.вкл { opacity:1; }

  .пусто { color:var(--dim); font-size:.85rem; }
  @media (max-width:560px){ .плитка{flex:1 1 45%} body{padding:16px 12px 50px} }
</style></head>
<body>
  <h1>СТАТИСТИКА</h1>
  <div class="под" id="под">загружаю…</div>

  <div class="сроки">
    <button class="срок" data-срок="day">Сегодня</button>
    <button class="срок вкл" data-срок="month">Этот месяц</button>
    <button class="срок" data-срок="year">Этот год</button>
    <button class="срок" data-срок="all">За всё время</button>
  </div>

  <div class="плитки" id="плитки"></div>
  <div id="тело"></div>

<script>
const КЛЮЧ = "__КЛЮЧ__";
let срок = "month";
let данные = null;   // последний ответ сервера
let фильтр = null;   // null · {след, дата} — один посетитель · {день} — один день

const ИМЕНА = { day:"за сегодня", month:"за этот месяц",
                year:"за этот год", all:"за всё время" };

// Всё, что пришло снаружи (страница, город, источник), перед вставкой в
// разметку экранируем — иначе хитрый заход мог бы подсунуть скрипт
// прямо в эту админскую страницу.
function экран(т) { return String(т ?? "").replace(/[&<>"']/g,
  с => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[с])); }

function таблица(заголовок, объект, всего) {
  const пары = Object.entries(объект || {}).filter(([к]) => к && к !== "—");
  if (!пары.length) return "";
  const строки = пары.slice(0, 12).map(([к, в]) => {
    const доля = всего ? Math.round(в / всего * 100) : 0;
    return `<tr><td>${экран(к)}<div class="полоса" style="width:${доля}%"></div></td><td>${в}</td></tr>`;
  }).join("");
  return `<h2>${заголовок}</h2><table>${строки}</table>`;
}

function шапка_ленты() {
  return `<tr><th>когда</th><th>откуда</th><th>оператор</th>
          <th>страница</th><th>пришёл с</th><th>устройство</th></tr>`;
}

function строки_ленты(записи) {
  return записи.map(з => {
    const клик = з.след ? ` class="клик" data-след="${экран(з.след)}" data-дата="${экран(з.дата || "")}"` : "";
    return `
    <tr${клик}>
      <td class="когда">${экран((з.дата || "").slice(5))} ${экран(з.время || "")}</td>
      <td>${экран(з.город || з.страна || "—")}${з.новый ? '<span class="новый">новый</span>' : ""}</td>
      <td class="тускло">${экран(з.оператор || "—")}</td>
      <td>${экран(з.страница || "—")}</td>
      <td class="тускло">${экран(з.источник || "напрямую")}</td>
      <td class="тускло">${экран(з.устройство || "")}</td>
    </tr>`;
  }).join("");
}

function лента(записи) {
  if (!записи || !записи.length) return "";
  return `<h2>КТО ЗАХОДИЛ</h2>
    <p class="подсказка">нажми на строку — покажу все заходы этого посетителя</p>
    <div class="обёртка"><table class="лента">${шапка_ленты()}${строки_ленты(записи.slice(0, 400))}</table></div>`;
}

function посетитель(след, дата) {
  // лента приходит свежими сверху → в отфильтрованном первый = самый свежий
  const свои = (данные.лента || []).filter(з => з.след === след && з.дата === дата);
  if (!свои.length) return `<button class="назад" onclick="сброс()">← все заходы</button>
    <p class="пусто">По этому посетителю записей нет.</p>`;
  const последний = свои[0], первый = свои[свои.length - 1];
  const страницы = {};
  свои.forEach(з => { if (з.страница) страницы[з.страница] = (страницы[з.страница] || 0) + 1; });
  return `
    <button class="назад" onclick="сброс()">← все заходы</button>
    <h2>ПОСЕТИТЕЛЬ ${экран(след)} · ${экран(дата.slice(5))}</h2>
    <div class="плитки">
      <div class="плитка"><b>${свои.length}</b><span>заходов</span></div>
      <div class="плитка"><b>${Object.keys(страницы).length}</b><span>страниц</span></div>
      <div class="плитка"><b>${экран(первый.время || "—")}</b><span>первый заход</span></div>
      <div class="плитка"><b>${экран(последний.время || "—")}</b><span>последний заход</span></div>
    </div>
    <table>
      <tr><td>откуда</td><td>${экран(первый.город || первый.страна || "—")}</td></tr>
      <tr><td>устройство</td><td>${экран(первый.устройство || "—")}</td></tr>
      <tr><td>оператор</td><td>${экран(первый.оператор || "—")}</td></tr>
      <tr><td>пришёл с</td><td>${экран(первый.источник || "напрямую")}</td></tr>
    </table>
    ${таблица("ЕГО СТРАНИЦЫ", страницы, свои.length)}
    <h2>ЕГО ЗАХОДЫ</h2>
    <div class="обёртка"><table class="лента">${шапка_ленты()}${строки_ленты(свои)}</table></div>`;
}

function нарисовать() {
  const d = данные;
  if (!d) return;
  document.getElementById("под").textContent = ИМЕНА[срок] + " · время московское";

  const дней = d.по_дням.length || 1;
  document.getElementById("плитки").innerHTML = `
    <div class="плитка"><b>${d.всего_заходов}</b><span>заходов</span></div>
    <div class="плитка"><b>${d.всего_людей}</b><span>посетителей</span></div>
    <div class="плитка"><b>${Math.round(d.всего_заходов / дней)}</b><span>в среднем за день</span></div>
    <div class="плитка"><b>${d.по_дням.length}</b><span>дней с заходами</span></div>`;

  // режим «один посетитель»
  if (фильтр && фильтр.след) {
    document.getElementById("тело").innerHTML = посетитель(фильтр.след, фильтр.дата);
    навесить();
    return;
  }

  let html = "";
  if (d.по_дням.length > 1) {
    const макс = Math.max(...d.по_дням.map(x => x.заходов), 1);
    html += `<h2>ПО ДНЯМ</h2><p class="подсказка">нажми на столбик — покажу только этот день</p><div class="дни">` + d.по_дням.map(x =>
      `<div class="день${фильтр && фильтр.день === x.день ? " вкл" : ""}" data-день="${x.день}" style="height:${Math.max(2, x.заходов / макс * 100)}%">
         <em>${x.день.slice(5)} · ${x.заходов}</em></div>`).join("") + `</div>`;
  }

  let записи = d.лента || [];
  if (фильтр && фильтр.день) {
    записи = записи.filter(з => з.дата === фильтр.день);
    html += `<button class="назад" onclick="сброс()">← весь срок</button>`;
    html += лента(записи);
  } else {
    html += лента(записи);
    html += таблица("ГОРОДА", d.города, d.всего_заходов);
    html += таблица("СТРАНИЦЫ", d.страницы, d.всего_заходов);
    html += таблица("ОТКУДА ПРИШЛИ", d.источники, d.всего_заходов);
    html += таблица("ОПЕРАТОРЫ", d.операторы, d.всего_заходов);
    html += таблица("УСТРОЙСТВА", d.устройства, d.всего_заходов);
    html += таблица("ЧАСЫ", d.часы, d.всего_заходов);
  }
  document.getElementById("тело").innerHTML = html ||
    `<p class="пусто">Пока никто не заходил.</p>`;
  навесить();
}

function навесить() {
  document.querySelectorAll("tr.клик").forEach(с => {
    с.addEventListener("click", () => {
      фильтр = { след: с.dataset["след"], дата: с.dataset["дата"] };
      нарисовать();
    });
  });
  document.querySelectorAll(".день[data-день]").forEach(с => {
    с.addEventListener("click", () => {
      фильтр = { день: с.dataset["день"] };
      нарисовать();
    });
  });
}

function сброс() { фильтр = null; нарисовать(); }

function загрузить() {
  document.getElementById("под").textContent = "загружаю…";
  fetch(`/api/stats?key=${encodeURIComponent(КЛЮЧ)}&period=${срок}`)
    .then(r => r.json())
    .then(d => {
      if (d.error) { document.getElementById("под").textContent = d.error; return; }
      данные = d;
      нарисовать();
    })
    .catch(e => { document.getElementById("под").textContent = "не загрузилось: " + e; });
}

document.querySelectorAll(".срок").forEach(к => {
  к.addEventListener("click", () => {
    document.querySelectorAll(".срок").forEach(x => x.classList.remove("вкл"));
    к.classList.add("вкл");
    срок = к.dataset["срок"];
    фильтр = null;               // смена среза сбрасывает фильтры
    загрузить();
  });
});

загрузить();
setInterval(загрузить, 60000);   // сам обновляется раз в минуту
</script>
</body></html>
"""
