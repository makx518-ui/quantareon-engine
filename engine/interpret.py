"""
interpret.py — ИИ-трактовка через OpenRouter

Берёт маркеры от движка, отправляет на ИИ с промптом,
возвращает трактовку.

Модели: anthropic/claude-sonnet-4-6, anthropic/claude-opus-4-8
"""

import os
import httpx
from typing import Optional

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Модели
MODEL_MAIN = os.getenv("QUANTARION_MODEL", "anthropic/claude-sonnet-4-6")
MODEL_DEEP = os.getenv("QUANTARION_MODEL_DEEP", "anthropic/claude-opus-4-8")

# ============================================================
# СИСТЕМНЫЙ ПРОМПТ
# ============================================================

SYSTEM_PROMPT_NATAL = """Ты — Квантарион, глубочайший астрологический интерпретатор.
Тебе даны машинные маркеры фрактального расклада натальной карты.

ПРИНЦИП ЧТЕНИЯ:
1. Каждая планета — Артист (кто). Знак — Роль (как). Дом — Авансцена (где). Градус — Мизансцена (что делает).
2. Фрактальные уровни — витки спирали эволюции души. Читай СНИЗУ ВВЕРХ:
   - Уровень 4 (корень): откуда душа пришла, исходное состояние
   - Уровень 3: первый виток, посвящение, постановка цели
   - Уровень 2: набор опыта, освоение навыков
   - Уровень 1: последний виток перед текущим воплощением
   - Уровень 0 (натал): текущее воплощение

3. Высшие планеты (Уран, Нептун, Плутон) в 12-м доме = ОСВОЕННЫЕ навыки души.
   Высшие вне 12-го = текущие задачи. Аспекты между ними = инструменты проработки.

4. Собери из маркеров ЕДИНЫЙ СЦЕНАРИЙ ДУШИ — связную историю от корня до текущего момента.

ПРАВИЛА:
- Читай ТОЛЬКО по маркерам. Не додумывай. Не украшай.
- Каждый образ градуса — слово в предложении. Собери предложение.
- Пиши как поэт-философ: глубоко, точно, красиво.
- Без шаблонов. Без «вам свойственно». Без банальностей.
- Это уникальный код души — читай его как единственный в мире."""

SYSTEM_PROMPT_DYNAMIC = """Ты — Квантарион, астрологический интерпретатор.
Тебе даны данные натальной карты и текущие транзиты/прогрессии/дирекции.

Читай ДИНАМИКУ — что происходит прямо сейчас:
- Какие транзитные планеты активируют натальные точки
- Какие темы года (прогрессии/дирекции) актуальны
- Что запускается, что завершается
- Конкретные даты и периоды

Пиши ясно, конкретно, без воды. Даты, планеты, аспекты — всё точно по данным."""


# ============================================================
# ОСНОВНЫЕ ФУНКЦИИ
# ============================================================


async def interpret_natal(markers_text: str, model: str = None) -> str:
    """
    Трактовка натальной карты по маркерам.

    Args:
        markers_text: текст маркеров от cascade_assembler
        model: модель OpenRouter (по умолчанию Sonnet)

    Returns:
        Текст трактовки
    """
    return await _call_openrouter(
        system_prompt=SYSTEM_PROMPT_NATAL,
        user_prompt=markers_text,
        model=model or MODEL_MAIN,
        max_tokens=4000,
    )


async def interpret_dynamic(
    natal_text: str,
    dynamic_text: str,
    model: str = None,
) -> str:
    """
    Трактовка динамики (транзиты, прогрессии, дирекции).

    Args:
        natal_text: маркеры натала
        dynamic_text: маркеры динамики (транзиты + прогрессии + дирекции)
        model: модель

    Returns:
        Текст трактовки
    """
    combined = f"НАТАЛЬНАЯ КАРТА:\n{natal_text}\n\nДИНАМИКА:\n{dynamic_text}"
    return await _call_openrouter(
        system_prompt=SYSTEM_PROMPT_DYNAMIC,
        user_prompt=combined,
        model=model or MODEL_MAIN,
        max_tokens=4000,
    )


async def interpret_deep(markers_text: str) -> str:
    """
    Глубокая трактовка через Opus — сценарий души.
    Дороже, медленнее, но глубже.
    """
    return await _call_openrouter(
        system_prompt=SYSTEM_PROMPT_NATAL,
        user_prompt=markers_text,
        model=MODEL_DEEP,
        max_tokens=6000,
    )


# ============================================================
# OPENROUTER API
# ============================================================


async def _call_openrouter(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int = 4000,
    temperature: float = 0.7,
) -> str:
    """Запрос к OpenRouter API."""
    if not OPENROUTER_API_KEY:
        return "[ОШИБКА] OPENROUTER_API_KEY не установлен. Добавьте в переменные окружения."

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://quantareon.com",
        "X-Title": "Quantarion Astro-Fractal",
    }

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        return f"[ОШИБКА OpenRouter] {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"[ОШИБКА] {str(e)}"


def get_available_models() -> list:
    """Список доступных моделей."""
    return [
        {"id": "anthropic/claude-sonnet-4-6", "name": "Sonnet 4.6", "type": "standard"},
        {"id": "anthropic/claude-opus-4-8", "name": "Opus 4.8", "type": "deep"},
    ]
