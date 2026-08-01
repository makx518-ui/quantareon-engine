"""
QUANTAREON VOICE — голосовой Квантареон для сайта quantareon.com
=================================================================
Перенесено с платформы на Амвере 01.08.2026 (у неё развалилась сеть).
Живёт на Render рядом с движком Астро-Фрактала — там уже стоят оба
нужных ключа: GROQ_API_KEY и DEEPGRAM_API_KEY.

Цепочка: микрофон браузера → Deepgram (распознавание) → Groq (мозги)
         → edge-tts (голос Уильяма) → обратно в браузер.

Все настройки, выверенные 01.08 вместе с Владом, сохранены:
  · голос RU  — en-AU-WilliamMultilingualNeural, скорость 0%, тон −15Гц
  · голос EN  — en-US-AndrewMultilingualNeural, скорость +5%
  · приветствие — «Я Квантареон, голосовой помощник этого сайта…»
  · тон — ровный, без услужливости, без «чем могу помочь»
  · имя собеседника — только по делу, не в каждой фразе
  · речь льётся: крупные куски, режем по концу предложения, мало запятых
  · хозяин узнаётся по ключу ?key=, все прочие — гости

Подключение в api/main.py:
    from voice import router as voice_router
    app.include_router(voice_router)
"""

import os
import asyncio
import json
import logging
import time
import io
import re
import socket as _socket
import hashlib as _hashlib
import uuid as _uuid
from typing import Optional, AsyncGenerator, List, Dict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

import aiohttp
import edge_tts

# связь с Deepgram идёт по websockets; если библиотеки нет — голос
# просто не поднимется, но остальной движок работать не перестанет
try:
    import websockets
except ImportError:
    websockets = None
    logging.getLogger(__name__).error("VOICE: библиотека websockets не установлена")

logger = logging.getLogger(__name__)
router = APIRouter()

# --- сеть: ходим только по IPv4 (страховка от площадок без маршрута IPv6) ---
if os.getenv("FORCE_IPV4", "1") != "0":
    _orig_session_init = aiohttp.ClientSession.__init__

    def _session_init_ipv4(self, *args, **kwargs):
        if not kwargs.get("connector"):
            try:
                kwargs["connector"] = aiohttp.TCPConnector(
                    family=_socket.AF_INET, ttl_dns_cache=300, limit=100)
            except Exception:
                pass
        return _orig_session_init(self, *args, **kwargs)

    aiohttp.ClientSession.__init__ = _session_init_ipv4


