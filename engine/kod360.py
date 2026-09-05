#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
КОД-360 — словарь «число → смысл» (QUANTAREON).
Парсит монолит и отдаёт по (знак, градус) технический градус-код:
{tag, vector, energy, flag, суть, действие, риск, переход}.
Это то, что машина ВШИВАЕТ в каждую точку. ИИ его только оживляет.
"""
from __future__ import annotations
import re, math, os

_KOD = None
SIGN_RU = ["ОВЕН","ТЕЛЕЦ","БЛИЗНЕЦЫ","РАК","ЛЕВ","ДЕВА",
           "ВЕСЫ","СКОРПИОН","СТРЕЛЕЦ","КОЗЕРОГ","ВОДОЛЕЙ","РЫБЫ"]

def load(path=None):
    """Грузит и кэширует монолит. Ключ (block 1..12, degree 1..30) → код-словарь."""
    global _KOD
    if _KOD is not None:
        return _KOD
    if path is None:
        # ⚠️ Каноном для машины служит ПРИЗЕМЛЁННАЯ редакция — 12 блоков Азбуки
        # (data/azbuka/blok_NN_kod.md). Монолит kod_processa_360_polny.md — архетипическая
        # редакция, она архив; его решение 16.08: коды для машины, проза для ИИ.
        папка = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "azbuka")
        # ⚠️ в отдельных блоках свои заголовки, а разбор ищет «#  БЛОК N · ЗНАК»
        # (как в монолите) — потому при склейке ставим такой разделитель сами
        ЗНАКИ = ["ОВЕН","ТЕЛЕЦ","БЛИЗНЕЦЫ","РАК","ЛЕВ","ДЕВА",
                 "ВЕСЫ","СКОРПИОН","СТРЕЛЕЦ","КОЗЕРОГ","ВОДОЛЕЙ","РЫБЫ"]
        куски = []
        for н in range(1, 13):
            п = os.path.join(папка, f"blok_{н:02d}_kod.md")
            if os.path.exists(п):
                куски.append(f"#  БЛОК {н} · {ЗНАКИ[н-1]}\n" + open(п, encoding="utf-8").read())
        if куски:
            txt = "\n".join(куски)
        else:
            path = os.path.join(os.path.dirname(__file__), "kod_processa_360_polny.md")
            txt = open(path, encoding="utf-8").read()
    else:
        txt = open(path, encoding="utf-8").read()
    _KOD = {}
    blocks = re.split(r"#  БЛОК (\d+) · (\w+)", txt)[1:]
    for i in range(0, len(blocks), 3):
        bi = int(blocks[i]); body = blocks[i+2]
        for ch in re.split(r"\n\*\*Шаг ", body)[1:]:
            h = re.match(r"(\d+) \[(.*?)\] (.) · энергия:\s*(.+?)\s*·\s*флаг:\s*(.+?)\*\*", ch)
            if not h:
                continue
            d = int(h.group(1)); rest = ch[h.end():].strip().split("\n")
            g = lambda p: next((l.split(":",1)[1].strip() for l in rest if l.startswith(p)), "")
            _KOD[(bi, d)] = {
                "tag":     h.group(2),
                "vector":  h.group(3),
                "energy":  h.group(4).strip(),
                "flag":    h.group(5).strip(),
                "суть":    rest[0].strip() if rest else "",
                "действие": g("Действие"),
                "риск":     g("Риск"),
                "переход":  next((l.strip() for l in rest if l.strip().startswith("→")), ""),
            }
    if len(_KOD) != 360:
        raise RuntimeError(f"КОД неполон: {len(_KOD)}/360")
    return _KOD

def degree_num(pos_in_sign: float) -> int:
    """position 0..30 → градус 1..30 (10°30' → 11-й)."""
    return min(30, int(math.floor(pos_in_sign)) + 1)

def code_for(sign_num0: int, pos_in_sign: float) -> dict:
    """sign_num0 = 0..11, pos = 0..30 → градус-код."""
    return load()[(sign_num0 + 1, degree_num(pos_in_sign))]

def code_by_abs(abs_pos: float) -> dict:
    """Абсолютная долгота 0..360 → градус-код."""
    a = float(abs_pos) % 360
    return code_for(int(a // 30), a % 30)

if __name__ == "__main__":
    load()
    print("КОД-360 загружен: 360/360 ✓")
    for lbl, ap in [("Солнце Влада (Вдл 10°30')", 310.5),
                    ("Колесо (Козерог 10.6°)", 280.62)]:
        c = code_by_abs(ap)
        print(f"\n{lbl}:  [{c['tag']}] {c['vector']}  флаг: {c['flag'][:40]}")
        print(f"  суть: {c['суть'][:90]}")
