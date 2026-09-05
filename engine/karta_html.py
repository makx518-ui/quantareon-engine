# -*- coding: utf-8 -*-
"""
КАРТА КЛИЕНТУ — красивый HTML-файл, как на экране.

Его правило 05.09: карту и кухню класть РАЗДЕЛЬНО.
Клиенту уходит файл с трактовкой, без единого термина.
Кухня остаётся в архиве для ученика.

Стиль взят с его страницы соляра: тёмный космический фон,
засечный шрифт, карточки-разделы.
"""
import html as _html
from datetime import datetime, timezone, timedelta

ЗАГОЛОВКИ = {
    "natal": ("НАТАЛЬНАЯ КАРТА", "кто ты и с чем пришёл"),
    "kosmogramma": ("КОСМОГРАММА", "узор, с которым пришла душа"),
    "tranzity": ("ГДЕ ТЫ СЕЙЧАС", "что сложилось на этот момент"),
    "solyar": ("КАРТА ГОДА", "прогноз от дня рождения до дня рождения"),
    "den": ("ПРОГНОЗ НА ДЕНЬ", "как разворачиваются эти сутки"),
    "sinastriya": ("СИНАСТРИЯ", "две карты одна на другую"),
}

СТИЛЬ = """
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background: radial-gradient(ellipse at top, #1a1b3f 0%, #0a0e27 55%, #050714 100%);
  background-attachment: fixed;
  font-family: Georgia, 'Times New Roman', serif;
  color: #e6ddc9;
  line-height: 1.75;
  padding: 40px 18px 80px;
}
.list { max-width: 720px; margin: 0 auto; }

.shapka { text-align:center; margin-bottom: 42px; }
.shapka h1 {
  font-size: 26px; letter-spacing: 5px; font-weight: 400;
  color: #E8B23A; margin-bottom: 10px;
}
.shapka .pod { color:#9b8fb0; font-size:14px; font-style:italic; }
.shapka .kto {
  margin-top: 20px; padding-top: 18px;
  border-top: 1px solid rgba(232,178,58,.2);
  color:#c9bfd8; font-size:14px;
}
.shapka .kto b { color:#e6ddc9; font-weight:400; }
.ogovorka {
  margin-top: 14px; color:#8b8299; font-size:12.5px; font-style:italic;
}

.razdel { margin-bottom: 34px; }
.razdel h2 {
  font-size: 13px; letter-spacing: 3px; font-weight: 400;
  color: #E8B23A; text-transform: uppercase;
  padding-bottom: 9px; margin-bottom: 16px;
  border-bottom: 1px solid rgba(232,178,58,.22);
}
.razdel p { margin-bottom: 15px; font-size: 16px; }
.razdel p:last-child { margin-bottom: 0; }
.razdel em { color:#d9c9e8; font-style: italic; }
.razdel b { color:#f0e6d2; font-weight: 600; }

.vrez {
  margin: 26px 0; padding: 18px 22px;
  border-left: 2px solid rgba(232,178,58,.45);
  background: rgba(232,178,58,.045);
  font-size: 16px; color:#f0e6d2;
}

.podval {
  margin-top: 54px; padding-top: 20px;
  border-top: 1px solid rgba(255,255,255,.08);
  text-align:center; color:#6b6478; font-size:12px; line-height:1.9;
}
.podval a { color:#8b8299; text-decoration:none; }

@media (max-width: 560px) {
  body { padding: 26px 14px 60px; }
  .shapka h1 { font-size: 21px; letter-spacing: 3px; }
  .razdel p { font-size: 15.5px; }
}
@media print {
  body { background:#fff; color:#1a1a1a; }
  .shapka h1, .razdel h2 { color:#8a6a12; }
  .vrez { background:#faf6ec; border-left-color:#c9a961; color:#1a1a1a; }
}
"""


def _абзацы(текст):
    """Текст трактовки в абзацы. Пустая строка — новый абзац.
    Строка, начатая с '>', становится врезом."""
    куски = []
    for кусок in текст.strip().split("\n\n"):
        к = кусок.strip()
        if not к:
            continue
        if к.startswith(">"):
            куски.append(f'<div class="vrez">{_html.escape(к.lstrip("> ")).strip()}</div>')
        else:
            куски.append(f"<p>{_html.escape(к)}</p>")
    return "\n      ".join(куски)


def карта_клиенту(трактовка_по_разделам, имя, заказ="natal",
                  данные_рождения=None, без_времени=False,
                  момент=None, пояс_часов=0):
    """Собирает HTML-файл для клиента.

    трактовка_по_разделам: [(заголовок, текст), ...] — то, что написал читатель.
    Кухни здесь нет вовсе: ни градусов, ни домов, ни терминов.
    """
    момент = момент or datetime.now(timezone.utc)
    местное = момент + timedelta(hours=пояс_часов)
    заг, под = ЗАГОЛОВКИ.get(заказ, ЗАГОЛОВКИ["natal"])

    строки_кто = []
    if данные_рождения:
        д = данные_рождения
        строка = f"<b>{_html.escape(имя)}</b>"
        if д.get("дата"):
            строка += f" · {_html.escape(str(д['дата']))}"
        if д.get("время") and not без_времени:
            строка += f", {_html.escape(str(д['время']))}"
        if д.get("место"):
            строка += f" · {_html.escape(str(д['место']))}"
        строки_кто.append(строка)
    else:
        строки_кто.append(f"<b>{_html.escape(имя)}</b>")

    оговорка = ('<div class="ogovorka">Время рождения не указано — '
                'карта прочитана от Солнца.</div>') if без_времени else ""

    разделы = "\n".join(
        f'''    <section class="razdel">
      <h2>{_html.escape(з)}</h2>
      {_абзацы(т)}
    </section>'''
        for з, т in трактовка_по_разделам if т and т.strip())

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(заг.title())} · {_html.escape(имя)}</title>
<style>{СТИЛЬ}</style>
</head>
<body>
<div class="list">

  <header class="shapka">
    <h1>{_html.escape(заг)}</h1>
    <div class="pod">{_html.escape(под)}</div>
    <div class="kto">{'<br>'.join(строки_кто)}</div>
    {оговорка}
  </header>

{разделы}

  <footer class="podval">
    Астрофрактальная астрология · Квантареон<br>
    разбор составлен {местное.strftime('%d.%m.%Y')}<br>
    <a href="https://quantareon.com">quantareon.com</a>
  </footer>

</div>
</body>
</html>"""
