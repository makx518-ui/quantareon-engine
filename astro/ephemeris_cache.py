"""
Кэш эфемериды на диске (pickle).

Ключ: {year}_{lat:.2f}_{lng:.2f}_{tz_str}
Один файл = список AstrologicalSubject на каждый день года.

Эфемерида для данного года и координат неизменна —
инвалидация не нужна.
"""

import os
import pickle
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

CACHE_DIR = "/data/astro_cache"


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_key(year: int, lat: float, lng: float, tz_str: str) -> str:
    """Формирует имя файла кэша."""
    safe_tz = tz_str.replace("/", "_").replace("\\", "_")
    return f"ephemeris_{year}_{lat:.2f}_{lng:.2f}_{safe_tz}.pkl"


def get_cached_subjects(year: int, lat: float, lng: float, tz_str: str):
    """
    Возвращает список AstrologicalSubject на каждый день года.
    Если кэш есть — читает с диска (~0.5s).
    Если нет — считает через EphemerisDataFactory (~16s) и сохраняет.
    """
    _ensure_cache_dir()
    fname = _cache_key(year, lat, lng, tz_str)
    fpath = os.path.join(CACHE_DIR, fname)

    # Попытка прочитать из кэша
    if os.path.exists(fpath):
        try:
            with open(fpath, "rb") as f:
                subjects = pickle.load(f)
            logger.info(f"📦 Ephemeris cache HIT: {fname} ({len(subjects)} subjects)")
            return subjects
        except Exception as e:
            logger.warning(f"⚠️ Ephemeris cache read error: {e}. Recalculating.")

    # Расчёт
    from kerykeion import EphemerisDataFactory

    factory = EphemerisDataFactory(
        start_datetime=datetime(year, 1, 1),
        end_datetime=datetime(year, 12, 31),
        step_type="days",
        step=1,
        lat=lat, lng=lng, tz_str=tz_str,
    )
    subjects = factory.get_ephemeris_data_as_astrological_subjects()
    logger.info(f"🔮 Ephemeris calculated: {len(subjects)} subjects for {year}")

    # Сохранение в кэш
    try:
        with open(fpath, "wb") as f:
            pickle.dump(subjects, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"💾 Ephemeris cache SAVED: {fname}")
    except Exception as e:
        logger.warning(f"⚠️ Ephemeris cache save error: {e}")

    return subjects
