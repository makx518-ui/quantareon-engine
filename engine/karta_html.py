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

ЗНАЧОК_ЗАКАЗА = {
    "natal": "✦", "kosmogramma": "✦", "tranzity": "🧭",
    "solyar": "☀️", "den": "🌙", "sinastriya": "💞",
}

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
html { scroll-behavior: smooth; }
body {
  background: radial-gradient(ellipse at top, #1a2040 0%, #0d0f1a 55%, #060810 100%);
  background-attachment: fixed;
  font-family: Georgia, 'Times New Roman', serif;
  color: #e6ddc9;
  line-height: 1.78;
  padding: 0 18px 90px;
  position: relative;
  overflow-x: hidden;
}
/* звёздное небо и туман — как на странице соляра */
.zvezda { position: fixed; width: 2px; height: 2px; background: #fff; border-radius: 50%;
          animation: mercanie 3s infinite ease-in-out; pointer-events: none; z-index: 0; }
@keyframes mercanie { 0%,100% { opacity:.25 } 50% { opacity:1 } }
.tuman { position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background: radial-gradient(ellipse at 30% 70%, rgba(90,110,190,.16), transparent 55%),
              radial-gradient(ellipse at 70% 25%, rgba(232,178,58,.07), transparent 55%); }
.list { max-width: 760px; margin: 0 auto; position: relative; z-index: 1; }

/* обложка */
.shapka { text-align:center; padding: 54px 0 34px; }
.shar {
  width: 78px; height: 78px; border-radius: 50%; margin: 0 auto 22px;
  background: radial-gradient(circle at 35% 32%, #ffd97a, #E8B23A 45%, #8a6a1e 100%);
  box-shadow: 0 0 32px rgba(232,178,58,.5);
  animation: pulsar 4s infinite ease-in-out;
  display:flex; align-items:center; justify-content:center; font-size:34px;
}
@keyframes pulsar {
  0%,100% { box-shadow: 0 0 30px rgba(232,178,58,.45) }
  50%     { box-shadow: 0 0 58px rgba(232,178,58,.75), 0 0 100px rgba(232,178,58,.3) }
}
.shapka h1 { font-size: 27px; letter-spacing: 6px; font-weight: 400; color: #E8B23A; margin-bottom: 10px; }
.shapka .pod { color:#9aa2c4; font-size:14px; font-style:italic; }
.shapka .znachok { display:inline-block; margin-top:16px; padding:4px 16px; border-radius:20px;
  background: rgba(232,178,58,.1); border:1px solid rgba(232,178,58,.3);
  color:#E8B23A; font-size:13px; letter-spacing:2px; }
.shapka .kto { margin-top: 22px; padding-top: 18px;
  border-top: 1px solid rgba(232,178,58,.2); color:#c3c9e0; font-size:14px; }
.shapka .kto b { color:#e6ddc9; font-weight:400; }
.ogovorka { margin-top: 14px; color:#7f87a6; font-size:12.5px; font-style:italic; }

/* навигация по разделам — карточками, как в соляре */
.navigator { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin: 26px 0 40px; }
.navigator a {
  display:block; padding:9px 14px; border-radius:12px; text-decoration:none;
  background: rgba(90,110,190,.10); border:1px solid rgba(90,110,190,.28);
  color:#c3c9e0; font-size:12.5px; letter-spacing:1px; transition: all .25s ease;
}
.navigator a:hover { background: rgba(232,178,58,.12); border-color: rgba(232,178,58,.45); color:#E8B23A; }
.navigator a .ikonka { margin-right:6px; }

/* разделы */
.razdel { margin-bottom: 40px; scroll-margin-top: 20px; }
.razdel h2 {
  font-size: 13px; letter-spacing: 3px; font-weight: 400;
  color: #E8B23A; text-transform: uppercase;
  padding-bottom: 9px; margin-bottom: 18px;
  border-bottom: 1px solid rgba(232,178,58,.22);
  display:flex; align-items:center; gap:9px;
}
.razdel p { margin-bottom: 15px; font-size: 16.5px; }
.razdel p:last-child { margin-bottom: 0; }
.razdel b, .razdel strong { color:#E8B23A; font-weight:600; }
.razdel em { color:#9aa2c4; }

/* врезка — окна, пики, важное */
.vrez {
  margin: 16px 0; padding: 13px 18px;
  border-left: 2px solid rgba(232,178,58,.5);
  background: rgba(232,178,58,.05);
  color:#d8cfae; font-size:15px; font-style: italic;
}
/* ключевые даты лентой */
.daty { display:flex; flex-wrap:wrap; gap:7px; margin-top:6px; }
.daty span {
  padding:5px 11px; border-radius:9px; font-size:13px;
  background: rgba(90,110,190,.12); border:1px solid rgba(90,110,190,.3); color:#c3c9e0;
}
.daty span.glavnaya { background: rgba(232,178,58,.14); border-color: rgba(232,178,58,.45); color:#E8B23A; }

/* панель правки — только на моей странице, в файле клиента её нет */
.pravka {
  position: fixed; left: 22px; bottom: 22px; z-index: 6;
  display: flex; gap: 8px; align-items: center;
}
.pravka button {
  padding: 9px 15px; border-radius: 22px; cursor: pointer;
  background: rgba(26,32,64,.92); border: 1px solid rgba(232,178,58,.45);
  color: #E8B23A; font-family: Georgia, serif; font-size: 13px;
  box-shadow: 0 4px 18px rgba(0,0,0,.5); transition: all .2s ease;
}
.pravka button:hover { background: rgba(232,178,58,.16); }
.pravka .sost { color:#9aa2c4; font-size:12px; }
body.pravim .razdel p, body.pravim .razdel h2,
body.pravim .vrez, body.pravim .daty span {
  outline: 1px dashed rgba(232,178,58,.35); outline-offset: 4px; border-radius: 3px;
}
body.pravim .razdel p:focus, body.pravim .razdel h2:focus, body.pravim .vrez:focus {
  outline: 1px solid #E8B23A; background: rgba(232,178,58,.05);
}

/* кнопка возврата к списку разделов */
.naverh {
  position: fixed; right: 22px; bottom: 22px; z-index: 5;
  width: 46px; height: 46px; border-radius: 50%;
  background: rgba(26,32,64,.92); border: 1px solid rgba(232,178,58,.45);
  color: #E8B23A; font-size: 19px; text-decoration: none;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none; transition: opacity .3s ease, transform .2s ease;
  box-shadow: 0 4px 18px rgba(0,0,0,.5);
}
.naverh.vidno { opacity: 1; pointer-events: auto; }
.naverh:hover { transform: translateY(-2px); background: rgba(232,178,58,.16); }
/* активный раздел в навигаторе */
.navigator a.tekushiy {
  background: rgba(232,178,58,.16); border-color: rgba(232,178,58,.5); color: #E8B23A;
}
.konec { margin-top: 54px; padding-top: 26px;
  border-top: 1px solid rgba(232,178,58,.2); text-align:center; }
.konec .podpis { color:#E8B23A; font-size: 15px; letter-spacing: 2px; }
.konec .data { color:#6f7794; font-size: 12px; margin-top: 8px; }

@media (max-width: 600px) {
  body { padding: 0 13px 60px; }
  .shapka h1 { font-size: 21px; letter-spacing: 4px; }
  .razdel p { font-size: 15.5px; }
  .navigator a { font-size: 11.5px; padding: 7px 11px; }
}
@media print {
  body { background: #fff; color: #1a1a1a; }
  .zvezda, .tuman, .navigator, .shar { display: none; }
  .shapka h1, .razdel h2, .razdel b { color: #7a5c14; }
}
"""

ЗНАЧКИ_РАЗДЕЛОВ = {
    "что это за год": "🌟", "суть": "🌟", "кто ты": "🌟", "кто пришёл": "🌟",
    "где ты": "🧭", "дуга": "🧭", "герой": "☀️", "судьба": "🔮", "кармик": "🔮",
    "вызрело": "🌱", "разворачивается": "📅", "акт": "📅", "главное событие": "⚡",
    "дело": "💼", "признание": "💼", "любовь": "💕", "близк": "💕",
    "деньги": "💰", "здоровье": "🌿", "силы": "🌿",
    "взять": "🎯", "избежать": "🎯", "возможност": "🎯", "предупрежд": "⚠️",
    "ключевые": "📌", "даты": "📌", "дни": "📌", "узор": "✦", "итог": "✦", "совет": "🎯",
}


ПАНЕЛЬ_ПРАВКИ = """
<div class="pravka">
  <button id="knopkaPravki">✎ править</button>
  <button id="knopkaSohranit" style="display:none">сохранить</button>
  <button id="knopkaOtmena" style="display:none">отменить</button>
  <span class="sost" id="sostoyanie"></span>
</div>
<script>
(function () {
  var put = new URLSearchParams(location.search).get('f');
  var telo = document.body;
  var kPr = document.getElementById('knopkaPravki');
  var kSo = document.getElementById('knopkaSohranit');
  var kOt = document.getElementById('knopkaOtmena');
  var sost = document.getElementById('sostoyanie');
  var bylo = null;
  var pravimye = function () {
    return document.querySelectorAll('.razdel p, .razdel h2, .vrez, .daty span, .shapka .kto');
  };
  function vklyuchit(da) {
    telo.classList.toggle('pravim', da);
    pravimye().forEach(function (e) { e.contentEditable = da ? 'true' : 'false'; });
    kPr.style.display = da ? 'none' : '';
    kSo.style.display = kOt.style.display = da ? '' : 'none';
    document.querySelector('.naverh').style.display = da ? 'none' : '';
  }
  kPr.onclick = function () {
    bylo = document.querySelector('.list').innerHTML;
    vklyuchit(true);
    sost.textContent = 'правь текст прямо на странице';
  };
  kOt.onclick = function () {
    if (bylo !== null) document.querySelector('.list').innerHTML = bylo;
    vklyuchit(false);
    sost.textContent = 'правки отменены';
    setTimeout(function () { sost.textContent = ''; }, 2500);
  };
  kSo.onclick = function () {
    vklyuchit(false);
    if (!put) { sost.textContent = 'некуда сохранять: открой карту из истории'; return; }
    sost.textContent = 'сохраняю…';
    var kopiya = document.documentElement.cloneNode(true);
    var lishnee = kopiya.querySelector('.pravka');
    if (lishnee) lishnee.remove();
    var skripty = kopiya.querySelectorAll('script');
    // оставляем только скрипт кнопки «наверх» (первый), скрипт правки удаляем
    if (skripty.length > 1) skripty[skripty.length - 1].remove();
    kopiya.querySelectorAll('[contenteditable]').forEach(function (e) { e.removeAttribute('contenteditable'); });
    fetch('/api/karta/sohranit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ f: put, html: '<!DOCTYPE html>' + kopiya.outerHTML })
    }).then(function (o) { return o.json(); })
      .then(function (j) {
        sost.textContent = j.ok ? 'сохранено · прежняя версия рядом' : ('не сохранилось: ' + (j.detail || ''));
        setTimeout(function () { sost.textContent = ''; }, 4000);
      })
      .catch(function (e) { sost.textContent = 'ошибка: ' + e.message; });
  };
})();
</script>"""

СКРИПТ = """<a href="#top" class="naverh" title="К списку разделов">&#8593;</a>
<script>
(function () {
  var knopka = document.querySelector('.naverh');
  var ssylki = [].slice.call(document.querySelectorAll('.navigator a'));
  var razdely = ssylki.map(function (a) { return document.querySelector(a.getAttribute('href')); });
  function obnovit() {
    if (knopka) knopka.classList.toggle('vidno', window.scrollY > 500);
    var i = 0;
    for (var n = 0; n < razdely.length; n++) {
      if (razdely[n] && razdely[n].getBoundingClientRect().top <= 120) i = n;
    }
    ssylki.forEach(function (a, n) { a.classList.toggle('tekushiy', n === i); });
  }
  window.addEventListener('scroll', obnovit, { passive: true });
  obnovit();
})();
</script>"""

def _значок(заголовок):
    н = заголовок.lower()
    for ключ, знак in ЗНАЧКИ_РАЗДЕЛОВ.items():
        if ключ in н:
            return знак
    return "✦"



def _абзацы(текст):
    """Markdown читателя → HTML: жирный, курсив, врезки, ленты дат."""
    import re as _re
    куски = []
    for к in текст.split("\n\n"):
        к = к.strip()
        if not к:
            continue
        если_врез = к.startswith(">") or к.startswith("*Окно") or к.startswith("*Окна")
        # экранируем, потом возвращаем разметку
        т = _html.escape(к.lstrip("> ").strip())
        т = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", т)
        т = _re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", т)
        т = т.replace("\n", "<br>")
        if если_врез:
            куски.append(f'<div class="vrez">{т}</div>')
        elif "·" in к and _re.search(r"\d{1,2}\s+(янв|фев|мар|апр|ма|июн|июл|авг|сен|окт|ноя|дек)", к):
            # лента ключевых дат
            дни = [x.strip() for x in т.split("·") if x.strip()]
            ленты = "".join(
                f'<span class="{"glavnaya" if "<b>" in д else ""}">{д}</span>' for д in дни)
            куски.append(f'<div class="daty">{ленты}</div>')
        else:
            куски.append(f"<p>{т}</p>")
    return "\n      ".join(куски)

def карта_клиенту(трактовка_по_разделам, имя, заказ="natal",
                  данные_рождения=None, без_времени=False,
                  момент=None, пояс_часов=0, правка=False):
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

    # разделы с якорями и значками + навигатор поверх, как на странице соляра
    куски, ссылки = [], []
    for н, (з, т) in enumerate(x for x in трактовка_по_разделам if x[1] and x[1].strip()):
        знак = _значок(з)
        куски.append(f'''    <section class="razdel" id="r{н}">
      <h2><span class="ikonka">{знак}</span>{_html.escape(з)}</h2>
      {_абзацы(т)}
    </section>''')
        ссылки.append(f'<a href="#r{н}"><span class="ikonka">{знак}</span>{_html.escape(з)}</a>')
    разделы = "\n".join(куски)
    навигатор = ('<nav class="navigator">' + "".join(ссылки) + "</nav>") if len(ссылки) > 2 else ""
    звёзды = "".join(
        f'<div class="zvezda" style="left:{(i * 37) % 100}%;top:{(i * 61) % 100}%;'
        f'animation-delay:{(i % 7) * 0.4:.1f}s"></div>' for i in range(60))

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(заг.title())} · {_html.escape(имя)}</title>
<style>{СТИЛЬ}</style>
</head>
<body>
<div class="tuman"></div>
{звёзды}
<div class="list" id="top">

  <header class="shapka">
    <div class="shar">{ЗНАЧОК_ЗАКАЗА.get(заказ, "✦")}</div>
    <h1>{_html.escape(заг)}</h1>
    <div class="pod">{_html.escape(под)}</div>
    <div class="kto">{'<br>'.join(строки_кто)}</div>
    {оговорка}
  </header>

{навигатор}

{разделы}

  <footer class="konec">
    <div class="podpis">Астрофрактальная астрология · Квантареон</div>
    <div class="data">разбор составлен {местное.strftime('%d.%m.%Y')} · <a href="https://quantareon.com" style="color:#7f87a6">quantareon.com</a></div>
  </footer>

</div>
{СКРИПТ}{ПАНЕЛЬ_ПРАВКИ if правка else ''}
</body>
</html>"""
