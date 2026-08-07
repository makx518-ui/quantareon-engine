"""
QUANTARION — Web Tools v2.0 MAX
================================
Максимальное покрытие сбора информации из сети.

АРХИТЕКТУРА (6 слоёв):

┌──────────────────────────────────────────────────┐
│  СЛОЙ 1: ПОИСК (кто ищет)                       │
│  ├─ Tavily       — AI-поиск #1 (основной)       │
│  ├─ Serper       — Google SERP (быстрый, точный) │
│  └─ DuckDuckGo   — бесплатный fallback           │
├──────────────────────────────────────────────────┤
│  СЛОЙ 2: ИЗВЛЕЧЕНИЕ КОНТЕНТА                     │
│  └─ Jina Reader  — любой URL → чистый markdown   │
├──────────────────────────────────────────────────┤
│  СЛОЙ 3: СПЕЦИАЛИЗИРОВАННЫЕ                      │
│  ├─ NewsData.io  — структурированные новости     │  ← уже есть в server.py
│  ├─ Finnhub      — котировки акций               │  ← уже есть в server.py
│  └─ Open-Meteo   — погода                        │  ← уже есть в server.py
├──────────────────────────────────────────────────┤
│  СЛОЙ 4: ВРЕМЯ                                   │
│  └─ Python datetime (без API)                    │  ← уже есть в server.py
├──────────────────────────────────────────────────┤
│  СЛОЙ 5: УМНЫЙ РОУТИНГ                           │
│  ├─ smart_search()  — авто fallback              │
│  ├─ smart_news()    — новости с fallback         │
│  └─ deep_research() — глубокий ресёрч            │
├──────────────────────────────────────────────────┤
│  СЛОЙ 6: ФОРМАТИРОВАНИЕ                          │
│  └─ format_for_prompt() — готовый текст для LLM  │
└──────────────────────────────────────────────────┘

ПОКРЫТИЕ:
✅ Политика, экономика, наука, технологии, спорт, здоровье
✅ Мировые новости на 80+ языках (NewsData.io + DDG News)
✅ Финансы: акции, крипто, ставки (Finnhub + Tavily)
✅ Погода: глобально (Open-Meteo + Tavily)
✅ Любой вопрос: Tavily → Serper → DuckDuckGo
✅ Глубокое чтение: Jina Reader (URL → полный текст)
✅ Deep Research: поиск + чтение топ-страниц

СТОИМОСТЬ:
  Tavily:     $0 (1000 кредитов/мес) → $30/мес (4000 кредитов)
  Serper:     $0 (2500 запросов)     → $50 (50k запросов разово)
  Jina:       $0 (10M токенов)       → $10-20 (доп. токены)
  DuckDuckGo: $0 (бесплатно навсегда)
  NewsData:   $0 (200 req/день)      → уже в server.py
  Finnhub:    $0 (60 req/мин)        → уже в server.py
  ─────────────────────────────────────────────
  ИТОГО:      $0-100/мес покрывает ВСЁ

Зависимости: pip install aiohttp ddgs
ENV: TAVILY_API_KEY, SERPER_API_KEY (опц.), JINA_API_KEY (опц.)
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import aiohttp

logger = logging.getLogger("quantarion.web_tools")

# ============================================================
# CONFIG — ключи читаются лениво через функции,
# чтобы load_dotenv() в server.py гарантированно отработал до нас
# ============================================================

# ═══════════════════════════════════════════════════════
#  КЛЮЧИ. Репозиторий движка ЗАКРЫТЫЙ (Private на GitHub),
#  поэтому держим их прямо здесь — не надо ничего заводить
#  в панели Render. Переменная окружения, если задана,
#  всё равно старше: так ключ можно сменить, не трогая код.
#  ⚠️ ЕСЛИ РЕПОЗИТОРИЙ КОГДА-НИБУДЬ ОТКРОЮТ — ключи убрать
#  отсюда немедленно и перенести в переменные.
# ═══════════════════════════════════════════════════════
_ЗАПАСНЫЕ_КЛЮЧИ = {
    "TAVILY_API_KEY":   "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",
    "SERPER_API_KEY":   "7aab1011802f0ea6f010f9dca4edbdaad79e5dfa",
    "NEWSDATA_API_KEY": "pub_1607a041d81b407d9c70d63f8fa90203",
    # JINA не нужен: без ключа читает страницы нормально
}


def _ключ(имя: str) -> str:
    return os.getenv(имя, "") or _ЗАПАСНЫЕ_КЛЮЧИ.get(имя, "")


def _get_tavily_key() -> str:
    return _ключ("TAVILY_API_KEY")

def _get_serper_key() -> str:
    return _ключ("SERPER_API_KEY")

def _get_jina_key() -> str:
    return _ключ("JINA_API_KEY")

REQUEST_TIMEOUT = 12  # секунд — быстро, бот не тормозит


# ============================================================
# СЛОЙ 1: ПОИСК
# ============================================================

# --- 1A. TAVILY — AI-оптимизированный поиск ---

async def tavily_search(
    query: str,
    max_results: int = 3,
    topic: str = "general",
    include_answer: bool = True,
    search_depth: str = "basic",
    time_range: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tavily — лучший AI-поиск. Возвращает ранжированные результаты + AI-ответ.
    
    1000 бесплатных кредитов/мес. Basic = 1 кредит, Advanced = 2.
    topic: "general" | "news" | "finance"
    time_range: "day" | "week" | "month" | "year" | None
    """
    if not _get_tavily_key():
        return _err("tavily", "TAVILY_API_KEY не установлен")
    
    try:
        payload = {
            "api_key": _get_tavily_key(),
            "query": query[:400],
            "max_results": min(max_results, 20),
            "search_depth": search_depth,
            "topic": topic,
            "include_answer": include_answer,
        }
        if time_range:
            payload["time_range"] = time_range
        # поиск ТОЛЬКО по названным сайтам («найди на Ленте», «поищи на Хабре»)
        if include_domains:
            payload["include_domains"] = include_domains[:5]
        # страна помогает отвечать на языке спрашивающего, а не по-английски
        if country:
            payload["country"] = country
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/search",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"❌ Tavily {resp.status}: {text[:150]}")
                    return _err("tavily", f"HTTP {resp.status}")
                
                data = await resp.json()
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", ""),
                        "score": r.get("score", 0),
                    }
                    for r in data.get("results", [])
                ]
                
                logger.info(f"✅ Tavily: {len(results)} results for '{query[:50]}'")
                return _ok("tavily", results, answer=data.get("answer"))
    
    except asyncio.TimeoutError:
        logger.warning(f"❌ Tavily timeout: '{query[:50]}'")
        return _err("tavily", "Timeout")
    except Exception as e:
        logger.warning(f"❌ Tavily error: {e}")
        return _err("tavily", str(e))


