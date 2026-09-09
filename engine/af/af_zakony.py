# -*- coding: utf-8 -*-
"""ЛИЧНЫЕ ЗАКОНЫ КАРТЫ — хранение при карте + блок для полки ИИ.
Правило Amvera: ЗАПИСЬ только в постоянное хранилище /data (иначе стирается при рестарте).
ЧТЕНИЕ: сначала /data (живые данные), иначе комплектный файл при коде."""
import json, os
_BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lichnye_zakony.json")
_PERSIST_DIR = os.getenv("QUANTAREON_DATA", "/data")
_PERSIST = os.path.join(_PERSIST_DIR, "lichnye_zakony.json")

def _read_path():
    return _PERSIST if os.path.exists(_PERSIST) else _BUNDLED

def _read_all():
    p = _read_path()
    if os.path.exists(p):
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return {}
    return {}

def load(karta_id):
    return _read_all().get(karta_id, [])

def save(karta_id, laws):
    d = _read_all(); d[karta_id] = laws
    # Запись ТОЛЬКО в постоянное хранилище /data (правило Amvera). Вне его — не пишем никогда.
    if os.path.isdir(_PERSIST_DIR) and os.access(_PERSIST_DIR, os.W_OK):
        json.dump(d, open(_PERSIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("[QUANTAREON] /data недоступен — личные законы не сохранены (чтение работает)")

def render(karta_id):
    laws = load(karta_id)
    if not laws: return ""
    L = ["╔═══ ЛИЧНЫЕ ЗАКОНЫ КАРТЫ (из прожитой биографии; применять поверх всего) ═══"]
    for z in laws: L.append(f"  ◆ {z}")
    return "\n".join(L)
