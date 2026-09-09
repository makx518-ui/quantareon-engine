# -*- coding: utf-8 -*-
"""НАРЕЗКА ПОЛОЧКИ ПО БЛОКАМ — для схемы «Дирижёр»: каждый вызов ИИ несёт
только полочку своего блока. slice_natal(text, block) режет выдачу render_natal."""
BLOCKS_NATAL = {
    "шапка":     ("ПАСПОРТ", "ЯДРО"),
    "кармика":   ("ЯДРО", "КОНТУР ЛИЧНОСТИ"),      # ЯДРО(узлы)+КАРМИКА-ТОЧКИ+оси
    "светила":   ("ЯДРО —", "КАРМИКА-ТОЧКИ"),
    "инструменты":("КОНТУР ЛИЧНОСТИ", "АСПЕКТЫ"),  # личные+социальные+высшие+управители
    "каркас":    ("АСПЕКТЫ", None),
}
def _cut(text, start_key, end_key):
    i = text.find(start_key)
    if i < 0: return ""
    i = text.rfind("╔", 0, i+3) if text.rfind("╔", 0, i+3) >= 0 else i
    j = text.find(end_key) if end_key else len(text)
    if j < 0: j = len(text)
    return text[i:j].rstrip()

def slice_natal(natal_text, block):
    """block: шапка|кармика|светила|инструменты|каркас|всё.
    Для кармики и инструментов добавляются их аспектные строки из общего каркаса."""
    if block in ("всё", "all", None): return natal_text
    seg = _cut(natal_text, *BLOCKS_NATAL.get(block, ("ЯДРО","")))
    if block in ("кармика","светила","инструменты"):
        KARMA = {"Сев.Узел","Юж.Узел","Чёрная Луна","Белая Луна","Хирон"}
        rows = [l for l in natal_text.split("\n") if l.strip().startswith("▶")]
        if block == "кармика":
            keep = [l for l in rows if any(k in l for k in KARMA)]
        elif block == "светила":
            keep = [l for l in rows if ("Солнце" in l or "Луна " in l) and not any(k in l for k in KARMA)]
        else:
            keep = [l for l in rows if not any(k in l for k in KARMA)]
        seg += "\n── аспектные строки блока:\n" + "\n".join(keep)
    return seg

def slice_relief(relief_text, mode="кратко", age=None):
    """кратко = только строки таблицы; том = маркер для генерации тома года age."""
    if mode == "кратко": return relief_text
    return f"[ЗАПРОС ТОМА ГОДА возраст={age} — сгенерировать полную развёртку]"
