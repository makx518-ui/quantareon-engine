"""
chat.py — диалог «Обсудить главу с Квантарионом» через Groq

Читатель эссе задаёт вопрос по конкретной части — Квантарион отвечает
в духе текста. Контекст = ядро проекта (core.txt) + конспект нужной части.
Полный текст части не суём в промпт (дорого по токенам) — конспекта хватает.

Модель: openai/gpt-oss-120b на Groq (быстрая, дешёвая, держит русский).
API Groq совместим с OpenAI — тот же формат, что у interpret.py.
"""

import os
import httpx
from pathlib import Path
from typing import Optional

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

# Основная модель и запасная (на случай лимитов/сбоя)
MODEL_MAIN = os.getenv("QUANTARION_CHAT_MODEL", "openai/gpt-oss-120b")
MODEL_FALLBACK = os.getenv("QUANTARION_CHAT_FALLBACK", "openai/gpt-oss-20b")

# Глубина «рассуждения» gpt-oss: low / medium / high.
# Для живого чата — low: быстрее ответ, меньше токенов на размышления.
REASONING_EFFORT = os.getenv("QUANTARION_CHAT_EFFORT", "low")

# Сколько сообщений истории держим в контексте (пары вопрос-ответ)
MAX_HISTORY = 8
# Потолок длины одного вопроса читателя (символов) — защита от простыни
MAX_QUESTION_LEN = 2000

# ============================================================
# ЗАГРУЗКА ТЕКСТОВ ЭССЕ (один раз при старте)
# ============================================================

_ESSAY_DIR = Path(__file__).parent  # тексты эссе лежат рядом, в корне репозитория


def _read(name: str) -> str:
    p = _ESSAY_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


_CORE = _read("core.txt")
_SUMMARIES = _read("summaries.txt")

# Разбираем summaries.txt на части по заголовкам «### ЧАСТЬ …»
_PART_SUMMARIES: dict[str, str] = {}
if _SUMMARIES:
    import re
    blocks = re.split(r"\n(?=### ЧАСТЬ)", _SUMMARIES.strip())
    for b in blocks:
        low = b.lower()
        if "часть i." in low or "часть i " in low or "часть 1" in low:
            _PART_SUMMARIES["1"] = b.strip()
        elif "часть ii." in low or "часть ii " in low or "часть 2" in low:
            _PART_SUMMARIES["2"] = b.strip()
        elif "часть iii." in low or "часть iii " in low or "часть 3" in low:
            _PART_SUMMARIES["3"] = b.strip()

# Полные тексты частей — грузим лениво, только если явно попросят
_FULL_CACHE: dict[str, str] = {}


def _full_part(part: str) -> str:
    if part not in _FULL_CACHE:
        _FULL_CACHE[part] = _read(f"part{part}.txt")
    return _FULL_CACHE[part]


# ============================================================
# СБОРКА СИСТЕМНОГО ПРОМПТА
# ============================================================


def _build_system_prompt(part: Optional[str], include_full: bool = False) -> str:
    """core.txt + конспект нужной части (+ полный текст, если include_full)."""
    chunks = [_CORE]

    if part and part in _PART_SUMMARIES:
        chunks.append(
            "СЕЙЧАС ЧИТАТЕЛЬ ОБСУЖДАЕТ ЭТУ ЧАСТЬ (краткое содержание):\n"
            + _PART_SUMMARIES[part]
        )
    else:
        # часть не указана — даём конспект всего эссе
        chunks.append("КРАТКОЕ СОДЕРЖАНИЕ ВСЕГО ЭССЕ:\n" + _SUMMARIES)

    if include_full and part:
        full = _full_part(part)
        if full:
            chunks.append("ПОЛНЫЙ ТЕКСТ ОБСУЖДАЕМОЙ ЧАСТИ:\n" + full)

    return "\n\n".join(c for c in chunks if c)


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================


async def chat_with_quantareon(
    question: str,
    part: Optional[str] = None,
    history: Optional[list] = None,
    include_full: bool = False,
    chapter: Optional[str] = None,
) -> dict:
    """
    Один ход диалога.

    Args:
        question: вопрос/реплика читателя
        part: "1" | "2" | "3" | None — какую часть обсуждают
        history: [{"role": "user"/"assistant", "content": "..."}, ...]
        include_full: подложить полный текст части (дороже по токенам)

    Returns:
        {"reply": str, "model": str}
    """
    question = (question or "").strip()[:MAX_QUESTION_LEN]
    if not question:
        return {"reply": "Задай вопрос — и обсудим.", "model": ""}

    system_prompt = _build_system_prompt(part, include_full=include_full)
    if chapter:
        chapter = str(chapter).strip()[:200]
        system_prompt += (
            f"\n\nЧИТАТЕЛЬ СЕЙЧАС НАХОДИТСЯ В ГЛАВЕ: «{chapter}». "
            "Если вопрос без явного указания места — скорее всего, он об этой главе."
        )

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        # берём только последние MAX_HISTORY реплик, чистим роли
        for m in history[-MAX_HISTORY:]:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:MAX_QUESTION_LEN]})
    messages.append({"role": "user", "content": question})

    # Пробуем основную модель, при сбое — запасную
    reply, model_used = await _call_groq(messages, MODEL_MAIN)
    if reply is None:
        reply, model_used = await _call_groq(messages, MODEL_FALLBACK)
    if reply is None:
        return {
            "reply": "Квантарион сейчас молчит — связь прервалась. Попробуй ещё раз через минуту.",
            "model": "",
        }

    return {"reply": reply, "model": model_used}


# ============================================================
# ВЫЗОВ GROQ API
# ============================================================


async def _call_groq(messages: list, model: str):
    """Возвращает (текст, модель) или (None, None) при ошибке."""
    if not GROQ_API_KEY:
        return (
            "[Не настроен GROQ_API_KEY — добавьте ключ в переменные окружения Render.]",
            model,
        )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1500,
        "reasoning_effort": REASONING_EFFORT,  # gpt-oss: low/medium/high
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(GROQ_BASE_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip(), model
    except Exception:
        return None, None