# --- 1B. SERPER — Google SERP (быстрый, дешёвый) ---

async def serper_search(
    query: str,
    max_results: int = 5,
    search_type: str = "search",
    gl: str = "ru",
    hl: str = "ru",
) -> Dict[str, Any]:
    """
    Serper.dev — прямой доступ к Google SERP. 1-2 сек, $1/1000 запросов.
    
    Бесплатно 2500 запросов при регистрации.
    search_type: "search" | "news" | "images"
    gl/hl: страна и язык результатов
    """
    if not _get_serper_key():
        return _err("serper", "SERPER_API_KEY не установлен")
    
    try:
        payload = {
            "q": query[:400],
            "num": min(max_results, 10),
            "gl": gl,
            "hl": hl,
        }
        
        url = f"https://google.serper.dev/{search_type}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={
                    "X-API-KEY": _get_serper_key(),
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"❌ Serper {resp.status}: {text[:150]}")
                    return _err("serper", f"HTTP {resp.status}")
                
                data = await resp.json()
                
                # Serper возвращает разные форматы для search/news
                raw_results = data.get("organic", []) or data.get("news", [])
                
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("link", ""),
                        "content": r.get("snippet", ""),
                        "score": r.get("position"),
                    }
                    for r in raw_results[:max_results]
                ]
                
                # Knowledge Graph (если есть — очень ценная инфо)
                answer = None
                kg = data.get("knowledgeGraph", {})
                if kg:
                    answer = f"{kg.get('title', '')}: {kg.get('description', '')}"
                
                # Answer Box
                ab = data.get("answerBox", {})
                if ab and ab.get("answer"):
                    answer = ab["answer"]
                elif ab and ab.get("snippet"):
                    answer = ab["snippet"]
                
                logger.info(f"✅ Serper: {len(results)} results for '{query[:50]}'")
                return _ok("serper", results, answer=answer)
    
    except asyncio.TimeoutError:
        logger.warning(f"❌ Serper timeout: '{query[:50]}'")
        return _err("serper", "Timeout")
    except Exception as e:
        logger.warning(f"❌ Serper error: {e}")
        return _err("serper", str(e))


# --- 1C. DUCKDUCKGO — бесплатный fallback ---

