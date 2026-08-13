"""
ЗНАНИЯ ГОЛОСОВОГО КВАНТАРЕОНА О САЙТЕ
======================================
Три слоя, чтобы не грузить всё разом:

  1. КАРТА САЙТА (karta.txt) — всегда в наставлении. Из неё помощник знает,
     какие разделы есть, о чём каждый и где лежит. ~3 КБ, дёшево.

  2. ЗНАНИЕ ПО ТЕМЕ — один файл на раздел. Подтягивается только тот, о чём
     спросили. Тема «липкая»: раз зашла, держится в разговоре, пока человек
     не свернёт на другое — иначе на «а поподробнее?» помощник терял бы нить.

  3. ГЛУБИНА — полный текст части эссе (part1/2/3.txt, по 36-43 КБ).
     Подкладывается, только когда разговор явно ушёл вглубь книги.

Добавить новый раздел = положить файл в knowledge/ и дописать строку в TOPICS.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "knowledge"


# ============================================================
# Темы: файл знаний + слова, по которым его узнаём
# ============================================================
TOPICS: Dict[str, Dict] = {
    "esse": {
        "file": "esse.txt",
        "words": [
            "эссе", "книг", "свет и код", "light and code", "текст", "глав",
            "клетк", "сознани", "фрактал", "голограмм", "инсайт",
            "прана", "светонос", "днк", "кундалини", "зеркал", "код мира",
            "микрокосм", "макрокосм", "биофотон", "читать", "прочитать",
            "essay", "book", "cell", "consciousness", "fractal", "hologram",
            "insight", "light", "read the", "chapter",
        ],
    },
    "arhitektura": {
        "file": "arhitektura.txt",
        "words": [
            "архитектур", "conscious", "консиош", "протокол", "пауз",
            "рефлекс", "vl-framework", "vl framework", "фреймворк",
            "первый импульс", "r-цикл", "самонаблюд", "инженер",
            "галлюцин", "модел", "агент", "четыре голос",
            "architecture", "protocol", "pause", "reflection", "self-reflection",
            "first impulse", "framework", "hallucinat", "engineering",
        ],
    },
    "laboratoriya": {
        "file": "laboratoriya.txt",
        "words": [
            "лаборатор", "labs", "лабс", "аудит", "кодинг", "api", "апи",
            "методолог", "лицензи", "инвест", "партнёр", "партнер",
            "контакт", "связаться", "почт", "телеграм", "github", "гитхаб",
            "основател", "влад", "автор", "кто сделал", "zenodo", "doi",
            "репозитор", "medium", "вайтпейпер",
            "labs", "audit", "coding", "founder", "who made", "who built",
            "contact", "invest", "partner", "methodolog", "license", "whitepaper",
            "vlad", "author", "creator", "quantareon labs", "github", "telegram",
        ],
    },
    "astrofraktal": {
        "file": "astrofraktal.txt",
        "words": [
            "астро", "фрактал-", "машина времени", "астролог", "гороскоп",
            "натальн", "транзит", "прогресс", "синастри", "хорар",
            "планет", "градус", "азбук", "зодиак", "аспект",
            "подкаст", "собеседник по книге",
            "astro", "time machine", "astrolog", "horoscope", "natal", "transit",
            "progression", "synastry", "horary", "degree", "zodiac",
        ],
    },
    "oracle": {
        "file": "oracle.txt",
        "words": [
            "оракул", "oracle", "сон ", "сны", "снов", "сновиден", "приснил",
            "нумеролог", "число судьбы", "психоматриц", "рун", "футарк",
            "расклад", "кров", "резус", "группа кров", "удач", "прогноз удач",
            "толкован", "трактовк", "гадан", "ton", "tonkeeper",
            "oracle", "dream", "numerolog", "rune", "futhark", "blood",
            "luck forecast", "interpretation", "spread",
        ],
    },
    "audiokniga": {
        "file": "audiokniga.txt",
        "words": [
            "аудиокниг", "аудио", "послушать", "слушать", "озвуч", "начитк",
            "дмитрий", "диктор", "плеер", "длительност", "сколько минут",
            "audiobook", "listen", "narrat", "player", "how long",
        ],
    },
    "pomoshnik": {
        "file": "pomoshnik.txt",
        "words": [
            "ты кто", "кто ты", "что ты умеешь", "как ты работаешь",
            "помощник", "голосов", "микрофон", "как с тобой", "разговор",
            "окно разговора", "выключить", "включить голос", "не слышу",
            "who are you", "what can you do", "how do you work", "assistant",
            "microphone", "talk to you", "turn off",
        ],
    },
    "muzyka": {
        "file": "muzyka.txt",
        "words": ["музык", "песн", "трек", "альбом", "мелоди", "слушать музык",
              "music", "song", "track", "album"],
    },
    "video": {
        "file": "video.txt",
        "words": ["видео", "ролик", "фильм", "youtube", "ютуб", "посмотреть видео",
              "video", "clip", "watch"],
    },
}

# части эссе — для третьего слоя
ESSAY_PARTS = {
    # ⚠️ Deepgram пишет числа ЦИФРАМИ («начало 1-ой части») — словесные корни
    # («перв») их не ловили, и полный текст не подмешивался ВООБЩЕ (13.08).
    "1": ["перв", "ткань мира", "механизм", "клетк", "свет как", "биофотон",
          "1-ой част", "1-й част", "1 част", "часть 1", "части 1", "1-ую"],
    "2": ["втор", "чтение процесса", "статик", "живому миру", "таймер", "сервер",
          "2-ой част", "2-й част", "2 част", "часть 2", "части 2", "2-ую"],
    "3": ["трет", "свёрнут", "свернут", "семя", "кундалини", "зеркал", "канал истины",
          "3-ей част", "3-й част", "3 част", "часть 3", "части 3", "3-ью"],
}


# ============================================================
# Чтение файлов (один раз при старте)
# ============================================================
_CACHE: Dict[str, str] = {}


def _read_lang(name: str, lang: str = "ru") -> str:
    """Прочитать файл знаний на нужном языке.

    Для английского сначала ищем файл с хвостом _en (например
    muzyka_en.txt) — это отдельный английский текст, а не перевод
    на лету. Нет такого файла — берём русский, лучше так, чем ничего.
    """
    if str(lang).lower().startswith("en"):
        en_name = name.replace(".txt", "_en.txt")
        text = _read(en_name)
        if text:
            return text
    return _read(name)


def _read(name: str) -> str:
    if name in _CACHE:
        return _CACHE[name]
    path = KNOWLEDGE_DIR / name
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(f"ЗНАНИЯ: не прочитался {name}: {e}")
        text = ""
    _CACHE[name] = text
    return text


def _read_essay_part(part: str) -> str:
    """Полный текст части эссе — лежит рядом с движком (part1/2/3.txt)."""
    for candidate in (ROOT / f"part{part}.txt", KNOWLEDGE_DIR / f"part{part}.txt"):
        try:
            return candidate.read_text(encoding="utf-8").strip()
        except Exception:
            continue
    return ""


def warm_knowledge():
    """Прогреть кэш при старте, чтобы первый вопрос не ждал диска."""
    for lang in ("ru", "en"):
        _read_lang("karta.txt", lang)
        for t in TOPICS.values():
            _read_lang(t["file"], lang)
    total = sum(len(v) for v in _CACHE.values())
    logger.info(f"ЗНАНИЯ: загружено {len(_CACHE)} файлов, {total // 1024} КБ")


# ============================================================
# Определение темы по вопросу
# ============================================================
def detect_topic(text: str) -> Optional[str]:
    """Какой раздел сайта имеется в виду. None — тема не распознана."""
    if not text:
        return None
    low = text.lower().replace("ё", "е")

    best, best_score = None, 0
    for name, topic in TOPICS.items():
        score = 0
        for w in topic["words"]:
            w = w.replace("ё", "е")
            # ищем с НАЧАЛА слова, иначе «про» ловится внутри «просто»,
            # а «карт» — внутри «картина»
            if re.search(r"(?<![а-яa-zё])" + re.escape(w), low):
                score += 2 if len(w) > 6 else 1
        if score > best_score:
            best, best_score = name, score

    return best if best_score > 0 else None


def detect_essay_part(text: str) -> Optional[str]:
    """Если говорят о конкретной части книги — вернуть её номер."""
    if not text:
        return None
    low = text.lower().replace("ё", "е")
    for part, words in ESSAY_PARTS.items():
        for w in words:
            if w.replace("ё", "е") in low:
                return part
    return None


# ============================================================
# Сборка блока знаний для наставления
# ============================================================
def build_knowledge_block(
    user_text: str,
    sticky_topic: Optional[str] = None,
    deep: bool = False,
    lang: str = "ru",
    sticky_part: Optional[str] = None,
) -> (str, Optional[str]):
    """
    Собрать кусок знаний под текущий вопрос.

    Возвращает (текст_для_наставления, тема).
    sticky_topic — тема прошлой реплики: если в новом вопросе темы не видно,
    остаёмся на прежней (человек уточняет, а не меняет разговор).
    """
    chunks: List[str] = []

    karta = _read_lang("karta.txt", lang)
    if karta:
        chunks.append(karta)

    topic = detect_topic(user_text) or sticky_topic

    if topic and topic in TOPICS:
        body = _read_lang(TOPICS[topic]["file"], lang)
        if body:
            label = ("THE PERSON IS ASKING ABOUT THIS SECTION — here is what you know:\n"
                     if str(lang).lower().startswith("en")
                     else "ЧЕЛОВЕК СПРАШИВАЕТ ОБ ЭТОМ РАЗДЕЛЕ — вот что ты о нём знаешь:\n")
            chunks.append(label + body)

        # третий слой: полный текст части эссе. Порога «глубины» больше нет
        # (13.08): когда человек прямо просит читать и часть известна (названа
        # или липнет с прошлой реплики) — текст нужен НЕМЕДЛЕННО, а не с
        # четвёртой реплики; иначе помощник «читает» по памяти и сочиняет.
        if topic == "esse":
            # 🔖 ЧАСТЬ ТОЖЕ ЛИПКАЯ (13.08): на «стоп... продолжай» в реплике нет
            # ни номера части, ни ключевых слов — полный текст выпадал из
            # памяти, и помощник продолжал ФАНТАЗИЕЙ в стиле эссе.
            part = detect_essay_part(user_text) or sticky_part
            if part:
                full = _read_essay_part(part)
                if full:
                    chunks.append(
                        f"ПОЛНЫЙ ТЕКСТ ЧАСТИ {part} ЭССЕ (для точных ответов):\n"
                        + full
                    )

    return "\n\n".join(chunks), topic
