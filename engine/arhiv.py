# -*- coding: utf-8 -*-
"""
АРХИВ КАРТ — карты клиентам и кухня ученику, раздельно.

Его правило 05.09: карта и кухня лежат ОТДЕЛЬНО.
Клиенту — красивый HTML без терминов. Ученику — три слоя целиком.

⚠️ 05.09, вечер: хранение переведено в Cloudflare R2.
Причина: Render стирает диск при каждой пересборке, а архив должен
жить годами — вернуться через год и сверить, отдать ученику.
Ключи те же, что у счётчика посещений (stats.py): R2_ACCOUNT_ID,
R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET. Создавать ничего не надо.

Устройство в бакете:
    astro/karty/<Имя>/карты/2026-09-05_11-20_natal.html
    astro/karty/<Имя>/кухня/2026-09-05_11-20.json
    astro/dnevnik.json
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta

БАКЕТ = os.getenv("R2_BUCKET", "quantareon-media")
ПАПКА = os.getenv("ASTRO_PREFIX", "astro")
АРХИВ = f"{ПАПКА}/karty"
ДНЕВНИК = f"{ПАПКА}/dnevnik.json"

# запасной путь на диске, если R2 недоступен — чтобы не терять расчёт
МЕСТНЫЙ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "astro_memory")

ВЕРСИЯ = {
    "методика": "2026-09-05",
    "азбука": "360 шагов, приземлённая редакция",
    "орбисы_космограммы": "светила 5° · септенер и Юпитер/Сатурн 4° · высшие 3.5° · Хирон, Лилит, Селена, узлы 3°",
    "орбисы_транзитов": "планеты 3° · высшие 2°",
    "орбисы_медленных": "дирекции, прогрессии, Колесо — 1°",
    "уровней_колеса": 2,
}

_хранилище = None


def _клиент():
    """Подключение к R2 — теми же ключами, что у счётчика."""
    global _хранилище
    if _хранилище is not None:
        return _хранилище
    аккаунт = os.getenv("R2_ACCOUNT_ID")
    ключ = os.getenv("R2_ACCESS_KEY")
    секрет = os.getenv("R2_SECRET_KEY")
    if not (аккаунт and ключ and секрет):
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
            config=Config(retries={"max_attempts": 2},
                          connect_timeout=5, read_timeout=15),
        )
        return _хранилище
    except Exception:
        return None


def _слаг(имя):
    """Имя клиента в имя папки."""
    ч = re.sub(r"[^\w\s-]", "", имя or "", flags=re.UNICODE).strip()
    return re.sub(r"[\s]+", "_", ч) or "без_имени"


def _положить(ключ, текст, тип="application/json; charset=utf-8"):
    """Записать в R2; если не вышло — на диск, чтобы не потерять."""
    к = _клиент()
    if к is not None:
        try:
            к.put_object(Bucket=БАКЕТ, Key=ключ,
                         Body=текст.encode("utf-8"), ContentType=тип)
            return ключ
        except Exception:
            pass
    путь = os.path.join(МЕСТНЫЙ, ключ)
    os.makedirs(os.path.dirname(путь), exist_ok=True)
    with open(путь, "w", encoding="utf-8") as ф:
        ф.write(текст)
    return ключ


def _взять(ключ):
    """Прочитать из R2, иначе с диска. None — если нигде нет."""
    к = _клиент()
    if к is not None:
        try:
            о = к.get_object(Bucket=БАКЕТ, Key=ключ)
            return о["Body"].read().decode("utf-8")
        except Exception:
            pass
    путь = os.path.join(МЕСТНЫЙ, ключ)
    if os.path.exists(путь):
        return open(путь, encoding="utf-8").read()
    return None


def _убрать(ключ):
    к = _клиент()
    убрано = False
    if к is not None:
        try:
            к.delete_object(Bucket=БАКЕТ, Key=ключ)
            убрано = True
        except Exception:
            pass
    путь = os.path.join(МЕСТНЫЙ, ключ)
    if os.path.exists(путь):
        os.remove(путь)
        убрано = True
    return убрано


def перечислить(префикс):
    """Все ключи под этим префиксом — из R2 и с диска."""
    ключи = set()
    к = _клиент()
    if к is not None:
        try:
            маркер = None
            while True:
                кв = {"Bucket": БАКЕТ, "Prefix": префикс, "MaxKeys": 1000}
                if маркер:
                    кв["ContinuationToken"] = маркер
                о = к.list_objects_v2(**кв)
                for э in о.get("Contents", []):
                    ключи.add(э["Key"])
                if not о.get("IsTruncated"):
                    break
                маркер = о.get("NextContinuationToken")
        except Exception:
            pass
    корень = os.path.join(МЕСТНЫЙ, префикс)
    if os.path.isdir(корень):
        for к_, _, фс in os.walk(корень):
            for ф in фс:
                п = os.path.join(к_, ф)
                ключи.add(os.path.relpath(п, МЕСТНЫЙ).replace(os.sep, "/"))
    return sorted(ключи)


# ═══════════════════════════════════════════════════════════════════
#  КУХНЯ · для ученика
# ═══════════════════════════════════════════════════════════════════

def положить_кухню(имя_клиента, заказ, итог, данные_рождения,
                   момент=None, пояс_часов=0):
    """Три слоя целиком, вся механика."""
    момент = момент or datetime.now(timezone.utc)
    местное = момент + timedelta(hours=пояс_часов)
    ключ = (f"{АРХИВ}/{_слаг(имя_клиента)}/кухня/"
            f"{местное.strftime('%Y-%m-%d_%H-%M')}.json")
    _положить(ключ, json.dumps({
        "клиент": имя_клиента, "заказ": заказ,
        "момент_расчёта": местное.strftime("%Y-%m-%d %H:%M:%S"),
        "версия": ВЕРСИЯ,
        "данные_рождения": данные_рождения,
        "время_известно": итог.get("время_известно"),
        "слой1_данность": итог.get("слой1", ""),
        "слой2_ситуация": итог.get("слой2", ""),
        "слой3_сутки": итог.get("слой3", ""),
    }, ensure_ascii=False, indent=2))
    _в_дневник(имя_клиента, ключ, местное)
    return ключ


# ═══════════════════════════════════════════════════════════════════
#  КАРТА · для клиента
# ═══════════════════════════════════════════════════════════════════

def положить_карту(имя_клиента, заказ, html, момент=None, пояс_часов=0):
    """Готовый HTML без единого термина."""
    момент = момент or datetime.now(timezone.utc)
    местное = момент + timedelta(hours=пояс_часов)
    ключ = (f"{АРХИВ}/{_слаг(имя_клиента)}/карты/"
            f"{местное.strftime('%Y-%m-%d_%H-%M')}_{заказ}.html")
    _положить(ключ, html, "text/html; charset=utf-8")
    return ключ


def сохранить_синастрию(имя_а, имя_б, итог, данные_а, данные_б,
                        трактовка="", момент=None, пояс_часов=0):
    """Встреча двух карт — в папку на пару."""
    момент = момент or datetime.now(timezone.utc)
    местное = момент + timedelta(hours=пояс_часов)
    ключ = (f"{АРХИВ}/{_слаг(f'{имя_а} и {имя_б}')}/кухня/"
            f"{местное.strftime('%Y-%m-%d_%H-%M')}.json")
    _положить(ключ, json.dumps({
        "клиент": f"{имя_а} и {имя_б}", "заказ": "sinastriya",
        "момент_расчёта": местное.strftime("%Y-%m-%d %H:%M:%S"),
        "версия": ВЕРСИЯ,
        "данные_рождения": {"первый": данные_а, "второй": данные_б},
        "карта_первого": итог["первый"].get("слой1", ""),
        "карта_второго": итог["второй"].get("слой1", ""),
        "встреча": итог.get("встреча", ""),
        "трактовка": трактовка,
    }, ensure_ascii=False, indent=2))
    _в_дневник(f"{имя_а} и {имя_б}", ключ, местное)
    return ключ


# ═══════════════════════════════════════════════════════════════════
#  ДНЕВНИК И ЧТЕНИЕ
# ═══════════════════════════════════════════════════════════════════

def _в_дневник(имя, ключ, когда):
    """Короткая строка на каждый заход."""
    дн = {"заходы": []}
    было = _взять(ДНЕВНИК)
    if было:
        try:
            дн = json.loads(было)
        except Exception:
            pass
    дн.setdefault("заходы", []).append({
        "номер": len(дн.get("заходы", [])) + 1,
        "клиент": имя,
        "когда": когда.strftime("%Y-%m-%d %H:%M"),
        "файл": ключ,
    })
    дн["заходы"] = дн["заходы"][-500:]        # держим последние пятьсот
    _положить(ДНЕВНИК, json.dumps(дн, ensure_ascii=False, indent=2))


def отдать_файл(ключ):
    """Содержимое по ключу — карта или кухня."""
    if not ключ or ".." in ключ or not ключ.startswith(ПАПКА):
        return None
    return _взять(ключ)


def дописать_отклик(ключ, что_было, сбылось=None, промахи=""):
    """Вернуться к старой записи и записать, что случилось.
    Это и есть материал для азбуки перевода."""
    т = _взять(ключ)
    if not т:
        return None
    з = json.loads(т)
    з["отклик"] = {"что_было": что_было, "сбылось": сбылось,
                   "промахи": промахи,
                   "дата_отклика": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    _положить(ключ, json.dumps(з, ensure_ascii=False, indent=2))
    return ключ


def карты_клиента(имя):
    """Все заходы человека."""
    return перечислить(f"{АРХИВ}/{_слаг(имя)}/")


def найти_по_градусу(тег):
    """Все кухни, где встречался этот код — для азбуки."""
    найдено = []
    for к in перечислить(f"{АРХИВ}/"):
        if not к.endswith(".json"):
            continue
        т = _взять(к)
        if т and тег in т:
            найдено.append(к)
    return найдено
