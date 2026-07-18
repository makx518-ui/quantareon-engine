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
    micStart: "Записать голосом",
    listen: "Озвучить",
    micStop: "Идёт запись — говори",
    micWait: "Распознаю…",
    micListen: "Слушаю… говори",
    micQuiet: "Ничего не расслышал. Попробуй ещё раз, поближе к микрофону.",
    micDenied: "Не получилось включить микрофон. Разреши доступ в настройках браузера.",
    micFail: "Не удалось распознать речь. Попробуй ещё раз или напиши текстом.",
  } : {
    fabFull: "Discuss with Quantareon",
    fabShort: "Discuss",
    title: "QUANTAREON",
    intro: "You are reading the essay — and you can discuss it.\nAsk about any idea in this part, and let's think it through together.",
    placeholder: "Ask about what you've read…",
    thinking: "Quantareon is reflecting…",
    limit: "Quite a long conversation for today — let the thoughts settle. Reread the chapter, and we'll return to it fresh.",
    error: "Connection lost. Try again in a minute.",
    micStart: "Record by voice",
    listen: "Listen",
    micStop: "Recording — speak",
    micWait: "Transcribing…",
    micListen: "Listening… speak",
    micQuiet: "I didn't catch anything. Try again, closer to the mic.",
    micDenied: "Could not access the microphone. Allow it in your browser settings.",
    micFail: "Could not transcribe. Try again or type your question.",
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
  ".qc-mic{background:none;border:1px solid var(--line,#43474f);color:var(--ink-dim,#8a8f99);" +
    "border-radius:8px;padding:0 .7rem;cursor:pointer;display:flex;align-items:center;" +
    "justify-content:center;transition:color .2s,border-color .2s}" +
  ".qc-mic:hover{color:var(--fire,#e8bd6a);border-color:var(--fire,#e8bd6a)}" +
  ".qc-mic.rec{color:#e05a4a;border-color:#e05a4a;animation:qcpulse 1.1s infinite}" +
  ".qc-mic:disabled{opacity:.45;cursor:default}" +
  "@keyframes qcpulse{0%,100%{opacity:1}50%{opacity:.45}}" +
  ".qc-spk{background:none;border:1px solid var(--line,#43474f);border-radius:14px;" +
    "color:var(--fire,#e8bd6a);cursor:pointer;" +
    "padding:4px 10px;margin-top:6px;display:inline-flex;align-items:center;gap:6px;" +
    "font-size:12.5px;font-family:Inter,sans-serif;opacity:.95;transition:border-color .2s,opacity .2s}" +
  ".qc-spk:hover{border-color:var(--fire,#e8bd6a);opacity:1}" +
  ".qc-spk.playing{color:var(--fire,#e8bd6a);opacity:1;animation:qcpulse 1.2s infinite}" +
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
      '<button class="qc-mic" id="qc-mic" aria-label="' + T.micStart + '" title="' + T.micStart + '">' +
        '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>' +
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/>' +
        '<line x1="8" y1="23" x2="16" y2="23"/></svg></button>' +
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
  // На телефоне: кнопка стоит полной ровно 15 секунд (скролл в это время не считается),
  // и только потом первый скролл её сворачивает в компактную
  if (window.matchMedia("(max-width:600px)").matches) {
    var onScrollMini = function () {
      fab.classList.add("qc-mini");
      window.removeEventListener("scroll", onScrollMini);
    };
    setTimeout(function () {
      window.addEventListener("scroll", onScrollMini, { passive: true });
    }, 15000);
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
    if (who === "ai") {
      var spk = document.createElement("button");
      spk.className = "qc-spk";
      spk.setAttribute("aria-label", T.listen);
      spk.innerHTML = SPK_ICON + " " + T.listen;
      spk.addEventListener("click", function () { toggleSpeak(spk, text); });
      d.appendChild(document.createElement("br"));
      d.appendChild(spk);
    }
    body.appendChild(d);
    body.scrollTop = body.scrollHeight;
    return d;
  }

  // \u2500\u2500 \u041e\u0417\u0412\u0423\u0427\u041a\u0410 \u041e\u0422\u0412\u0415\u0422\u041e\u0412 \u2500\u2500
  var SPK_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>' +
    '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>';

  var curAudio = null, curBtn = null, curAbort = null;
  var ttsCache = {};   // текст -> готовый mp3 (Blob): повтор играет мгновенно

  function stopSpeak() {
    if (curAbort) { try { curAbort.abort(); } catch (e) {} curAbort = null; }
    if (curAudio) { try { curAudio.pause(); } catch (e) {} curAudio = null; }
    if (curBtn) { curBtn.classList.remove("playing"); curBtn = null; }
  }

  // Прогрев: как только ответ дописан — сразу тихо синтезируем его в кэш.
  // К моменту нажатия «Озвучить» звук уже готов, играет мгновенно.
  var warming = {};

  function prewarmTts(text) {
    if (!text || ttsCache[text] || warming[text]) return;
    warming[text] = (async function () {
      try {
        var res = await fetch(API.replace(/\/chat$/, "/tts"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: text, language: isRU ? "ru" : "en" }),
        });
        if (res.ok) {
          var blob = await res.blob();
          if (blob && blob.size) ttsCache[text] = blob;
        }
      } catch (e) { /* не вышло — озвучится по нажатию, как раньше */ }
      finally { delete warming[text]; }
    })();
  }

  function playBlob(blob, btn) {
    var audio = new Audio(URL.createObjectURL(blob));
    curAudio = audio;
    audio.onended = function () { if (curAudio === audio) stopSpeak(); };
    audio.onerror = function () { if (curAudio === audio) stopSpeak(); };
    audio.play().catch(function () { stopSpeak(); });
  }

  async function toggleSpeak(btn, text) {
    if (curBtn === btn) { stopSpeak(); return; }
    stopSpeak();
    curBtn = btn;
    btn.classList.add("playing");

    // Уже озвучивали этот ответ — играем из кэша, мгновенно и без сервера
    if (ttsCache[text]) { playBlob(ttsCache[text], btn); return; }
    // Прогрев ещё идёт — дожидаемся, второй синтез не запускаем
    if (warming[text]) {
      try { await warming[text]; } catch (e) {}
      if (curBtn !== btn) return;
      if (ttsCache[text]) { playBlob(ttsCache[text], btn); return; }
    }

    var url = API.replace(/\/chat$/, "/tts");
    curAbort = (typeof AbortController !== "undefined") ? new AbortController() : null;

    try {
      var res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, language: isRU ? "ru" : "en" }),
        signal: curAbort ? curAbort.signal : undefined,
      });
      if (!res.ok || !res.body) throw new Error("tts_failed");

      var canMse = (typeof MediaSource !== "undefined") &&
                   MediaSource.isTypeSupported && MediaSource.isTypeSupported("audio/mpeg");

      if (canMse) {
        var ms = new MediaSource();
        var audio = new Audio();
        curAudio = audio;
        audio.src = URL.createObjectURL(ms);
        var reader = res.body.getReader();
        var cacheParts = [];   // копим куски, чтобы повтор был мгновенным

        ms.addEventListener("sourceopen", function () {
          var sb = ms.addSourceBuffer("audio/mpeg");
          var queue = [], ended = false, appending = false;

          function pump() {
            if (appending || !queue.length || sb.updating) return;
            appending = true;
            try { sb.appendBuffer(queue.shift()); } catch (e) { appending = false; }
          }
          sb.addEventListener("updateend", function () {
            appending = false;
            if (!queue.length && ended) { try { ms.endOfStream(); } catch (e) {} }
            else pump();
          });

          (function read() {
            reader.read().then(function (r) {
              if (r.done) {
                ended = true;
                if (cacheParts.length) ttsCache[text] = new Blob(cacheParts, { type: "audio/mpeg" });
                if (!queue.length && !sb.updating) { try { ms.endOfStream(); } catch (e) {} }
                return;
              }
              cacheParts.push(r.value);
              queue.push(r.value);
              pump();
              read();
            }).catch(function () { ended = true; });
          })();
        });

        audio.onended = function () { if (curAudio === audio) stopSpeak(); };
        audio.onerror = function () { if (curAudio === audio) stopSpeak(); };
        await audio.play();
      } else {
        var blob = await res.blob();
        ttsCache[text] = blob;
        playBlob(blob, btn);
      }
    } catch (e) {
      stopSpeak();
    }
  }

  function submit() {
    if (dgOn) stopStream();
    if (micOn) stopMic();
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
        prewarmTts(reply);   // греем озвучку, пока человек читает
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

  // ── ГОЛОСОВОЙ ВВОД: микрофон горит, пока не выключишь. Текст прибавляется после каждой паузы ──
  var mic = panel.querySelector("#qc-mic");
  var micOn = false;                 // намерение человека: микрофон включён
  var recorder = null, chunks = [], recStream = null;
  var actx = null, vadTimer = null, maxTimer = null, busyStt = false;
  var segSpoke = false, segHasVad = false;   // была ли в отрезке живая речь

  if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder))
    mic.style.display = "none";

  function pickMime() {
    var list = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    for (var i = 0; i < list.length; i++)
      if (window.MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(list[i]))
        return list[i];
    return "";
  }
  function extFor(mime) {
    if (mime.indexOf("ogg") > -1) return "voice.ogg";
    if (mime.indexOf("mp4") > -1) return "voice.m4a";
    return "voice.webm";
  }

  function micRed(on) {
    if (on) {
      mic.classList.add("rec");
      mic.setAttribute("aria-label", T.micStop);
      mic.title = T.micStop;
    } else {
      mic.classList.remove("rec");
      mic.setAttribute("aria-label", T.micStart);
      mic.title = T.micStart;
    }
  }

  function killStream() {
    if (vadTimer) { clearInterval(vadTimer); vadTimer = null; }
    if (maxTimer) { clearTimeout(maxTimer); maxTimer = null; }
    if (actx) { try { actx.close(); } catch (e) {} actx = null; }
    if (recStream) {
      recStream.getTracks().forEach(function (t) { t.stop(); });
      recStream = null;
    }
  }

  // Один отрезок речи: пишем, пока не наступит тишина
  function recordSegment() {
    if (!micOn || !recStream) return;
    chunks = [];
    segSpoke = false;
    segHasVad = false;
    var mime = pickMime();
    try {
      recorder = mime ? new MediaRecorder(recStream, { mimeType: mime })
                      : new MediaRecorder(recStream);
    } catch (e) { stopMic(); addMsg(T.micFail, "ai"); return; }

    recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = function () { flushSegment(); };
    recorder.start(500);

    // Слежение за тишиной внутри отрезка
    if (vadTimer) clearInterval(vadTimer);
    try {
      if (!actx) {
        var AC = window.AudioContext || window.webkitAudioContext;
        actx = new AC();
      }
      var src = actx.createMediaStreamSource(recStream);
      var an = actx.createAnalyser();
      an.fftSize = 512;
      src.connect(an);
      var buf = new Uint8Array(an.fftSize);
      var quietFrom = null;
      segHasVad = true;
      vadTimer = setInterval(function () {
        an.getByteTimeDomainData(buf);
        var sum = 0;
        for (var i = 0; i < buf.length; i++) { var v = (buf[i] - 128) / 128; sum += v * v; }
        var rms = Math.sqrt(sum / buf.length);
        if (rms > 0.03) { segSpoke = true; quietFrom = null; }
        else if (segSpoke) {
          if (!quietFrom) quietFrom = Date.now();
          else if (Date.now() - quietFrom > 1800) {
            clearInterval(vadTimer); vadTimer = null;
            if (recorder && recorder.state !== "inactive") recorder.stop();
          }
        }
      }, 150);
    } catch (e) { /* без анализатора: отрезок закроется по потолку времени */ }

    if (maxTimer) clearTimeout(maxTimer);
    maxTimer = setTimeout(function () {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    }, 60000);
  }

  // Отрезок закончился: отправляем в Whisper, дописываем текст, слушаем дальше
  async function flushSegment() {
    var mime = (recorder && recorder.mimeType) || "audio/webm";
    var blob = new Blob(chunks, { type: mime });
    chunks = [];

    // Тишину в Whisper не шлём — он на ней фантазирует («спасибо», «продолжение следует»)
    if (blob.size < 1200 || (segHasVad && !segSpoke)) {
      if (micOn) recordSegment();
      return;
    }

    busyStt = true;
    var savedPh = T.micListen;
    input.placeholder = T.micWait;
    try {
      var fd = new FormData();
      fd.append("file", blob, extFor(mime));
      fd.append("language", isRU ? "ru" : "en");
      var res = await fetch(API.replace(/\/chat$/, "/transcribe"), { method: "POST", body: fd });
      var data = await res.json();
      if (data && data.text) {
        input.value = (input.value ? input.value.trim() + " " : "") + data.text;
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 100) + "px";
      }
    } catch (e) {
      addMsg(T.micFail, "ai");
    } finally {
      busyStt = false;
      input.placeholder = micOn ? savedPh : T.placeholder;
      if (micOn) recordSegment();           // микрофон по-прежнему горит — слушаем дальше
    }
  }

  async function startMic() {
    if (micOn) return;
    try {
      recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) { addMsg(T.micDenied, "ai"); return; }
    micOn = true;
    micRed(true);
    input.placeholder = T.micListen;
    recordSegment();
  }

  function stopMic() {
    micOn = false;
    if (vadTimer) { clearInterval(vadTimer); vadTimer = null; }
    if (maxTimer) { clearTimeout(maxTimer); maxTimer = null; }
    if (recorder && recorder.state !== "inactive") {
      try { recorder.stop(); } catch (e) {}   // последний отрезок ещё распознается
    }
    micRed(false);
    if (!busyStt) input.placeholder = T.placeholder;
    setTimeout(killStream, 500);
    input.focus();
  }

  // ── ЖИВОЕ РАСПОЗНАВАНИЕ ЧЕРЕЗ DEEPGRAM (текст идёт во время речи) ──
  // Звук уходит в вебсокет сырым PCM 16 кГц — как в конвейере Оракула.
  var WS_URL = API.replace(/^http/, "ws").replace(/\/chat$/, "/stt-stream");
  var dgWs = null, dgCtx = null, dgProc = null, dgStream = null, dgSrc = null;
  var dgOn = false, dgBase = "", dgFinal = "", dgReady = false;

  function resampleTo16k(input, rate) {
    if (rate === 16000) return input;
    var ratio = rate / 16000;
    var out = new Float32Array(Math.round(input.length / ratio));
    for (var i = 0; i < out.length; i++) out[i] = input[Math.floor(i * ratio)] || 0;
    return out;
  }

  function paintLive(interim) {
    var t = (dgFinal + (interim ? " " + interim : "")).replace(/\s+/g, " ").trim();
    input.value = (dgBase ? dgBase + " " : "") + t;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  }

  async function startStream() {
    try {
      dgStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) { addMsg(T.micDenied, "ai"); return false; }

    try {
      dgWs = new WebSocket(WS_URL + "?lang=" + (isRU ? "ru" : "en"));
      dgWs.binaryType = "arraybuffer";
    } catch (e) { killStream(); return false; }

    dgBase = input.value.trim();
    dgFinal = "";
    dgReady = false;

    // Ждём от сервера подтверждения "ready" — значит, Deepgram реально на связи.
    // Пришла ошибка или тишина — уходим на запасной путь (Whisper).
    var ready = await new Promise(function (resolve) {
      var done = false;
      var finish = function (v) { if (!done) { done = true; clearTimeout(t); resolve(v); } };
      var t = setTimeout(function () { finish(false); }, 6000);
      dgWs.onopen = function () {};
      dgWs.onerror = function () { finish(false); };
      dgWs.onclose = function () { finish(false); };
      dgWs.onmessage = function (ev) {
        var d;
        try { d = JSON.parse(ev.data); } catch (e) { return; }
        if (d.type === "ready") finish(true);
        else if (d.type === "error") finish(false);
      };
    });
    if (!ready) {
      try { if (dgWs) dgWs.close(); } catch (e) {}
      dgWs = null;
      if (dgStream) { dgStream.getTracks().forEach(function (t) { t.stop(); }); dgStream = null; }
      return false;
    }

    dgWs.onmessage = function (ev) {
      var d;
      try { d = JSON.parse(ev.data); } catch (e) { return; }
      if (d.type !== "transcript") return;
      dgReady = true;
      if (d.final) { dgFinal = (dgFinal + " " + d.text).trim(); paintLive(""); }
      else paintLive(d.text);
    };
    dgWs.onerror = function () {};
    dgWs.onclose = function () { if (dgOn) stopStream(); };

    var AC = window.AudioContext || window.webkitAudioContext;
    try { dgCtx = new AC({ sampleRate: 16000 }); } catch (e) { dgCtx = new AC(); }
    dgSrc = dgCtx.createMediaStreamSource(dgStream);
    dgProc = dgCtx.createScriptProcessor(4096, 1, 1);
    dgProc.onaudioprocess = function (e) {
      if (!dgOn || !dgWs || dgWs.readyState !== WebSocket.OPEN) return;
      var raw = e.inputBuffer.getChannelData(0);
      if (!raw || !raw.length) return;
      var pcm = resampleTo16k(raw, dgCtx.sampleRate);
      var buf = new Int16Array(pcm.length);
      for (var i = 0; i < pcm.length; i++) {
        var v = Math.max(-1, Math.min(1, pcm[i]));
        buf[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
      }
      try { dgWs.send(buf.buffer); } catch (err) {}
    };
    dgSrc.connect(dgProc);
    dgProc.connect(dgCtx.destination);

    dgOn = true;
    micRed(true);
    input.placeholder = T.micListen;
    return true;
  }

  function stopStream() {
    dgOn = false;
    try { if (dgWs && dgWs.readyState === WebSocket.OPEN) dgWs.send("stop"); } catch (e) {}
    setTimeout(function () { try { if (dgWs) dgWs.close(); } catch (e) {} dgWs = null; }, 300);
    if (dgProc) { try { dgProc.disconnect(); } catch (e) {} dgProc = null; }
    if (dgSrc) { try { dgSrc.disconnect(); } catch (e) {} dgSrc = null; }
    if (dgCtx) { try { dgCtx.close(); } catch (e) {} dgCtx = null; }
    if (dgStream) { dgStream.getTracks().forEach(function (t) { t.stop(); }); dgStream = null; }
    micRed(false);
    input.placeholder = T.placeholder;
    input.focus();
  }

  mic.addEventListener("click", async function () {
    if (dgOn) { stopStream(); return; }
    if (micOn) { stopMic(); return; }
    mic.disabled = true;
    var ok = false;
    try { ok = await startStream(); }   // сначала пробуем живой поток
    catch (e) { ok = false; }
    finally { mic.disabled = false; }   // кнопка не залипнет ни при какой ошибке
    if (!ok) { try { await startMic(); } catch (e) {} }  // запасной путь — Whisper
  });

  send.addEventListener("click", submit);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  });
})();
