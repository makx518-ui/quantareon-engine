/*
 * quantareon-chat.js — виджет «Обсудить с Квантарионом» (v2)
 *
 * Вставка на страницу эссе одной строкой перед </body>:
 *   <script src="https://quantareon-engine.onrender.com/quantareon-chat.js" defer></script>
 *
 * — Подхватывает светлую/тёмную тему сайта через CSS-переменные
 * — Работает на ru.html (русский) и index.html (английский)
 * — По прокрутке сам определяет, какую часть читает человек
 */
(function () {
  "use strict";

  // ── НАСТРОЙКА ────────────────────────────────────────────
  var API = "https://quantareon-engine.onrender.com/chat";
  var MAX_MESSAGES = 40; // лимит реплик читателя за сессию

  // Якоря частей: русская и английская версии страницы
  var PARTS_RU = [
    { id: "s1-часть-первая-ткань-мира-и-её-механизм", num: "1", label: "Часть I" },
    { id: "s2-часть-вторая-чтение-процесса-от-статики-к-живому-миру", num: "2", label: "Часть II" },
    { id: "s3-часть-третья-свёрнутое-семя", num: "3", label: "Часть III" },
  ];
  var PARTS_EN = [
    { id: "part-one-the-fabric-of-the-world-and-its-mechanism", num: "1", label: "Part I" },
    { id: "part-two-reading-the-process-from-the-static-to-the-living-world", num: "2", label: "Part II" },
    { id: "part-three-the-folded-seed", num: "3", label: "Part III" },
  ];

  // Определяем язык по наличию якорей на странице
  var isRU = !!document.getElementById(PARTS_RU[0].id);
  var isEN = !isRU && !!document.getElementById(PARTS_EN[0].id);
  if (!isRU && !isEN) return; // не страница эссе — виджет не нужен
  var PARTS = isRU ? PARTS_RU : PARTS_EN;

  var T = isRU ? {
    fabFull: "Обсудить с Квантарионом",
    fabShort: "Обсудить",
    title: "КВАНТАРИОН",
    intro: "Ты читаешь эссе — и можешь обсудить прочитанное.\nСпроси о любой мысли этой части, и разберём вместе.",
    placeholder: "Спросить о прочитанном…",
    thinking: "Квантарион размышляет…",
    limit: "На сегодня разговор довольно длинный — дай мыслям осесть. Перечитай главу, и вернёмся к ней свежими.",
    error: "Связь прервалась. Попробуй ещё раз через минуту.",
  } : {
    fabFull: "Discuss with Quantareon",
    fabShort: "Discuss",
    title: "QUANTAREON",
    intro: "You are reading the essay — and you can discuss it.\nAsk about any idea in this part, and let's think it through together.",
    placeholder: "Ask about what you've read…",
    thinking: "Quantareon is reflecting…",
    limit: "Quite a long conversation for today — let the thoughts settle. Reread the chapter, and we'll return to it fresh.",
    error: "Connection lost. Try again in a minute.",
  };

  var history = [];
  var userCount = 0;
  var busy = false;

  // Прогрев Render: будим сервер сразу при заходе на страницу,
  // чтобы к первому вопросу он был уже готов (холодный старт ~50 сек)
  try {
    fetch(API.replace(/\/chat$/, "/health"), { method: "GET", cache: "no-store" }).catch(function(){});
  } catch (e) {}

  // Собираем все главы (h3 с id) прямо со страницы
  var CHAPTERS = [];
  var h3s = document.querySelectorAll("h3[id]");
  for (var i = 0; i < h3s.length; i++) {
    CHAPTERS.push({ el: h3s[i], title: h3s[i].textContent.trim() });
  }

  // ── какая глава сейчас в поле зрения ─────────────────────
  function currentChapter() {
    var active = null;
    var mid = window.innerHeight * 0.4;
    for (var i = 0; i < CHAPTERS.length; i++) {
      if (CHAPTERS[i].el.getBoundingClientRect().top <= mid) active = CHAPTERS[i];
    }
    return active ? active.title : null;
  }

  // ── какая часть сейчас в поле зрения ─────────────────────
  function currentPart() {
    var active = PARTS[0];
    var mid = window.innerHeight * 0.4;
    for (var i = 0; i < PARTS.length; i++) {
      var el = document.getElementById(PARTS[i].id);
      if (el && el.getBoundingClientRect().top <= mid) active = PARTS[i];
    }
    return active;
  }

  // ── стили: цвета берём из переменных темы сайта ──────────
  // (fallback-значения — тёмная тема, если переменной вдруг нет)
  var css = "\n" +
  ".qc-fab{position:fixed;right:22px;bottom:22px;z-index:9999;" +
    "background:var(--bg,#0b0d10);border:1px solid var(--fire,#c9993f);color:var(--fire,#c9993f);" +
    "font-family:Georgia,serif;font-size:.9rem;padding:.7rem 1.1rem;" +
    "border-radius:30px;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,.25);transition:opacity .2s}" +
  ".qc-fab:hover{opacity:.85}" +
  ".qc-panel{position:fixed;right:22px;bottom:22px;z-index:10000;" +
    "width:min(400px,calc(100vw - 44px));height:min(560px,calc(100vh - 44px));" +
    "background:var(--bg,#0b0d10);border:1px solid var(--line,#43474f);border-radius:14px;" +
    "display:none;flex-direction:column;overflow:hidden;" +
    "box-shadow:0 10px 40px rgba(0,0,0,.35);font-family:Georgia,serif}" +
  ".qc-panel.open{display:flex}" +
  ".qc-head{padding:.85rem 1rem;border-bottom:1px solid var(--line,#2a2d33);" +
    "display:flex;align-items:center;justify-content:space-between}" +
  ".qc-title{font-family:Inter,-apple-system,sans-serif;font-size:.72rem;" +
    "letter-spacing:.22em;font-weight:700;color:var(--fire,#e8bd6a)}" +
  ".qc-part{font-size:.72rem;color:var(--ink-dim,#8a8f99);font-family:Inter,sans-serif;margin-top:.15rem}" +
  ".qc-close{background:none;border:none;color:var(--ink-dim,#8a8f99);font-size:1.3rem;" +
    "cursor:pointer;line-height:1;padding:0 .2rem}" +
  ".qc-close:hover{color:var(--ink,#e6e1d6)}" +
  ".qc-body{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:.75rem}" +
  ".qc-msg{max-width:85%;padding:.6rem .85rem;border-radius:12px;" +
    "font-size:.92rem;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}" +
  ".qc-user{align-self:flex-end;background:var(--bg-soft,#1c2026);color:var(--ink,#e6e1d6);" +
    "border-bottom-right-radius:3px}" +
  ".qc-ai{align-self:flex-start;background:var(--bg-soft,#14171c);color:var(--ink,#d6d1c4);" +
    "border:1px solid var(--line,#2a2d33);border-bottom-left-radius:3px}" +
  ".qc-intro{color:var(--ink-dim,#8a8f99);font-size:.85rem;line-height:1.5;text-align:center;" +
    "margin:auto 0;padding:1rem;white-space:pre-line}" +
  ".qc-dots{align-self:flex-start;color:var(--ink-dim,#8a8f99);font-size:.9rem;padding:.4rem .6rem}" +
  ".qc-foot{border-top:1px solid var(--line,#2a2d33);padding:.7rem;display:flex;gap:.5rem}" +
  ".qc-input{flex:1;background:var(--bg-soft,#14171c);border:1px solid var(--line,#43474f);" +
    "color:var(--ink,#e6e1d6);padding:.6rem .8rem;border-radius:8px;font-size:.92rem;" +
    "font-family:Georgia,serif;resize:none;max-height:100px}" +
  ".qc-input:focus{outline:none;border-color:var(--fire,#e8bd6a)}" +
  ".qc-send{background:none;border:1px solid var(--fire,#e8bd6a);color:var(--fire,#e8bd6a);" +
    "border-radius:8px;padding:0 .9rem;cursor:pointer;font-size:1.1rem}" +
  ".qc-send:hover{opacity:.8}" +
  ".qc-send:disabled{opacity:.4;cursor:default}" +
  ".qc-fab{display:flex;align-items:center;gap:7px;transition:padding .25s,font-size .25s,opacity .25s}" +
  ".qc-fab-short{display:none}" +
  "@media (max-width:600px){" +
    ".qc-fab{right:12px;bottom:16px;font-size:12.5px;padding:.62rem .9rem}" +
    ".qc-fab.qc-mini{padding:.45rem .7rem;font-size:11.5px;opacity:.72;gap:5px}" +
    ".qc-fab.qc-mini:active{opacity:1}" +
    ".qc-fab.qc-mini .qc-fab-full{display:none}" +
    ".qc-fab.qc-mini .qc-fab-short{display:inline}" +
    ".qc-fab.qc-mini svg{width:13px;height:13px}" +
    ".qc-panel{right:8px;left:8px;bottom:8px;width:auto;height:min(80vh,calc(100vh - 80px))}" +
  "}";

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // ── разметка ─────────────────────────────────────────────
  var fab = document.createElement("button");
  fab.className = "qc-fab";
  var BUBBLE = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7' +
    'a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
  fab.innerHTML = BUBBLE +
    '<span class="qc-fab-full">' + T.fabFull + '</span>' +
    '<span class="qc-fab-short">' + T.fabShort + '</span>';

  var panel = document.createElement("div");
  panel.className = "qc-panel";
  panel.innerHTML =
    '<div class="qc-head"><div>' +
      '<div class="qc-title">' + T.title + '</div>' +
      '<div class="qc-part" id="qc-part"></div>' +
    '</div>' +
    '<button class="qc-close" aria-label="close">×</button></div>' +
    '<div class="qc-body" id="qc-body">' +
      '<div class="qc-intro">' + T.intro + '</div></div>' +
    '<div class="qc-foot">' +
      '<textarea class="qc-input" id="qc-input" rows="1" placeholder="' + T.placeholder + '"></textarea>' +
      '<button class="qc-send" id="qc-send" aria-label="send">↑</button></div>';

  document.body.appendChild(fab);
  document.body.appendChild(panel);

  var body = panel.querySelector("#qc-body");
  var input = panel.querySelector("#qc-input");
  var send = panel.querySelector("#qc-send");
  var partLabel = panel.querySelector("#qc-part");

  function headLabel() {
    var ch = currentChapter();
    var p = currentPart().label;
    return ch ? p + " \u00b7 " + ch : p;
  }
  function open() {
    panel.classList.add("open");
    fab.style.display = "none";
    partLabel.textContent = headLabel();
    input.focus();
  }
  function close() {
    panel.classList.remove("open");
    fab.style.display = "";
  }
  // На телефоне: кнопка появляется полной, при первом скролле (или через 10 сек) сжимается
  if (window.matchMedia("(max-width:600px)").matches) {
    var mini = function () {
      fab.classList.add("qc-mini");
      window.removeEventListener("scroll", onScrollMini);
    };
    var onScrollMini = function () { mini(); };
    window.addEventListener("scroll", onScrollMini, { passive: true, once: true });
    setTimeout(mini, 10000);
  }

  fab.addEventListener("click", open);
  panel.querySelector(".qc-close").addEventListener("click", close);

  window.addEventListener("scroll", function () {
    if (panel.classList.contains("open"))
      partLabel.textContent = headLabel();
  }, { passive: true });

  function addMsg(text, who) {
    var intro = body.querySelector(".qc-intro");
    if (intro) intro.remove();
    var d = document.createElement("div");
    d.className = "qc-msg " + (who === "user" ? "qc-user" : "qc-ai");
    d.textContent = text;
    body.appendChild(d);
    body.scrollTop = body.scrollHeight;
    return d;
  }

  function submit() {
    var q = input.value.trim();
    if (!q || busy) return;

    if (userCount >= MAX_MESSAGES) {
      addMsg(T.limit, "ai");
      input.value = "";
      return;
    }

    var part = currentPart();
    addMsg(q, "user");
    history.push({ role: "user", content: q });
    userCount++;
    input.value = "";
    input.style.height = "auto";
    busy = true;
    send.disabled = true;

    var dots = document.createElement("div");
    dots.className = "qc-dots";
    dots.textContent = T.thinking;
    body.appendChild(dots);
    body.scrollTop = body.scrollHeight;

    fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: q,
        part: part.num,
        chapter: currentChapter(),
        history: history.slice(0, -1),
      }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        dots.remove();
        var reply = (data && data.reply) || "…";
        addMsg(reply, "ai");
        history.push({ role: "assistant", content: reply });
      })
      .catch(function () {
        dots.remove();
        addMsg(T.error, "ai");
      })
      .finally(function () {
        busy = false;
        send.disabled = false;
        input.focus();
      });
  }

  send.addEventListener("click", submit);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  });
})();