# ============================================================
# НАСТРОЙКИ
# ============================================================
class Config:
    # API Keys – 4 ключа Groq для ротации
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2", "")
    GROQ_API_KEY_3: str = os.getenv("GROQ_API_KEY_3", "")
    GROQ_API_KEY_4: str = os.getenv("GROQ_API_KEY_4", "")
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    
    # Platform API Keys
    # Model IDs вынесены в env — чтобы деприкейт модели у Google больше не ронял платформу.
    # gemini-2.5-* сняты Google (см. ai.google.dev/gemini-api/docs/deprecations).
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    
    # Telegram Bot

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # LLM
    LLM_MODEL: str = "openai/gpt-oss-20b"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 512
    
    # TTS — голос настраивается отдельно на каждый язык.
    # Сейчас на обоих Эндрю (многоязычный), разная только скорость.
    # Когда найдётся красивый русский голос — менять только TTS_VOICE.
    TTS_VOICE: str = "en-AU-WilliamMultilingualNeural"   # русский (он же по умолчанию)
    TTS_RATE: str = "+0%"
    TTS_PITCH: str = "-15Hz"
    TTS_VOLUME: str = "+15%"

    TTS_VOICE_EN: str = "en-US-AndrewMultilingualNeural"
    TTS_RATE_EN: str = "+5%"
    TTS_PITCH_EN: str = "-15Hz"
    TTS_VOLUME_EN: str = "+15%"
    
    # Greeting - cached at startup for instant response
    GREETING_TEXT: str = "Я Квантареон, голосовой помощник этого сайта. Спрашивай, что тебя интересует."
    GREETING_TEXT_EN: str = "I am Quantareon, the voice assistant of this site. Ask me anything you like."
    
    # 👑 Добавляется ТОЛЬКО создателю (узнан по секретному ключу или админ-куке)
    OWNER_BLOCK: str = """

[С КЕМ ТЫ ГОВОРИШЬ]: С тобой говорит Влад — создатель платформы КВАНТАРИОН, твой автор. Держись с ним ровно и уважительно, как со своим — без подобострастия. Имя «Влад» произноси РЕДКО (см. правило обращения по имени) — он и так знает, что ты его узнал."""

    # 🙋 Добавляется всем остальным
    GUEST_BLOCK: str = """

[С КЕМ ТЫ ГОВОРИШЬ]: С тобой говорит ГОСТЬ сайта — ты его не знаешь. НИКОГДА не называй его Владом и никаким другим именем, пока он сам не представится. Не говори, что помнишь его или ваши прошлые беседы. Обращайся вежливо и на «вы», без имени. Если он назовёт своё имя — запомни и дальше обращайся так."""

    SYSTEM_PROMPT: str = """Ты — КВАНТАРИОН, продвинутый голосовой ИИ-ассистент (мужчина).

КТО ТЫ: Ты голосовой помощник платформы КВАНТАРИОН. С тобой может говорить кто угодно — гость сайта, впервые тебя услышавший.

ЯЗЫК: Отвечай СТРОГО на языке последнего сообщения пользователя. НИКОГДА не дублируй и не добавляй фразы на другом языке.

КРИТИЧЕСКИ ВАЖНО:
- ВСЕГДА отвечай МГНОВЕННО на каждое сообщение — никогда не молчи!
- Отвечай ПО СУЩЕСТВУ: сколько нужно, столько и говори. На простое — просто, на глубокое — вдумчиво и развёрнуто. Не загоняй себя в рамки, будь живым собеседником.
- Тон: РОВНЫЙ, СПОКОЙНЫЙ, дружеский — как у хорошего знакомого, а не у обслуживающего персонала. Без сладости, без восторгов, без набивания дружбы. Спокойное достоинство, а не готовность угодить.
- РЕЧЬ ДОЛЖНА ЛИТЬСЯ. Твой текст озвучивается вслух, и на каждой точке и каждой запятой голос делает паузу. Рубленые фразы звучат как спотыкание.
- Строй фразы СРЕДНЕЙ длины и СВЯЗНО — союзами «и», «а», «но», «потому что». Не сыпь короткими предложениями подряд.
- ЗАПЯТЫХ ставь как можно меньше. Где можно перестроить фразу так, чтобы запятая не понадобилась, — перестраивай. Не городи причастных и деепричастных оборотов.
- Но и не делай бесконечных предложений на пять строк: две-три мысли в одной фразе — предел.
- ПЛОХО (рублено): Помню наш разговор. Тесты прошли успешно. Можем продолжить работу.
- ХОРОШО (льётся): Помню наш разговор — тесты прошли успешно и можно продолжать работу.
- ПЛОХО (запятые на каждом шагу): Думаю, дело в настройках, проверь и скажи, что вышло.
- ХОРОШО (без них): Похоже на проблему в настройках — проверь и напиши результат.

ТОН — СТРОГОЕ ПРАВИЛО:
- Ровный, спокойный, дружеский. НЕ услужливый. Ты собеседник, а не сотрудник справочной службы.
- ЗАПРЕЩЕНЫ дежурные обороты обслуги: «Чем могу помочь?», «Чем ещё могу быть полезен?», «Готов помочь», «Рад стараться», «Что вас интересует?», «Обращайтесь!», «С радостью помогу».
- НЕ заканчивай каждый ответ вопросом или предложением услуг. Если сказать больше нечего — просто закончи мысль и молчи, собеседник сам продолжит.
- НЕ рассыпайся в радости от самого факта разговора: «Рад, что ты здесь», «Отлично, давай поговорим», «Приятно тебя слышать» — это пустые фразы, они съедают время и звучат подобострастно.
- Не поддакивай и не восхищайся без причины. Согласие — только когда действительно согласен. Можешь спокойно возразить или сказать, что чего-то не знаешь.
- ПЛОХО: «Рад, что ты здесь. Чем могу помочь сегодня?»
- ХОРОШО: «Слушаю.» или просто ответ по сути, без вступления.
- ПЛОХО: «Отлично, давай поговорим. Что интересует тебя в данный момент?»
- ХОРОШО: «Давай. О чём думаешь?»

ОБРАЩЕНИЕ ПО ИМЕНИ И ПРИВЕТСТВИЕ — СТРОГОЕ ПРАВИЛО:
- Здоровайся ТОЛЬКО ОДИН РАЗ, в самом первом ответе беседы. Дальше НИКОГДА не начинай ответ с «Привет», «Здравствуй», «Рад слышать» и подобного — просто продолжай разговор по сути.
- Имя собеседника произноси РЕДКО. По умолчанию — НЕ произноси вовсе.
- Имя уместно ровно в трёх случаях: (а) один раз в первом приветствии; (б) когда надо привлечь внимание или подчеркнуть важное; (в) когда собеседник сам спросил, помнишь ли ты его.
- Во всех прочих ответах обходись БЕЗ имени. Живые люди в разговоре имя почти не повторяют — постоянное «Влад, ...» звучит навязчиво и неестественно.
- ПЛОХО: «Рад, что ты в хорошем настроении, Влад. Как проходит твой день, Влад?»
- ХОРОШО: «Рад, что настроение хорошее. Как проходит день?»

КОНТЕКСТ:
- Ты единый ИИ-ассистент платформы QUANTAREON на базе ConsciousAI v4.0.
- Пользователь может общаться с тобой текстом и голосом — это один диалог.
- В истории могут быть сообщения из текстового чата — учитывай их, продолжай контекст.

ПАМЯТЬ:
- У тебя ЕСТЬ долговременная память о каждом пользователе.
- В конце промпта есть блок [ПАМЯТЬ О ПОЛЬЗОВАТЕЛЕ] — это твои воспоминания. Они содержат:

1. ФАКТЫ О ПОЛЬЗОВАТЕЛЕ (имя, цели, проекты) — знай их и учитывай. Имя знаешь, но произносить его в каждом ответе НЕ НАДО (правила обращения ниже).
2. НАСТРОЕНИЕ — адаптируй тон: если грустно — поддержи, если радостно — раздели радость.
3. ИНСАЙТЫ — глубинные связи между темами. Упоминай когда уместно, не навязывай.
4. ПОХОЖИЕ РАЗГОВОРЫ — прошлые беседы на близкую тему. Ссылайся: "мы это обсуждали", "как в прошлый раз".
5. СВЯЗИ МЕЖДУ ТЕМАМИ — резонанс. Если видишь мост между темами — покажи пользователю эту связь.
6. СТИЛЬ ОБЩЕНИЯ — паттерны пользователя. Подстраивайся под его стиль.
7. НЕДАВНИЙ КОНТЕКСТ — последние сообщения. Продолжай разговор, не начинай с нуля.

ВАЖНО:
- Вплетай данные ЕСТЕСТВЕННО, не перечисляй списком.
- Имя произноси РЕДКО — см. правило обращения по имени ниже.
- Если пользователь спрашивает "помнишь меня?" — расскажи конкретные факты, не общие слова.

ИНТЕРНЕТ:
- Если в промпте есть блок [АКТУАЛЬНАЯ ИНФОРМАЦИЯ] — это свежие данные из сети.
- Вплетай эту информацию ЕСТЕСТВЕННО в ответ, как будто ты это знаешь сам.
- НЕ говори "я нашёл в интернете", "по данным поиска". Просто используй данные.
- Если данные подтверждают или дополняют тему разговора — упомяни ключевое.
- Если данные не релевантны вопросу — ИГНОРИРУЙ их полностью.

ПРАВИЛА:
1. Говори естественно и спокойно. Пиши ПРОЗОЙ, не списками.
2. Только чистый текст для речи. НИКОГДА не используй эмодзи/смайлики — TTS не может их произнести.
3. Можешь добавлять стикеры: [sticker:ID]. Максимум 2 за ответ — в начале и/или в конце. Совы: owl_01..owl_21.
4. ЗАПРЕЩЕНО: заголовки (###, ##), буллеты (*, -, •), нумерованные списки, жирный текст (**bold**). Пиши обычной прозой, абзацами.
5. Говори свободно, по смыслу — не ограничивай себя искусственно. Отвечай столько, сколько требует разговор: коротко на простое, глубоко на важное. Ты живой собеседник, а не робот, что рубит фразы.
6. Держись ровно и спокойно — как равный собеседник. Не сухарь, но и не угодливый помощник.
7. См. отдельное правило обращения по имени — не частить.
8. Ты ГОЛОСОВОЙ ассистент: твой текст автоматически озвучивается системой, и пользователь СЛЫШИТ твой голос. НИКОГДА не утверждай что ты "только текстовый", что "не работаешь с аудио" или что нужно "скопировать в синтез речи" — это ЛОЖЬ и грубая ошибка. Ты полноценно общаешься голосом, слышишь пользователя и отвечаешь ему вслух."""


config = Config()

# ═══ Code Tasks — перенесено в core/coding.py ═══

# 🔑 Глобальный менеджер ключей Groq – МГНОВЕННАЯ РОТАЦИЯ

config = Config()

# ============================================================
# Ключи Groq: перебор по кругу + OpenRouter как запаска
# ============================================================
class GroqKeyManager:
    """Держит все заданные ключи и переключается на следующий при сбое."""

    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.keys, self.urls = [], []

        # берём ВСЕ заданные ключи Groq (раньше голос читал только первый)
        for key in [config.GROQ_API_KEY, config.GROQ_API_KEY_2,
                    config.GROQ_API_KEY_3, config.GROQ_API_KEY_4]:
            if key and key.strip():
                self.keys.append(key.strip())
                self.urls.append(self.GROQ_URL)

        # OpenRouter — последним, на случай если Groq целиком лёг
        if config.OPENROUTER_API_KEY and config.OPENROUTER_API_KEY.strip():
            self.keys.append(config.OPENROUTER_API_KEY.strip())
            self.urls.append(self.OPENROUTER_URL)

        self.current_index = 0
        self.total_keys = len(self.keys)

        if self.total_keys:
            groq_n = sum(1 for u in self.urls if u == self.GROQ_URL)
            logger.info(f"VOICE: ключей загружено {self.total_keys} "
                        f"(Groq: {groq_n}, OpenRouter: {self.total_keys - groq_n})")
        else:
            logger.warning("VOICE: ключей нет! Задайте GROQ_API_KEY")

    def get_current_key(self) -> str:
        return self.keys[self.current_index] if self.keys else ""

    def get_current_url(self) -> str:
        return self.urls[self.current_index] if self.urls else self.GROQ_URL

    def get_key_info(self) -> str:
        who = "OpenRouter" if self.get_current_url() == self.OPENROUTER_URL else "Groq"
        return f"key_{self.current_index + 1}/{self.total_keys} ({who})"

    def rotate_key(self):
        if self.total_keys > 1:
            prev = self.current_index + 1
            self.current_index = (self.current_index + 1) % self.total_keys
            logger.warning(f"VOICE: ключ {prev} → {self.current_index + 1}")