async def ddg_search(
    query: str,
    max_results: int = 5,
    region: str = "ru-ru",
) -> Dict[str, Any]:
    """DuckDuckGo — бесплатно, без ключа. Третий рубеж, если легли Tavily и Serper.

    ⚠️ Библиотека переименована: duckduckgo_search → ddgs. Старая ещё
    отвечает, но выдаёт мусор (на вопрос о курсе валют возвращала форумы
    про видеокарты), поэтому берём новую, а старую держим как запасную.
    Обе синхронные — крутим в отдельном потоке, чтобы не морозить сервер.
    """
    def _синхронно():
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS   # старое имя
        with DDGS() as d:
            return list(d.text(query, region=region, max_results=max_results))

    try:
        raw = await asyncio.to_thread(_синхронно)
        results = [
            {"title": r.get("title", ""), "url": r.get("href", ""),
             "content": r.get("body", ""), "score": None}
            for r in raw
        ]
        logger.info(f"✅ DDG: {len(results)} for '{query[:50]}'")
        return _ok("duckduckgo", results)
    except ImportError:
        return _err("duckduckgo", "pip install ddgs")
    except Exception as e:
        logger.warning(f"❌ DDG error: {e}")
        return _err("duckduckgo", str(e))


async def ddg_news(
    query: str,
    max_results: int = 5,
    region: str = "wt-wt",
) -> Dict[str, Any]:
    """DuckDuckGo News — запасной новостной источник.

    ⚠️ ПОЧЕМУ РАНЬШЕ НЕ РАБОТАЛ (найдено 07.08): код определял новую
    библиотеку `ddgs`, но вызывал класс `AsyncDDGS` из старой
    `duckduckgo_search`, которой в окружении нет. Итог — ошибка на каждом
    вызове, и очередь запасных источников на нём обрывалась.
    Теперь для каждой библиотеки зовём её собственный класс, а
    блокирующий вызов уводим в отдельный поток, чтобы не тормозить голос.
    """
    def _собрать(raw) -> list:
        return [
            {"title": r.get("title", ""), "url": r.get("url", "") or r.get("href", ""),
             "content": r.get("body", "") or r.get("excerpt", ""), "score": None,
             "date": r.get("date"), "source_name": r.get("source")}
            for r in raw
        ]

    # 1) новая библиотека ddgs — синхронная, уводим в поток
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

    if DDGS is not None:
        try:
            def _искать():
                with DDGS() as d:
                    return list(d.news(query, max_results=max_results, region=region))
            raw = await asyncio.to_thread(_искать)
            results = _собрать(raw)
            logger.info(f"✅ DDG News: {len(results)} for '{query[:50]}'")
            return _ok("duckduckgo_news", results)
        except Exception as e:
            logger.warning(f"DDG News (ddgs): {type(e).__name__}: {e}")

    # 2) старая библиотека duckduckgo_search — асинхронная
    try:
        from duckduckgo_search import AsyncDDGS
        raw = await AsyncDDGS().news(query, max_results=max_results, region=region)
        results = _собрать(raw)
        logger.info(f"✅ DDG News (старая библиотека): {len(results)}")
        return _ok("duckduckgo_news", results)
    except ImportError:
        return _err("duckduckgo_news", "нет ни ddgs, ни duckduckgo_search")
    except Exception as e:
        return _err("duckduckgo_news", f"{type(e).__name__}: {e}")


async def jina_read(url: str) -> Dict[str, Any]:
    """
    Jina Reader — зайти на любой URL, вытащить чистый markdown.
    
    Работает через headless browser (рендерит JS, SPA).
    Без ключа: лимит по rate. С ключом: 10M токенов бесплатно.
    """
    try:
        headers = {
            "Accept": "application/json",
            "X-Return-Format": "markdown",
            "X-Retain-Images": "none",
        }
        if _get_jina_key():
            headers["Authorization"] = f"Bearer {_get_jina_key()}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://r.jina.ai/{url}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return {"success": False, "title": "", "content": "", "url": url, "error": f"HTTP {resp.status}"}
                
                data = await resp.json()
                doc = data.get("data", {})
                logger.info(f"✅ Jina: {url[:60]}")
                return {"success": True, "title": doc.get("title", ""),
                        "content": doc.get("content", ""), "url": doc.get("url", url), "error": None}
    
    except asyncio.TimeoutError:
        return {"success": False, "title": "", "content": "", "url": url, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "title": "", "content": "", "url": url, "error": str(e)}


# ============================================================
# СЛОЙ 5: УМНЫЙ РОУТИНГ
# ============================================================

