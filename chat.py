"""
chat.py — диалог «Обсудить главу с Квантареоном» через Groq

Читатель эссе задаёт вопрос по конкретной части — Квантареон отвечает
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

_ESSAY_DIR = Path(__file__).parent


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
            "reply": "Квантареон сейчас молчит — связь прервалась. Попробуй ещё раз через минуту.",
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

# ============================================================
# РАСПОЗНАВАНИЕ РЕЧИ (Groq Whisper)
# ============================================================

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MODEL = os.getenv("QUANTARION_STT_MODEL", "whisper-large-v3-turbo")
MAX_AUDIO_BYTES = 8 * 1024 * 1024  # 8 МБ — с запасом на пару минут речи


async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.webm",
                           language: str = "ru") -> dict:
    """
    Речь -> текст через Groq Whisper.
    Возвращает {"text": str} или {"text": "", "error": str}
    """
    if not GROQ_API_KEY:
        return {"text": "", "error": "no_key"}
    if not audio_bytes:
        return {"text": "", "error": "empty"}
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return {"text": "", "error": "too_large"}

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {"file": (filename, audio_bytes, "application/octet-stream")}
    data = {"model": STT_MODEL, "response_format": "json"}
    if language:
        data["language"] = language

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(GROQ_STT_URL, headers=headers, files=files, data=data)
            r.raise_for_status()
            text = (r.json().get("text") or "").strip()
            return {"text": _drop_hallucination(text)}
    except Exception as e:
        return {"text": "", "error": str(e)[:200]}


# Whisper на тишине и шуме выдумывает фразы из титров, на которых учился.
# Такие «призраки» отбрасываем, чтобы они не лезли в поле ввода.
# Титры-подписи: мусор с любым хвостом («субтитры создавал такой-то»)
_GHOST_CREDITS = (
    "субтитры создавал",
    "субтитры сделал",
    "субтитры делал",
    "субтитры подготовил",
    "редактор субтитров",
    "корректор субтитров",
    "субтитры и перевод",
    "перевод и субтитры",
    "subtitles by",
    "subs by",
    "amara.org",
    "transcription by",
)

# Обычные фразы-паразиты: выбрасываем, только если это весь ответ целиком
_GHOST_LINES = (
    "продолжение следует",
    "спасибо за просмотр",
    "спасибо за внимание",
    "подписывайтесь на канал",
    "ставьте лайки",
    "до новых встреч",
    "всем пока",
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "you",
    "bye",
    "спасибо",
    "спасибо большое",
    "ага",
    "угу",
    "продолжение",
    "конец",
    "музыка",
    "аплодисменты",
    "смех",
    "thank you",
    "thanks",
    "okay",
    "ok",
    "music",
    "applause",
    "[музыка]",
    "[music]",
)


def _drop_hallucination(text: str) -> str:
    """Пустой ответ вместо выдуманной фразы (Whisper фантазирует на тишине и шуме)."""
    if not text:
        return ""
    probe = text.lower().strip(" .,!?\u2026-\u2014\"'\u00ab\u00bb\n\t")
    if len(probe) < 2:
        return ""
    for g in _GHOST_CREDITS:            # титры — режем с хвостом
        if probe.startswith(g):
            return ""
    for g in _GHOST_LINES:              # фразы — только если это весь ответ
        if probe == g or (probe.startswith(g) and len(probe) <= len(g) + 6):
            return ""
    return text

# ============================================================
# ПОТОКОВОЕ РАСПОЗНАВАНИЕ (Deepgram) — текст появляется во время речи
# ============================================================

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


# Ключевые термины проекта — Deepgram Nova-3 склоняется к ним при распознавании
# твоей речи (keyterm prompting). Сюда — имена и слова, которые движок иначе
# слышит криво. Дополняется свободно.
DEEPGRAM_KEYTERMS = [
    "Квантареон", "Квантарион", "инсайт", "накшатра", "накшатры",
    "мухурта", "кундалини", "самадхи", "сабианский", "сабианские градусы",
    "хора", "профекции", "синастрия", "хорар", "эфемериды",
    "фрактал", "фрактальная астрология", "асцендент", "натальная карта",
]

def deepgram_url(language: str = "ru") -> str:
    """Адрес Deepgram Nova-3 с настройками. Nova-3 точнее Nova-2 на русском
    и поддерживает keyterm prompting — подсказку ожидаемых терминов."""
    from urllib.parse import quote_plus
    params = [
        "model=nova-3",
        f"language={language}",
        "punctuate=true",
        "smart_format=true",
        "filler_words=false",
        "encoding=linear16",
        "sample_rate=16000",
        "channels=1",
        "endpointing=300",
        "interim_results=true",
    ]
    # keyterm работает на nova-3; добавляем каждый термин отдельным параметром
    for kt in DEEPGRAM_KEYTERMS:
        params.append("keyterm=" + quote_plus(kt))
    return f"{DEEPGRAM_WS_URL}?{'&'.join(params)}"


async def open_deepgram(language: str = "ru"):
    """Открывает сокет к Deepgram. Возвращает соединение или None."""
    if not DEEPGRAM_API_KEY:
        return None
    import websockets
    url = deepgram_url(language)
    auth = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    try:
        try:
            return await websockets.connect(url, extra_headers=auth)
        except TypeError:
            # в новых версиях библиотеки параметр называется иначе
            return await websockets.connect(url, additional_headers=auth)
    except Exception:
        return None

# ============================================================
# ОЗВУЧКА ОТВЕТОВ (edge-tts, по конвейеру Оракула)
# ============================================================

# Голоса по версиям сайта. По умолчанию везде Андрей (проверенный по Оракулу);
# захочешь Дмитрия на русской — переменная QUANTARION_TTS_VOICE_RU=ru-RU-DmitryNeural в Render
TTS_VOICE_RU = os.getenv("QUANTARION_TTS_VOICE_RU", "ru-RU-DmitryNeural")
TTS_VOICE_EN = os.getenv("QUANTARION_TTS_VOICE_EN", "en-US-AndrewMultilingualNeural")
# Русский — как в аудиокниге (голос Дмитрий): темп -15%, высота -12Hz.
# Английский — как было (голос Эндрю): темп +5%, высота -15Hz.
TTS_RATE_RU = os.getenv("QUANTARION_TTS_RATE_RU", "-10%")
TTS_PITCH_RU = os.getenv("QUANTARION_TTS_PITCH_RU", "-12Hz")
TTS_VOLUME_RU = os.getenv("QUANTARION_TTS_VOLUME_RU", "+15%")
TTS_RATE_EN = os.getenv("QUANTARION_TTS_RATE_EN", "+5%")
TTS_PITCH_EN = os.getenv("QUANTARION_TTS_PITCH_EN", "-15Hz")
TTS_VOLUME_EN = os.getenv("QUANTARION_TTS_VOLUME_EN", "+15%")

import re as _re



# ============================================================
# СЛОВАРЬ УДАРЕНИЙ (из аудиокниги, голос Дмитрий)
# Движок edge-tts предсказуемо ошибается в одних и тех же словах.
# Перед озвучкой русского текста заменяем их на формы, которые голос
# произносит верно (удвоение ударной гласной / фонетическая запись).
# Приёмы и список — те же, что утверждены при озвучке книги.
# ============================================================

# Пословные замены (по границе слова, регистр сохраняем у первой буквы).
# Ключ — как пишется в норме, значение — как отдать движку.
_UDAR_WORDS = {
    # Слова с ОДНОЗНАЧНЫМ ударением из отработанного словаря аудиокниги.
    # Двузначные ("стоит" сто́ит/стои́т, "самой" са́мой/само́й) СОЗНАТЕЛЬНО не берём:
    # в живом тексте смысл заранее неизвестен, автозамена сломала бы половину
    # случаев — движок их чаще читает верно сам. Список дополняется по слуху.
    "тела": "телаа",       # тела́ (мн.ч.) — движок тянет те́ла
    "ума": "умаа",         # ума́ (род.п.)
    "ядра": "ядраа",       # ядра́ (род.п.)
    "ходу": "хооду",       # хо́ду
    "часа": "чааса",       # ча́са
    "волны": "волныы",     # волны́ (род.п., "длина волны")
    "замки": "замкии",     # замки́ (запоры) — движок читает за́мки
    "мастеров": "мастиров",# мастеро́в — фонетическая (короткое частое слово)
}

# Замены-подстроки (санскрит, аббревиатуры, устойчивые формы) —
# применяются как есть, без границы слова.
_UDAR_SUBSTR = [
    ("кундалини", "кундалинии"),   # кундали́ни
    ("самому",    "самомуу"),      # самому́
    ("среду",     "сридуу"),       # сре́ду — фонетическая запись (его выбор в книге)
]

def _apply_udar(text: str) -> str:
    t = text
    def _sub_keepcase(good):
        def _r(m):
            w = m.group(0)
            return good[0].upper() + good[1:] if w[:1].isupper() else good
        return _r
    for bad, good in _UDAR_SUBSTR:
        t = _re.sub(_re.escape(bad), _sub_keepcase(good), t, flags=_re.IGNORECASE)
    def _wrepl(m):
        w = m.group(0)
        rep = _UDAR_WORDS[w.lower()]
        # сохраняем заглавную первую букву
        return rep[0].upper() + rep[1:] if w[0].isupper() else rep
    pattern = r"\b(" + "|".join(_re.escape(k) for k in _UDAR_WORDS) + r")\b"
    t = _re.sub(pattern, _wrepl, t, flags=_re.IGNORECASE)
    return t


def _tts_clean(text: str, language: str = "ru") -> str:
    """Готовим текст к озвучке: убираем то, что голос прочитал бы вслух как мусор."""
    t = text or ""
    t = _re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", t)   # эмодзи
    t = _re.sub(r"\*{1,3}", "", t)                                        # **жирный**
    t = _re.sub(r"#{1,6}\s*", "", t)                                       # ## заголовки
    t = _re.sub(r"`+", "", t)                                              # `код`
    t = _re.sub(r"\s+", " ", t)
    t = t.strip()
    if language == "ru":
        t = _apply_udar(t)
    return t


def _tts_chunks(text: str, limit: int = 260):
    """Режем текст на фразы и собираем куски до ~260 символов.
    Первую фразу отдаём отдельно и без запятых — голос стартует быстрее
    (приём из конвейера Оракула)."""
    sentences = _re.split(r"(?<=[.!?\u2026])\s+", text)
    sentences = [s for s in (x.strip() for x in sentences) if s]
    if not sentences:
        return
    # Первый кусок делаем совсем коротким (до ~60 символов, по границе слова):
    # чем меньше текста, тем раньше польётся звук. Остаток первой фразы — вторым куском.
    first_sent = _re.sub(r"[,;:\-\u2014\u2013]", " ", sentences[0])
    first_sent = _re.sub(r"\s+", " ", first_sent).strip()
    if len(first_sent) > 60:
        cut = first_sent.rfind(" ", 20, 60)
        if cut == -1:
            cut = 60
        yield first_sent[:cut].strip()
        rest = first_sent[cut:].strip()
        if rest:
            sentences = [rest] + sentences[1:]
        else:
            sentences = sentences[1:]
    else:
        yield first_sent
        sentences = sentences[1:]
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) + 1 > limit:
            yield buf
            buf = s
        else:
            buf = (buf + " " + s).strip()
    if buf:
        yield buf


async def tts_stream(text: str, language: str = "ru"):
    """Асинхронный поток mp3-кусков: первый уходит, пока следующие синтезируются.
    Каждый кусок собирается целиком (без щелчков) и с тремя попытками."""
    import edge_tts

    clean = _tts_clean(text, language)
    if not clean:
        return

    for chunk_text in _tts_chunks(clean):
        audio = b""
        for attempt in range(3):
            try:
                comm = edge_tts.Communicate(
                    text=chunk_text,
                    voice=(TTS_VOICE_RU if language == "ru" else TTS_VOICE_EN),
                    rate=(TTS_RATE_RU if language == "ru" else TTS_RATE_EN),
                    pitch=(TTS_PITCH_RU if language == "ru" else TTS_PITCH_EN),
                    volume=(TTS_VOLUME_RU if language == "ru" else TTS_VOLUME_EN),
                )
                buf = bytearray()
                async for part in comm.stream():
                    if part["type"] == "audio":
                        buf.extend(part["data"])
                if buf:
                    audio = bytes(buf)
                    break
            except Exception:
                if attempt < 2:
                    import asyncio as _aio
                    await _aio.sleep(0.4 * (attempt + 1))
        if audio:
            yield audio