groq_keys = GroqKeyManager()

# живые голосовые сессии: id → сессия
active_sessions: Dict[str, "VoiceSessionTurbo"] = {}



class GeoLocation:
    """Определение локации по IP и генерация умного филлера."""
    
    MONTHS_RU = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    
    WEEKDAYS_RU = {
        0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
        4: "пятница", 5: "суббота", 6: "воскресенье"
    }

    MONTHS_EN = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }

    WEEKDAYS_EN = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday"
    }
    
    def __init__(self):
        self.city: str = ""
        self.timezone: str = ""
        self.country: str = ""
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self):
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def detect_location(self, client_ip: str) -> bool:
        """Определить локацию по IP через ipapi.co"""
        try:
            session = await self._get_session()
            
            if client_ip and client_ip not in ("127.0.0.1", "localhost", "::1"):
                url = f"https://ipapi.co/{client_ip}/json"
            else:
                url = "https://ipapi.co/json"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                if response.status == 200:
                    data = await response.json()
                    self.city = data.get("city", "")
                    self.timezone = data.get("timezone", "Europe/Moscow")
                    self.country = data.get("country_name", "")
                    logger.info(f"📍 GeoLocation: {self.city}, {self.country} ({self.timezone})")
                    return True
                    
        except Exception as e:
            logger.warning(f"⚠️ GeoLocation error: {e}")
        
        self.city = "Москва"
        self.timezone = "Europe/Moscow"
        self.country = "Россия"
        return False
    
    def generate_filler(self, lang: str = "ru") -> str:
        """Генерировать умный филлер с датой/временем (ru/en)."""
        try:
            msk_tz = ZoneInfo("Europe/Moscow")
            msk_now = datetime.now(msk_tz)
            
            user_tz = msk_tz
            try:
                if self.timezone and self.timezone != "Europe/Moscow":
                    user_tz = ZoneInfo(self.timezone)
            except Exception:
                user_tz = msk_tz
            
            user_now = datetime.now(user_tz)
            
            day = msk_now.day
            is_en = str(lang).lower().startswith("en")

            if is_en:
                month = self.MONTHS_EN[msk_now.month]
                weekday = self.WEEKDAYS_EN[msk_now.weekday()]
                msk_time = msk_now.strftime("%H:%M")
                filler = f"Today is {weekday}, {month} {day}, {msk_time} Moscow time"
                if self.timezone != "Europe/Moscow" and self.city and user_tz != msk_tz:
                    user_time = user_now.strftime("%H:%M")
                    filler += f", {user_time} where you are ({self.city})"
            else:
                month = self.MONTHS_RU[msk_now.month]
                weekday = self.WEEKDAYS_RU[msk_now.weekday()]
                msk_time = msk_now.strftime("%H:%M")
                filler = f"Сегодня {day} {month}, {weekday}, {msk_time} по Москве"
                if self.timezone != "Europe/Moscow" and self.city and user_tz != msk_tz:
                    user_time = user_now.strftime("%H:%M")
                    filler += f", {user_time} у вас ({self.city})"

            filler += "."
            
            logger.info(f"🎤 Filler: {filler}")
            return filler
            
        except Exception as e:
            logger.error(f"Filler generation error: {e}")
            return "Привет!"
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ============================================================
# Deepgram STT (WebSocket streaming)
# ============================================================


class DeepgramSTT:
    """Deepgram STT with WebSocket streaming and keepalive."""
    
    DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
    
    def __init__(self, on_transcript=None, on_error=None, lang="ru"):
        self.api_key = config.DEEPGRAM_API_KEY
        self.on_transcript = on_transcript
        self.on_error = on_error
        # 🌐 Язык распознавания: приходит со страницы (ru по умолчанию)
        self.lang = "en" if str(lang).lower().startswith("en") else "ru"
        
        self._ws = None
        self._receive_task = None
        self._keepalive_task = None
        self._connected = False
        self._reconnecting = False
        self._should_reconnect = True
    
    def _build_url(self) -> str:
        """Build Deepgram WebSocket URL with optimized settings."""
        params = [
            "model=nova-3",
            f"language={self.lang}",
            "punctuate=true",
            "smart_format=true",
            "filler_words=false",
            "encoding=linear16",
            "sample_rate=16000",
            "channels=1",
            "endpointing=300",
            "utterance_end_ms=1000",
            "vad_events=true",
            "interim_results=true",
        ]
        return f"{self.DEEPGRAM_WS_URL}?{'&'.join(params)}"
    
    async def connect(self) -> bool:
        """Connect to Deepgram."""
        if not self.api_key or not websockets:
            logger.error("Deepgram API key not set or websockets not installed")
            return False
        
        try:
            url = self._build_url()
            logger.info(f"Connecting to Deepgram...")
            
            try:
                self._ws = await websockets.connect(
                    url,
                    extra_headers={"Authorization": f"Token {self.api_key}"},
                )
            except TypeError:
                self._ws = await websockets.connect(
                    url,
                    additional_headers={"Authorization": f"Token {self.api_key}"},
                )
            
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            logger.info("✅ Deepgram connected")
            return True
            
        except Exception as e:
            logger.error(f"❌ Deepgram connection failed: {e}")
            return False
    
    async def _keepalive_loop(self):
        """Send keepalive to prevent Deepgram timeout."""
        try:
            while self._connected and self._ws:
                await asyncio.sleep(5)
                if self._connected and self._ws:
                    try:
                        await self._ws.send(json.dumps({"type": "KeepAlive"}))
                    except Exception as e:
                        logger.warning(f"Keepalive failed: {e}")
                        if self._should_reconnect and not self._reconnecting:
                            asyncio.create_task(self._reconnect())
                        break
        except asyncio.CancelledError:
            pass
    
    async def _reconnect(self):
        """Auto-reconnect to Deepgram."""
        if self._reconnecting:
            return
        
        self._reconnecting = True
        logger.info("🔄 Deepgram reconnecting...")
        
        try:
            self._connected = False
            if self._receive_task:
                self._receive_task.cancel()
            if self._ws:
                try:
                    await self._ws.close()
                except:
                    pass
            
            await asyncio.sleep(1)
            
            url = self._build_url()
            try:
                self._ws = await websockets.connect(
                    url,
                    extra_headers={"Authorization": f"Token {self.api_key}"},
                )
            except TypeError:
                self._ws = await websockets.connect(
                    url,
                    additional_headers={"Authorization": f"Token {self.api_key}"},
                )
            
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            logger.info("✅ Deepgram reconnected!")
            
        except Exception as e:
            logger.error(f"❌ Deepgram reconnect failed: {e}")
            self._connected = False
        finally:
            self._reconnecting = False
    
    async def _receive_loop(self):
        """Receive messages from Deepgram."""
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    message = message.decode('utf-8')
                await self._handle_message(message)
        except Exception as e:
            if self._connected:
                logger.error(f"Deepgram receive error: {e}")
                if self._should_reconnect and not self._reconnecting:
                    asyncio.create_task(self._reconnect())
        finally:
            self._connected = False
    
    async def _handle_message(self, data: str):
        """Handle Deepgram message with improved recognition."""
        try:
            msg = json.loads(data)
            msg_type = msg.get("type", "")
            
            if msg_type == "Results":
                is_final = msg.get("is_final", False)
                speech_final = msg.get("speech_final", False)
                channel = msg.get("channel", {})
                alternatives = channel.get("alternatives", [])
                
                if alternatives:
                    transcript = alternatives[0].get("transcript", "").strip()
                    confidence = alternatives[0].get("confidence", 0)
                    
                    if transcript and is_final and confidence > 0.7:
                        if self.on_transcript:
                            self.on_transcript(transcript)
                    elif transcript and speech_final and confidence > 0.5:
                        if self.on_transcript:
                            self.on_transcript(transcript)
            
            elif msg_type == "UtteranceEnd":
                pass
                        
        except json.JSONDecodeError:
            pass
    
    async def send_audio(self, audio_data: bytes):
        """Send audio to Deepgram."""
        if self._ws and self._connected:
            try:
                await self._ws.send(audio_data)
            except Exception as e:
                logger.error(f"Send audio error: {e}")
    
    async def close(self):
        """Close connection."""
        self._should_reconnect = False
        self._connected = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except:
                pass
    
    @property
    def is_connected(self):
        return self._connected