async def smart_search(
    query: str,
    max_results: int = 3,
    topic: str = "general",
    deep_read: bool = False,
) -> Dict[str, Any]:
    """
    🧠 Умный поиск — 3 уровня fallback:
    
    Tavily (лучшее качество) → Serper (Google SERP) → DuckDuckGo (бесплатно)
    
    Если deep_read=True — дополнительно извлекает полный контент
    из топ-3 страниц через Jina Reader.
    """
    result = None
    
    # 1. Tavily
    if _get_tavily_key():
        result = await tavily_search(query, max_results=max_results, topic=topic)
        if result["success"] and result.get("results"):
            logger.info(f"🧠 Smart: Tavily")
    
    # 2. Serper (Google)
    if (not result or not result["success"] or not result.get("results")) and _get_serper_key():
        result = await serper_search(query, max_results=max_results)
        if result["success"] and result.get("results"):
            logger.info(f"🧠 Smart: Serper fallback")
    
    # 3. DuckDuckGo
    if not result or not result["success"] or not result.get("results"):
        result = await ddg_search(query, max_results=max_results)
        if result["success"] and result.get("results"):
            logger.info(f"🧠 Smart: DDG fallback")
    
    # 4. Deep Read
    if deep_read and result and result["success"] and result.get("results"):
        urls = [r["url"] for r in result["results"][:3] if r.get("url")]
        if urls:
            reads = await asyncio.gather(
                *[jina_read(u) for u in urls], return_exceptions=True)
            for i, rd in enumerate(reads):
                if isinstance(rd, dict) and rd.get("success") and i < len(result["results"]):
                    result["results"][i]["full_content"] = rd["content"][:3000]
            logger.info(f"🧠 Deep read: {len(urls)} pages")
    
    return result


async def smart_news(
    query: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    🧠 Умные новости — 3 уровня fallback:
    
    Tavily(news) → Serper(news) → DuckDuckGo News
    """
    result = None
    
    # 1. Tavily News
    if _get_tavily_key():
        result = await tavily_search(query, max_results=max_results, topic="news", time_range="week")
        if result["success"] and result.get("results"):
            logger.info(f"🧠 Smart News: Tavily")
    
    # 2. Serper News
    if (not result or not result["success"] or not result.get("results")) and _get_serper_key():
        result = await serper_search(query, max_results=max_results, search_type="news")
        if result["success"] and result.get("results"):
            logger.info(f"🧠 Smart News: Serper fallback")
    
    # 3. DuckDuckGo News
    if not result or not result["success"] or not result.get("results"):
        result = await ddg_news(query, max_results=max_results)
        if result["success"] and result.get("results"):
            logger.info(f"🧠 Smart News: DDG fallback")
    
    return result


async def deep_research(
    query: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    🔬 Глубокий ресёрч — поиск + извлечение полного контента.
    
    Для сложных вопросов где нужна детальная информация:
    - наука, медицина, юриспруденция
    - сравнение технологий
    - развёрнутый анализ
    
    Выполняет smart_search + Jina Reader на все результаты.
    Занимает 5-10 сек, но даёт максимум информации.
    """
    return await smart_search(
        query=query,
        max_results=max_results,
        deep_read=True,
    )


# ============================================================
# СЛОЙ 6: ФОРМАТИРОВАНИЕ
# ============================================================

def format_for_prompt(
    result: Dict[str, Any],
    label: str = "🌐 ИНФОРМАЦИЯ ИЗ ИНТЕРНЕТА",
    max_chars: int = 2000,
) -> str:
    """
    Форматировать результат поиска для инъекции в system prompt.
    Формат: жёсткая структура фактов которую LLM не может проигнорировать.
    Если есть full_content (от Jina) — используем его для более глубокого контекста.
    """
    if not result or not result.get("success"):
        return ""
    
    results_list = result.get("results", [])
    if not results_list:
        return ""
    
    parts = [f"[{label}]"]
    
    # Tavily answer — самый точный, ставим как ФАКТ
    if result.get("answer"):
        parts.append(f"ФАКТ: {result['answer']}")
    
    # Источники — с учётом deep content
    _chars_used = len(parts[0]) + (len(parts[1]) if len(parts) > 1 else 0)
    _chars_per_source = (max_chars - _chars_used) // min(len(results_list), 3)
    
    for i, r in enumerate(results_list[:3], 1):
        source = r.get("url", "").split("/")[2] if r.get("url") and "/" in r.get("url", "") else ""
        # Если есть full_content от Jina — берём его (глубокий контент)
        full = r.get("full_content", "")
        if full and len(full) > 100:
            content = full[:_chars_per_source]
            parts.append(f"[{source} — полный текст]:\n{content}")
        else:
            content = r.get("content", "")[:min(300, _chars_per_source)]
            if content:
                parts.append(f"[{source}]: {content}")
    
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


# ============================================================
# UTILS
# ============================================================

def _ok(source: str, results: list, answer: str = None) -> Dict[str, Any]:
    return {"success": True, "answer": answer, "results": results, "source": source, "error": None}

def _err(source: str, error: str) -> Dict[str, Any]:
    return {"success": False, "answer": None, "results": [], "source": source, "error": error}