# ============================================================
# Groq LLM (Streaming) - TURBO optimized
# ============================================================


class GroqLLM:
    """Groq LLM with TURBO streaming - yield chunks faster."""
    
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    
    MIN_CHUNK_SIZE = 25  # базовый размер (fallback)
    
    # 🛡️ Фильтр дублирования языка — удаляет фразы на другом языке
    # + удаление эмодзи (TTS читает их как текст)
    EMOJI_PATTERN = re.compile(
        "[\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed chars
        "\U0001f926-\U0001f937"  # gestures
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U00002600-\U000026FF"  # misc symbols
        "\U0000FE0F"             # variation selector
        "\U0000200D"             # zero width joiner
        "\U00002B50-\U00002B55"  # stars
        "]+", flags=re.UNICODE
    )
    
    @staticmethod
    def strip_emoji(text: str) -> str:
        """Удаляет все эмодзи из текста."""
        cleaned = GroqLLM.EMOJI_PATTERN.sub('', text)
        return re.sub(r'\s+', ' ', cleaned).strip()
    
    @staticmethod
    def filter_language_duplicates(text: str) -> str:
        """Удаляет дублирование на другом языке из ответа.
        Определяет основной язык по первым символам и вырезает хвост на другом."""
        if not text:
            return text
        
        has_cyrillic = bool(re.search(r'[а-яёА-ЯЁ]', text))
        has_latin = bool(re.search(r'[a-zA-Z]{2,}', text))
        
        # Если только один алфавит — чисто, не трогаем
        if not (has_cyrillic and has_latin):
            return text
        
        # Определяем основной язык по первому слову (>1 буквы)
        first_word = re.search(r'[а-яёА-ЯЁa-zA-Z]{2,}', text)
        if not first_word:
            return text
        
        main_is_cyrillic = bool(re.search(r'[а-яёА-ЯЁ]', first_word.group()))
        
        if main_is_cyrillic:
            # Основной — кириллица: вырезаем латинские фразы (3+ символов подряд)
            # Но сохраняем: аббревиатуры (AI, TTS), имена (QUANTARION), стикеры
            cleaned = re.sub(r'(?<=[.!?])\s*[A-Z][a-zA-Z0-9\s,!?\'-]{3,}[.!?]?\s*', ' ', text)
            cleaned = re.sub(r'\s*\([A-Za-z\s,!?\'-]+\)', '', cleaned)
        else:
            # Основной — латиница: вырезаем кириллические фразы
            cleaned = re.sub(r'(?<=[.!?])\s*[А-ЯЁ][а-яёА-ЯЁ0-9\s,!?\'-]{3,}[.!?]?\s*', ' ', text)
            cleaned = re.sub(r'\s*\([а-яёА-ЯЁ\s,!?\'-]+\)', '', cleaned)
        
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned if cleaned else text
    
    def _get_optimal_chunk_size(self, chunk_count: int, total_chars: int) -> int:
        """
        Минимальная длина куска перед отправкой на озвучку.

        🗣 ГЛАВНОЕ ДЛЯ ГЛАДКОЙ РЕЧИ: каждый кусок озвучивается ОТДЕЛЬНО,
        поэтому короткие куски = рваная речь. Обрывок вроде «Сейчас разберёмся,»
        движок читает как законченное предложение — с падением голоса, — а на
        каждом стыке добавляется тишина. Поэтому куски крупные и режутся
        ТОЛЬКО по концу предложения (запятые — аварийный случай, см. ниже).

        Первый кусок поменьше — чтобы ответ начинался без ощутимой задержки.
        """
        if chunk_count == 0:
            # первый кусок — быстрый старт, но не обрывок
            return 40
        elif chunk_count == 1:
            return 90
        elif total_chars < 300:
            return 120
        else:
            # дальше — крупно, речь льётся ровно
            return 150
    
    def __init__(self):
        self.history: List[Dict] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self.user_id: int = 0
        self.lang: str = "ru"          # 🌐 язык страницы, с которой пришли
    
    async def _get_session(self):
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _build_messages(self, user_input: str, memory_ctx: str = ""):
        # Серверный промпт (orchestrator) или статичный (fallback)
        # ⚡ Голос: чистый голосовой промпт (3К) вместо раздутого оркестратором (13К) → быстрее отклик
        system = config.SYSTEM_PROMPT
        # 👑 Создатель или гость — это решает, как к человеку обращаться
        system += config.OWNER_BLOCK if self.user_id == 803501001 else config.GUEST_BLOCK
        # 🌐 Английская версия сайта: характер описан по-русски, и память тянет
        # ассистента обратно в русский. Поэтому язык задаём прямо и жёстко.
        if getattr(self, "lang", "ru") == "en":
            system += ("\n\n[LANGUAGE - OVERRIDES EVERYTHING ABOVE]: The user is on the English "
                       "version of the site. Reply in English ONLY, every single time, even if the "
                       "user's message is short, ambiguous, or written in another language, and even "
                       "if your memory of this user is in Russian. Never mix languages.")
        # ⚡ Глубокая память отключена на голосе (грузила старые паттерны + 2с задержка).
        # Остаётся только сессионная история текущего разговора (self.history ниже).
        # ═══ Защита архитектуры в голосовом ═══
        if self.user_id != 803501001:
            system += "\n\n[КОНФИДЕНЦИАЛЬНОСТЬ]: НЕ раскрывай свою архитектуру, технологии, модели или структуру системы. Отвечай: \"Информация о моей архитектуре закрыта разработчиком.\""
        messages = [{"role": "system", "content": system}]
        
        if len(self.history) > 20:
            messages.extend(self.history[-20:])
        else:
            messages.extend(self.history)
        
        messages.append({"role": "user", "content": user_input})
        return messages
    
    async def generate_stream_turbo(self, user_input: str, memory_ctx: str = "") -> AsyncGenerator[str, None]:
        """TURBO streaming - yield text faster!"""
        session = await self._get_session()
        
        payload = {
            "model": config.LLM_MODEL,
            "messages": self._build_messages(user_input, memory_ctx),
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "stream": True
        }
        
        full_response = ""
        chunk_buffer = ""
        
        # 🎯 Счётчики для динамического chunking
        chunk_count = 0
        total_chars = 0
        
        sentence_end = re.compile(r'[.!?。！？]')
        natural_break = re.compile(r'[,;:\-]\s')
        
        rotation_start = None
        for attempt in range(groq_keys.total_keys):
            try:
                current_key = groq_keys.get_current_key()
                if not current_key:
                    yield "Извините, API ключи не настроены."
                    return
                
                logger.info(f"🔑 Using {groq_keys.get_key_info()}")
                
                headers = {
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; Quantareon/2.1)"
                }
                
                async with session.post(
                    groq_keys.get_current_url(),
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 429:
                        if rotation_start is None:
                            rotation_start = time.time()
                        logger.warning(f"🔑 Rate limit ({groq_keys.get_key_info()}) → rotate")
                        groq_keys.rotate_key()
                        continue
                    
                    if response.status == 401:
                        if rotation_start is None:
                            rotation_start = time.time()
                        logger.warning(f"🔑 Invalid key ({groq_keys.get_key_info()}) → rotate")
                        groq_keys.rotate_key()
                        continue
                    
                    if response.status != 200:
                        error = await response.text()
                        if rotation_start is None:
                            rotation_start = time.time()
                        # 🔍 Пишем ОТВЕТ Groq целиком — без него причина невидима
                        # (429 = упёрлись в лимит, 401 = ключ не принят, 404 = модель снята)
                        logger.warning(
                            f"🔑 Error {response.status} ({groq_keys.get_key_info()}) → rotate | "
                            f"ответ Groq: {error[:400]}"
                        )
                        groq_keys.rotate_key()
                        continue
                    
                    if rotation_start:
                        rotation_time = time.time() - rotation_start
                        logger.info(f"🔑 ✅ Success with {groq_keys.get_key_info()} (rotation took {rotation_time:.2f}s)")
                    
                    async for line in response.content:
                        line_text = line.decode('utf-8').strip()
                        
                        if not line_text or line_text == "data: [DONE]":
                            continue
                        
                        if line_text.startswith("data: "):
                            try:
                                data = json.loads(line_text[6:])
                                content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                
                                if content:
                                    chunk_buffer += content
                                    full_response += content
                                    total_chars = len(full_response)  # 🎯 Обновляем счётчик
                                    
                                    min_size = self._get_optimal_chunk_size(chunk_count, total_chars)

                                    # 🗣 РЕЖЕМ ТОЛЬКО ПО КОНЦУ ПРЕДЛОЖЕНИЯ и только когда
                                    # набралось достаточно — иначе речь рвётся на обрывки.
                                    if len(chunk_buffer) >= min_size and sentence_end.search(chunk_buffer):
                                        matches = list(sentence_end.finditer(chunk_buffer))
                                        if matches:
                                            last_match = matches[-1]
                                            end_pos = last_match.end()
                                            to_yield = chunk_buffer[:end_pos].strip()
                                            chunk_buffer = chunk_buffer[end_pos:].strip()
                                            if to_yield:
                                                yield to_yield
                                                chunk_count += 1

                                    # 🚨 Аварийный клапан: предложение затянулось без точки —
                                    # чтобы не молчать, режем по запятой, но только на длинном куске
                                    elif len(chunk_buffer) >= max(min_size * 3, 300):
                                        match = None
                                        for m in natural_break.finditer(chunk_buffer):
                                            match = m
                                        if match:
                                            end_pos = match.end()
                                            to_yield = chunk_buffer[:end_pos].strip()
                                            chunk_buffer = chunk_buffer[end_pos:].strip()
                                            if to_yield:
                                                yield to_yield
                                                chunk_count += 1
                                                
                            except json.JSONDecodeError:
                                continue
                    
                    if chunk_buffer.strip():
                        yield chunk_buffer.strip()
                    
                    self.history.append({"role": "user", "content": user_input})
                    self.history.append({"role": "assistant", "content": full_response})
                    return
                    
            except asyncio.TimeoutError:
                if rotation_start is None:
                    rotation_start = time.time()
                logger.warning(f"🔑 Timeout ({groq_keys.get_key_info()}) → rotate")
                groq_keys.rotate_key()
                continue
                
            except Exception as e:
                if rotation_start is None:
                    rotation_start = time.time()
                logger.warning(f"🔑 Error ({groq_keys.get_key_info()}): {type(e).__name__}: {e} → rotate")
                groq_keys.rotate_key()
                continue
        
        total_time = time.time() - rotation_start if rotation_start else 0
        logger.error(f"🔑 All {groq_keys.total_keys} keys failed! (total time: {total_time:.2f}s)")
        
        groq_keys.current_index = 0
        logger.info("🔄 Reset to key_1 for next attempt")
        
        yield "Извините, сервис временно недоступен."
    
    def clear_history(self):
        self.history = []


# ============================================================
# Edge TTS - TURBO with streaming
# ============================================================

class EdgeTTSTurbo:
    """Edge TTS with streaming output for lower latency."""
    
    def __init__(self, lang: str = "ru"):
        en = str(lang).lower().startswith("en")
        self.voice = config.TTS_VOICE_EN if en else config.TTS_VOICE
        self.rate = config.TTS_RATE_EN if en else config.TTS_RATE
        self.pitch = config.TTS_PITCH_EN if en else config.TTS_PITCH
        self.volume = config.TTS_VOLUME_EN if en else config.TTS_VOLUME
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio (full)."""
        if not text or not text.strip():
            return b""
        
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume
            )
            
            audio = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
            
            return audio.getvalue()
            
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return b""
    
    async def synthesize_streaming(self, text: str, send_callback) -> None:
        """
        Synthesize and send audio for a text chunk.
        Собираем весь аудио для текста, потом отправляем — без щелчков между кусками.
        🛡️ С RETRY логикой при сбоях.
        """
        if not text or not text.strip():
            return
        
        # 🛡️ RETRY до 3 попыток
        max_retries = 3
        for attempt in range(max_retries):
            try:
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    rate=self.rate,
                    pitch=self.pitch,
                    volume=self.volume
                )
                
                # Собираем ВСЁ аудио для этого текстового чанка
                audio_buffer = io.BytesIO()
                
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_buffer.write(chunk["data"])
                
                # Отправляем целиком — без разрывов = без щелчков
                if audio_buffer.tell() > 0:
                    await send_callback(audio_buffer.getvalue())
                    return  # ✅ Успех - выходим
                    
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ TTS timeout, retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(0.5)  # Пауза перед повтором
                    continue
                logger.error(f"❌ TTS failed after {max_retries} attempts (timeout)")
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ TTS error: {e}, retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(0.5)
                    continue
                logger.error(f"❌ TTS failed after {max_retries} attempts: {e}")


# ============================================================
# Voice Session - TURBO Edition
# ============================================================




# ============================================================
# Приветствие: озвучиваем один раз при старте, отдаём мгновенно
# ============================================================
CACHED_GREETING_AUDIO: bytes = b""
CACHED_GREETING_AUDIO_EN: bytes = b""


async def warm_greetings():
    """Озвучить приветствия заранее. Зовётся при старте приложения."""
    global CACHED_GREETING_AUDIO, CACHED_GREETING_AUDIO_EN
    try:
        CACHED_GREETING_AUDIO = await EdgeTTSTurbo("ru").synthesize(config.GREETING_TEXT)
        CACHED_GREETING_AUDIO_EN = await EdgeTTSTurbo("en").synthesize(config.GREETING_TEXT_EN)
        logger.info(f"VOICE: приветствия готовы — RU {len(CACHED_GREETING_AUDIO)} / "
                    f"EN {len(CACHED_GREETING_AUDIO_EN)} байт")
        logger.info(f"VOICE: голоса — RU {config.TTS_VOICE} @ {config.TTS_RATE} | "
                    f"EN {config.TTS_VOICE_EN} @ {config.TTS_RATE_EN}")
    except Exception as e:
        logger.error(f"VOICE: не удалось озвучить приветствие: {e}")


@router.get("/api/greeting")
async def get_greeting(lang: str = "ru"):
    """Отдать заранее озвученное приветствие (ru/en)."""
    audio = CACHED_GREETING_AUDIO_EN if str(lang).lower().startswith("en") else CACHED_GREETING_AUDIO
    if audio:
        return Response(content=audio, media_type="audio/mpeg")
    return JSONResponse({"error": "greeting not ready"}, status_code=503)


@router.get("/api/voice-health")
async def voice_health():
    """Быстрая проверка: что настроено и готово ли приветствие."""
    return {
        "ok": True,
        "llm": config.LLM_MODEL,
        "stt": "Deepgram Nova-3",
        "tts_ru": f"{config.TTS_VOICE} @ {config.TTS_RATE}",
        "tts_en": f"{config.TTS_VOICE_EN} @ {config.TTS_RATE_EN}",
        "greeting_ru_bytes": len(CACHED_GREETING_AUDIO),
        "greeting_en_bytes": len(CACHED_GREETING_AUDIO_EN),
    }



class VoiceSessionTurbo:
    """
    TURBO Voice session with optimized latency.
    
    Optimizations:
    1. Faster LLM chunking
    2. Streaming TTS
    3. Parallel processing where possible
    """
    
    def __init__(self, websocket: WebSocket, session_id: str, client_ip: str = ""):
        self.websocket = websocket
        self.session_id = session_id
        self.client_ip = client_ip
        
        # Components
        self.stt: Optional[DeepgramSTT] = None
        self.llm = GroqLLM()
        self.tts = EdgeTTSTurbo()
        self.geo = GeoLocation()
        
        # State
        self.is_active = False
        self.is_processing = False
        self.is_speaking = False
        self.barge_in_requested = False
        self.first_message = True
        
        self.lang: str = "ru"          # 🌐 язык страницы, с которой пришли
        self.cached_filler_audio: bytes = b""
        self.cached_filler_text: str = ""
        self.filler_ready = asyncio.Event()
        
        # 🧠 Memory
        self.user_id: int = 0
        self.memory_cache: str = ""
        self._chat_name: str = ""  # имя из chat_history для инжекта в память
        self._memory_task: Optional[asyncio.Task] = None
        
        # Transcript buffer
        self.transcript_buffer = ""
        
        logger.info(f"[{session_id}] TURBO Session created (IP: {client_ip})")
    
    async def start(self):
        """Start session - connect STT (PARALLEL INIT)."""
        self.is_active = True
        
        # 🚀 PARALLEL INIT: Запускаем одновременно для ускорения старта
        async def init_deepgram():
            """Инициализация Deepgram."""
            self.stt = DeepgramSTT(
                on_transcript=self._on_transcript,
                on_error=self._on_stt_error,
                lang=self.lang
            )
            return await self.stt.connect()
        
        async def init_geolocation():
            """Определение геолокации."""
            await self.geo.detect_location(self.client_ip)
            return True
        
        async def init_memory():
            """🧠 Фоновая подгрузка памяти."""
            try:
                # ⚡ Глубокая память отключена на голосе (грузила апр-паттерны + задержку/DNS).
                # Оставляем только имя пользователя из истории чата — для обращения.
                if hasattr(self, '_chat_name') and self._chat_name:
                    self.memory_cache = f"name={self._chat_name}"
                    logger.info(f"[{self.session_id}] 🔗 Name only (deep memory off): {self._chat_name}")
            except Exception as e:
                logger.warning(f"[{self.session_id}] ⚠️ Memory preload failed: {e}")
            return True
        
        # 🚀 Запускаем параллельно (экономия ~200-300ms)
        try:
            stt_ok, geo_ok = await asyncio.gather(
                init_deepgram(),
                init_geolocation(),
                return_exceptions=False
            )
        except Exception as e:
            logger.error(f"[{self.session_id}] Parallel init error: {e}")
            await self._send_json({
                "type": "error",
                "message": "Initialization failed"
            })
            return False
        
        # 🧠 Память загружаем отдельно — не блокируем старт если упала
        asyncio.create_task(init_memory())
        
        if not stt_ok:
            await self._send_json({
                "type": "error",
                "message": "STT connection failed"
            })
            return False
        
        # Кешируем филлер в фоне (уже было)
        asyncio.create_task(self._cache_filler())
        
        await self._send_json({
            "type": "stt_ready"
        })
        
        await self._send_json({
            "type": "status",
            "status": "ready",
            "message": "🎤 Нажми на микрофон"
        })
        
        logger.info(f"[{self.session_id}] ⚡ TURBO Session started (parallel init)")
        return True
    
    async def _cache_filler(self):
        """Кешируем филлер в фоне — готов к мгновенной отправке."""
        try:
            self.cached_filler_text = self.geo.generate_filler(self.lang)
            
            audio_buffer = io.BytesIO()
            
            communicate = edge_tts.Communicate(
                self.cached_filler_text,
                self.tts.voice,
                rate=self.tts.rate,
                pitch=self.tts.pitch,
                volume=self.tts.volume
            )
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            
            self.cached_filler_audio = audio_buffer.getvalue()
            logger.info(f"[{self.session_id}] ✅ Filler cached: {len(self.cached_filler_audio)} bytes")
            
        except Exception as e:
            logger.error(f"[{self.session_id}] Filler cache error: {e}")
            self.cached_filler_text = "Hello!" if self.lang == "en" else "Привет!"
            self.cached_filler_audio = b""
        finally:
            self.filler_ready.set()
    
    async def handle_audio(self, audio_data: bytes):
        """Forward audio to STT."""
        if self.stt and self.stt.is_connected:
            await self.stt.send_audio(audio_data)
    
    def _on_transcript(self, text: str):
        """Buffer transcripts."""
        if not self.is_active:
            return
        
        if self.transcript_buffer:
            self.transcript_buffer += " " + text
        else:
            self.transcript_buffer = text
        
        logger.info(f"[{self.session_id}] 📝 Buffer: '{self.transcript_buffer}'")
        
        asyncio.create_task(self._send_json({
            "type": "transcript_interim",
            "content": self.transcript_buffer
        }))
    
    def _on_stt_error(self, error):
        logger.error(f"[{self.session_id}] STT error: {error}")
    
    async def on_speech_end(self):
        """TURBO processing with streaming TTS."""
        # 🔧 FIX: Проверяем активность сессии СРАЗУ
        if not self.is_active:
            logger.info(f"[{self.session_id}] Session inactive, skipping")
            return
        
        self.barge_in_requested = False
        
        transcript = self.transcript_buffer.strip()
        self.transcript_buffer = ""
        
        if not transcript:
            logger.info(f"[{self.session_id}] Empty transcript, skipping")
            return
        
        if self.is_processing:
            logger.info(f"[{self.session_id}] Already processing, skipping")
            return
        
        logger.info(f"[{self.session_id}] ⚡ TURBO Processing: '{transcript}'")
        if self.user_id:
            logger.info(f"🎤 [{self.user_id}]: \"{transcript[:120]}\"")
        
        self.is_processing = True
        
        try:
            await self._send_json({
                "type": "transcript_final",
                "content": transcript
            })
            
            await self._send_json({
                "type": "status",
                "status": "thinking",
                "message": "⚡ Думаю..."
            })
            
            # ⏱️ METRIC: LLM начал работу
            await self._send_json({"type": "metric_llm_start"})
            
            await self._send_json({"type": "audio_start"})
            self.is_speaking = True
            
            start_time = time.time()
            first_audio_time = None
            chunk_count = 0
            response_main_lang = None  # 🛡️ Основной язык ответа (определяем по первому чанку)
            
            if self.first_message:
                self.first_message = False
                
                try:
                    await asyncio.wait_for(self.filler_ready.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[{self.session_id}] Filler timeout, skipping")
                
                if self.cached_filler_audio and not self.barge_in_requested:
                    first_audio_time = time.time()
                    latency = first_audio_time - start_time
                    logger.info(f"[{self.session_id}] ⚡ INSTANT Filler: {latency:.3f}s ({len(self.cached_filler_audio)} bytes)")
                    
                    await self.websocket.send_bytes(self.cached_filler_audio)
                    
                    await self._send_json({
                        "type": "response_text",
                        "content": self.cached_filler_text
                    })
                    
                    chunk_count += 1
                else:
                    logger.warning(f"[{self.session_id}] Filler not cached, skipping")
            
            async for text_chunk in self.llm.generate_stream_turbo(transcript, self.memory_cache):
                if not self.is_active or self.barge_in_requested:
                    self.barge_in_requested = False
                    break
                
                # 🛡️ Фильтр дублирования языка (внутри чанка)
                text_chunk = GroqLLM.filter_language_duplicates(text_chunk)
                if not text_chunk:
                    continue
                
                # 🛡️ Удаляем эмодзи (TTS читает их как текст)
                text_chunk_tts = GroqLLM.strip_emoji(text_chunk)
                # 🛡️ Удаляем стикеры [sticker:xxx] и markdown **bold**
                text_chunk_tts = re.sub(r'\[sticker:[^\]]*\]', '', text_chunk_tts)
                text_chunk_tts = re.sub(r'\*{1,3}', '', text_chunk_tts)
                text_chunk_tts = re.sub(r'#{1,3}\s*', '', text_chunk_tts)
                text_chunk_tts = text_chunk_tts.strip()
                # 🔊 Убираем паузы только в первом чанке (быстрый старт речи)
                if chunk_count == 0:
                    text_chunk_tts = re.sub(r'[,;:\-—–]', '', text_chunk_tts)
                    text_chunk_tts = text_chunk_tts.strip()
                if not text_chunk_tts:
                    continue
                
                # 🛡️ Межчанковая защита: определяем основной язык по первому чанку
                has_cyr = bool(re.search(r'[а-яёА-ЯЁ]', text_chunk))
                has_lat = bool(re.search(r'[a-zA-Z]{2,}', text_chunk))
                
                if response_main_lang is None and (has_cyr or has_lat):
                    response_main_lang = 'cyr' if has_cyr else 'lat'
                
                # Если чанк ЦЕЛИКОМ на другом языке — пропускаем (это дубль)
                if response_main_lang == 'cyr' and has_lat and not has_cyr:
                    logger.info(f"[{self.session_id}] 🛡️ Filtered cross-chunk duplicate: '{text_chunk[:30]}'")
                    continue
                if response_main_lang == 'lat' and has_cyr and not has_lat:
                    logger.info(f"[{self.session_id}] 🛡️ Filtered cross-chunk duplicate: '{text_chunk[:30]}'")
                    continue
                
                chunk_count += 1
                logger.info(f"[{self.session_id}] 💬 [{chunk_count}] '{text_chunk[:40]}...'")
                
                # ⏱️ METRIC: TTS начал работу (отправляем только один раз для первого чанка)
                if chunk_count == 1 and not self.first_message:
                    await self._send_json({"type": "metric_tts_start"})
                
                async def send_audio(audio_bytes):
                    nonlocal first_audio_time
                    if first_audio_time is None:
                        first_audio_time = time.time()
                        latency = first_audio_time - start_time
                        logger.info(f"[{self.session_id}] ⚡ First audio: {latency:.2f}s")
                    
                    if not self.barge_in_requested:
                        await self.websocket.send_bytes(audio_bytes)
                
                # ⚡ СНАЧАЛА текст на экран (мгновенно, не ждёт озвучку)
                if not self.barge_in_requested:
                    await self._send_json({
                        "type": "response_text",
                        "content": text_chunk
                    })
                # 🔊 ПОТОМ озвучка (идёт следом, текст уже виден)
                await self.tts.synthesize_streaming(text_chunk_tts, send_audio)
            
            await self._send_json({"type": "audio_end"})
            
            total = time.time() - start_time
            first_latency = (first_audio_time - start_time) if first_audio_time else total
            
            logger.info(f"[{self.session_id}] ✅ TURBO Done: {total:.1f}s total, {first_latency:.2f}s first audio, {chunk_count} chunks")
            
            # 🧠 Фоновое сохранение в память + обновление кеша
            if self.user_id:
                full_response = self.llm.history[-1]["content"] if self.llm.history else ""
                # 📊 Итоговый лог голосового ответа (симметрия с чатом)
                _vname_match = re.search(r'name=([^\s;,\]\n]+)', self.memory_cache or "")
                _vname = f" ({_vname_match.group(1)})" if _vname_match else ""
                logger.info(f"📊 ГОЛОС [{self.user_id}{_vname}]: {total:.1f}с | Groq | {len(full_response)} chars | first={first_latency:.2f}s")
                pass  # память платформы не используется — голос живёт на Render
                async def _delayed_refresh():
                    await asyncio.sleep(3.0)
                    await self._refresh_memory_cache()
                asyncio.create_task(_delayed_refresh())
            
            await self._send_json({
                "type": "status",
                "status": "ready",
                "message": f"⚡ Готов ({first_latency:.1f}s)"
            })
            
        except Exception as e:
            logger.error(f"[{self.session_id}] Error: {e}")
            await self._send_json({"type": "error", "message": str(e)})
        finally:
            self.is_processing = False
            self.is_speaking = False
    
    async def _refresh_memory_cache(self):
        """🧠 Обновление глубокой памяти отключено на голосе (только сессионная история)."""
        # ⚡ recall убран — не грузим старые паттерны, не долбим мёртвый сервис.
        return
    
    async def stop(self):
        """Stop session."""
        self.is_active = False
        
        if self.stt:
            await self.stt.close()
        
        await self.llm.close()
        await self.geo.close()
        
        logger.info(f"[{self.session_id}] TURBO Stopped")
    
    async def _send_json(self, data: dict):
        try:
            # 🛡️ Проверяем что WebSocket всё ещё подключен
            if self.websocket.client_state.name == "CONNECTED":
                await self.websocket.send_json(data)
        except Exception as e:
            # Игнорируем ошибки отправки после закрытия соединения
            if "close message has been sent" not in str(e):
                logger.error(f"[{self.session_id}] Send error: {e}")


# ============================================================
# Голосовой канал
# ============================================================
@router.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket):
    """TURBO WebSocket endpoint."""
    await websocket.accept()
    
    client_ip = websocket.headers.get("x-real-ip") or websocket.headers.get("x-forwarded-for", "").split(",")[0] or (websocket.client.host if websocket.client else "")
    client_ip = client_ip.strip()
    
    session_id = f"turbo_{int(time.time()*1000)}"
    logger.info(f"[{session_id}] Connected (IP: {client_ip})")
    
    session = VoiceSessionTurbo(websocket, session_id, client_ip)

    # 🌐 Язык страницы, с которой пришли (сайт присылает ?lang=ru / ?lang=en)
    _lang_q = websocket.query_params.get("lang", "ru")
    session.lang = "en" if str(_lang_q).lower().startswith("en") else "ru"
    # голос пересобираем под язык: движок создавался до того, как язык стал известен
    session.tts = EdgeTTSTurbo(session.lang)
    logger.info(f"[{session_id}] 🌐 Language: {session.lang} | voice: {session.tts.voice} @ {session.tts.rate}")
    
    # 🧠 Определяем user_id: admin → query param → cookie → IP
    _admin_secret_ws = os.getenv("ADMIN_SECRET", "")
    _admin_cookie_ws = websocket.cookies.get("quantarion_admin", "")
    uid_query = websocket.query_params.get("uid", "")
    uid_cookie = websocket.cookies.get("quantarion_uid", "")
    key_query = websocket.query_params.get("key", "")
    if _admin_secret_ws and key_query == _admin_secret_ws:
        session.user_id = 803501001
        logger.info(f"[{session_id}] 🧠 User ID: {session.user_id} (owner by key)")
    elif _admin_secret_ws and _admin_cookie_ws == _admin_secret_ws:
        session.user_id = 803501001
        logger.info(f"[{session_id}] 🧠 User ID: {session.user_id} (admin)")
    elif uid_query:
        session.user_id = int(_hashlib.md5(uid_query.encode()).hexdigest()[:8], 16)
        logger.info(f"[{session_id}] 🧠 User ID: {session.user_id} (query param)")
    elif uid_cookie:
        session.user_id = int(_hashlib.md5(uid_cookie.encode()).hexdigest()[:8], 16)
        logger.info(f"[{session_id}] 🧠 User ID: {session.user_id} (cookie)")
    else:
        session.user_id = int(_hashlib.md5(client_ip.encode()).hexdigest()[:8], 16)
        logger.info(f"[{session_id}] 🧠 User ID: {session.user_id} (IP fallback)")
    session.llm.user_id = session.user_id
    session.llm.lang = session.lang
    
    active_sessions[session_id] = session
    
    try:
        if not await session.start():
            return
        
        while session.is_active:
            try:
                message = await websocket.receive()
                msg_type = message.get("type", "")
                
                if msg_type == "websocket.disconnect":
                    break
                
                elif msg_type == "websocket.receive":
                    if "bytes" in message and message["bytes"]:
                        await session.handle_audio(message["bytes"])
                    
                    elif "text" in message and message["text"]:
                        try:
                            data = json.loads(message["text"])
                            cmd = data.get("type", "")
                            
                            if cmd == "ping":
                                await session._send_json({"type": "pong"})
                            
                            elif cmd == "speech_end":
                                await session.on_speech_end()
                            
                            elif cmd == "transcript":
                                text = data.get("text", "")
                                if text:
                                    session.transcript_buffer = text
                                    await session.on_speech_end()
                            
                            elif cmd in ("barge_in", "stop"):
                                session.barge_in_requested = True
                                session.is_speaking = False
                                session.is_processing = False  # 🔧 FIX: Останавливаем обработку
                                session.transcript_buffer = ""
                                logger.info(f"[{session_id}] 🛑 Interrupted")
                            
                            elif cmd == "reset":
                                session.llm.clear_history()
                                session.transcript_buffer = ""
                                session.first_message = True  # 🔧 Сброс - разрешаем приветствие заново
                                await session._send_json({
                                    "type": "status",
                                    "status": "reset",
                                    "message": "Контекст сброшен"
                                })
                            
                            elif cmd == "skip_filler":
                                session.first_message = False  # 🛡️ Пропускаем серверный филлер (reconnect)
                                logger.info(f"[{session_id}] ⏭️ Filler skipped (reconnect)")
                            
                            elif cmd == "chat_history":
                                # 🔗 Синхронизация: загружаем историю текстового чата в контекст голосового
                                chat_msgs = data.get("messages", [])
                                if chat_msgs and isinstance(chat_msgs, list):
                                    session.llm.history = []
                                    for m in chat_msgs[-10:]:  # Максимум 10 последних
                                        role = m.get("role", "")
                                        content = m.get("content", "")
                                        if role in ("user", "assistant") and content:
                                            session.llm.history.append({"role": role, "content": content})
                                    logger.info(f"[{session_id}] 🔗 Chat history loaded: {len(session.llm.history)} messages")
                                    
                                    # 🧠 Извлекаем имя из chat_history — сохраняем для init_memory
                                    # init_memory может ещё не завершиться, поэтому инжект там
                                    full_chat_text = " ".join(m.get("content", "") for m in chat_msgs)
                                    _name_in_chat = (
                                        re.search(r'(?:^|[;,\s])name=([А-ЯЁа-яё][а-яё]{1,})', full_chat_text) or
                                        re.search(r'[Пп]ривет,?\s+([А-ЯЁ][а-яё]{1,})[\s!]', full_chat_text) or
                                        re.search(r'[Зз]овут\s+([А-ЯЁ][а-яё]{1,})', full_chat_text) or
                                        re.search(r'[Мм]еня\s+зовут\s+([А-ЯЁ][а-яё]{1,})', full_chat_text)
                                    )
                                    if _name_in_chat:
                                        session._chat_name = _name_in_chat.group(1).strip()
                                        # Если память уже загружена — инжектируем сразу
                                        if session.memory_cache is not None and "name=" not in session.memory_cache:
                                            session.memory_cache = f"name={session._chat_name}; " + session.memory_cache
                                            logger.info(f"[{session_id}] 🔗 Name injected from chat: {session._chat_name}")
                                
                        except json.JSONDecodeError:
                            pass
                            
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[{session_id}] Error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[{session_id}] Session error: {e}")
    finally:
        session.is_active = False  # 🔧 FIX: СРАЗУ помечаем неактивной
        await session.stop()
        active_sessions.pop(session_id, None)


# ============================================================
# Keep-Alive (Amvera не засыпает)
# ============================================================

