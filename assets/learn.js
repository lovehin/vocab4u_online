/* ============================================================
   随浪背单词 · 学习器
   ------------------------------------------------------------
   五种模式：卡牌速览 / 打字默写 / 听写辨词 / 例句填空 / 选择题
   记忆算法：简化版 Leitner + ease（间隔 1/2/4/7/15/30/60 天）
   所有进度存在 localStorage，不上传、不需要账号。
   ============================================================ */
(function () {
  'use strict';

  var SHARD = 500;                 // 与 build/gen.py 的 SHARD 保持一致
  var INTERVALS = [0, 1, 2, 4, 7, 15, 30, 60];
  var K = {
    progress: 'v4u.progress.v1', meta: 'v4u.meta.v1',
    star: 'v4u.star.v1', prefs: 'v4u.prefs.v1'
  };
  var MODES = [
    ['card', '卡牌速览', '看词想意思，自己判断认不认识'],
    ['typing', '打字默写', '看中文敲英文，练拼写'],
    ['dictation', '听写辨词', '听发音敲单词'],
    ['cloze', '例句填空', '在句子里把词填回去'],
    ['choice', '选择题', '四选一，快速过词']
  ];

  /* ---------------- 存储 ---------------- */
  function read(key, fallback) {
    try { var raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; }
    catch (e) { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch (e) { toast('浏览器存储写不进去了，可能空间满了'); return false; }
  }
  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }
  function addDays(dateStr, n) {
    var parts = dateStr.split('-');
    var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    d.setDate(d.getDate() + n);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }

  var progress = read(K.progress, {});
  var stars = read(K.star, []);
  var meta = read(K.meta, {});
  var prefs = read(K.prefs, {});
  var booksData = null, books = [], bookList = null, shards = {};
  var state = {
    book: prefs.book || 'cet4', mode: prefs.mode || 'card',
    goal: prefs.goal || 20, group: prefs.group || 10, onlyNew: !!prefs.onlyNew
  };
  var session = null;

  /* ---------------- 小工具 ---------------- */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function toast(text) {
    var box = $('#toast');
    if (!box) { return; }
    box.textContent = text;
    box.classList.add('show');
    clearTimeout(box._t);
    box._t = setTimeout(function () { box.classList.remove('show'); }, 1900);
  }
  function say(text, kind) { if (window.V4U) { window.V4U.speak(text, kind); } }

  /* ---------------- 数据加载 ---------------- */
  function bookInfo(slug) {
    for (var i = 0; i < books.length; i++) { if (books[i].slug === slug) { return books[i]; } }
    return null;
  }
  function currentBook() { return bookInfo(state.book) || books[0]; }

  function loadShard(slug, n) {
    var key = slug + '.' + n;
    if (shards[key]) { return Promise.resolve(shards[key]); }
    return fetch('/data/words/' + slug + '.' + n + '.json').then(function (res) {
      if (!res.ok) { throw new Error('词库分片加载失败：' + key); }
      return res.json();
    }).then(function (data) {
      var map = {};
      data.words.forEach(function (w) { map[w.s] = w; });
      shards[key] = map;
      return map;
    });
  }

  function wordsFor(slugs) {
    var book = currentBook();
    var need = {};
    slugs.forEach(function (s) {
      var pos = book.lookup[s];
      if (pos === undefined) { return; }
      need[Math.floor(pos / SHARD) + 1] = true;
    });
    var nums = Object.keys(need).map(Number).sort(function (a, b) { return a - b; });
    return Promise.all(nums.map(function (n) { return loadShard(book.slug, n); }))
      .then(function (maps) {
        var out = [];
        slugs.forEach(function (s) {
          for (var i = 0; i < maps.length; i++) {
            if (maps[i][s]) { out.push(maps[i][s]); return; }
          }
        });
        return out;
      });
  }

  /* ---------------- 记忆算法 ---------------- */
  function entryOf(slug) {
    if (!progress[slug]) {
      progress[slug] = { b: 0, e: 2.5, d: today(), s: 0, r: 0, w: 0, t: '' };
    }
    return progress[slug];
  }

  function grade(slug, quality) {
    var p = entryOf(slug);
    if (quality >= 2) {
      p.b = Math.min(6, p.b + 1);
      p.e = Math.min(2.8, p.e + 0.08);
    } else if (quality === 1) {
      p.b = Math.max(1, Math.min(p.b, 3));
      p.e = Math.max(1.3, p.e - 0.12);
    } else {
      p.b = 0;
      p.e = Math.max(1.3, p.e - 0.25);
    }
    var days = INTERVALS[p.b];
    if (quality >= 2) { days = Math.max(1, Math.round(days * (p.e / 2.5))); }
    p.d = quality === 0 ? today() : addDays(today(), days);
    p.s += 1;
    p.t = today();
    if (quality >= 2) { p.r += 1; } else { p.w += 1; }
    saveProgress();
    bumpMeta(quality >= 2);
  }

  function saveProgress() { write(K.progress, progress); }

  function bumpMeta(ok) {
    var key = today();
    meta.history = meta.history || {};
    if (meta.lastDay !== key) {
      meta.streak = (meta.lastDay && addDays(meta.lastDay, 1) === key) ? (meta.streak || 0) + 1 : 1;
      meta.lastDay = key;
      meta.today = { n: 0, ok: 0 };
    }
    meta.today = meta.today || { n: 0, ok: 0 };
    meta.today.n += 1;
    if (ok) { meta.today.ok += 1; }
    meta.history[key] = meta.today;
    write(K.meta, meta);
  }

  function dueWords(book) {
    var out = [];
    var key = today();
    book.words.forEach(function (s) {
      var p = progress[s];
      if (p && p.d && p.d <= key) { out.push(s); }
    });
    return out;
  }

  function currentGoal() {
    var n = Number($('#goal') ? $('#goal').value : state.goal) || state.goal;
    return n;
  }

  /* ---------------- 会话 ---------------- */
  function buildQueue(kind) {
    var book = currentBook();
    var key = today();
    var queue = [];

    if (kind === 'review') {
      queue = dueWords(book);
      if (!queue.length) { toast('暂时没有到期的复习，先学点新词吧'); return Promise.resolve([]); }
      return wordsFor(queue.slice(0, Math.max(10, currentGoal() * 2)));
    }

    var pool = state.onlyNew && book.newWords && book.newWords.length ? book.newWords : book.words;
    var due = dueWords(book).slice(0, currentGoal());
    due.forEach(function (s) { queue.push(s); });

    var fresh = [];
    for (var i = 0; i < pool.length && fresh.length < currentGoal(); i++) {
      var s = pool[i];
      if (queue.indexOf(s) >= 0) { continue; }
      var p = progress[s];
      if (!p || (!p.s && (!p.b || p.b === 0))) { fresh.push(s); }
    }
    if (!fresh.length && !queue.length) {
      // 这本书的新词学完了，改成复习
      queue = dueWords(book).slice(0, currentGoal() * 2);
      if (!queue.length) {
        for (var j = 0; j < pool.length && queue.length < currentGoal(); j++) { queue.push(pool[j]); }
        toast('这本词书已经过了一遍，再来一轮巩固');
      }
    }
    var all = due.concat(fresh);
    if (kind === 'single' || !all.length) { all = fresh.length ? fresh : pool.slice(0, 1); }
    return wordsFor(all);
  }

  function startSession(words, mode) {
    if (!words.length) { return; }
    session = {
      mode: mode, idx: 0, words: words, right: 0, wrong: 0,
      start: Date.now(), retry: false, answered: false, badThis: false
    };
    $('#setup').hidden = true;
    $('#summary').hidden = true;
    $('#session').hidden = false;
    $('#mode-name').textContent = modeName(mode);
    render();
  }

  function modeName(slug) {
    for (var i = 0; i < MODES.length; i++) { if (MODES[i][0] === slug) { return MODES[i][1]; } }
    return '';
  }

  function endSession() {
    var elapsed = Math.round((Date.now() - session.start) / 1000);
    var total = session.right + session.wrong;
    var acc = total ? Math.round(session.right * 100 / total) : 0;
    var mastered = 0, learning = 0, fresh = 0;
    Object.keys(progress).forEach(function (s) {
      var b = progress[s].b;
      if (b >= 5) { mastered += 1; } else if (b >= 1) { learning += 1; } else { fresh += 1; }
    });
    var total_words = currentBook().count;
    $('#session').hidden = true;
    var sum = $('#summary');
    sum.hidden = false;
    sum.innerHTML =
      '<h2>这一轮结束了</h2>' +
      '<div class="result-grid">' +
      '<div><b>' + total + '</b>练习次数</div>' +
      '<div><b>' + acc + '%</b>正确率</div>' +
      '<div><b>' + Math.max(1, Math.round(elapsed / 60)) + '</b>分钟</div>' +
      '<div><b>' + (meta.streak || 1) + '</b>连续天数</div>' +
      '</div>' +
      '<h3 style="margin-top:22px">整本书的掌握情况（' + esc(currentBook().name) + ' ' + total_words + ' 词）</h3>' +
      '<div class="meter" aria-hidden="true">' +
      '<i style="background:#0e9f7d;width:' + (mastered * 100 / total_words) + '%"></i>' +
      '<i style="background:#2f6fe4;width:' + (learning * 100 / total_words) + '%"></i>' +
      '<i style="background:#cdd7e6;width:' + (fresh * 100 / total_words) + '%"></i>' +
      '</div>' +
      '<p class="hint">已掌握 ' + mastered + ' · 学习中 ' + learning + ' · 还没开始 ' + fresh + '</p>' +
      '<div class="stage-actions">' +
      '<button class="btn btn-primary" id="again">再来一组</button>' +
      '<button class="btn" id="back-home">回到设置</button>' +
      '<button class="btn btn-ghost" id="to-review">只复习错词</button>' +
      '</div>';
    $('#again').onclick = function () { sum.hidden = true; $('#setup').hidden = false; refreshDashboard(); };
    $('#back-home').onclick = function () { sum.hidden = true; $('#setup').hidden = false; refreshDashboard(); };
    $('#to-review').onclick = function () {
      var marks = Object.keys(progress).filter(function (s) { return progress[s].w > progress[s].r; });
      startSessionFromSlugs(marks.slice(0, 20), session.mode);
    };
    refreshDashboard();
  }

  function startSessionFromSlugs(slugs, mode) {
    wordsFor(slugs).then(function (words) {
      if (!words.length) { toast('没有找到可练的词'); return; }
      startSession(words, mode);
    });
  }

  function nextWord() {
    session.idx += 1;
    session.retry = false;
    session.answered = false;
    session.badThis = false;
    if (session.idx >= session.words.length) { endSession(); return; }
    render();
  }

  function repeatLater(word) {
    session.words.push(word);
  }

  function record(ok, quality) {
    var word = session.words[session.idx];
    if (ok) { session.right += 1; } else { session.wrong += 1; }
    grade(word.s, quality);
    if (quality === 0) { repeatLater(word); }
  }

  /* ---------------- 渲染 ---------------- */
  function render() {
    var word = session.words[session.idx];
    if (!word) { endSession(); return; }
    $('#progress-text').textContent = (session.idx + 1) + ' / ' + session.words.length;
    $('#progress-bar').style.width = (session.idx * 100 / session.words.length) + '%';
    var stage = $('#stage');
    stage.innerHTML = '';
    if (session.mode === 'card') { renderCard(stage, word); }
    else if (session.mode === 'typing') { renderTyping(stage, word); }
    else if (session.mode === 'dictation') { renderDictation(stage, word); }
    else if (session.mode === 'cloze') { renderCloze(stage, word); }
    else { renderChoice(stage, word); }
  }

  function ipaLine(word) {
    var ipa = word.u || word.k || '';
    return '<div class="quiz-ipa">' + esc(ipa) +
      ' <button class="speak" type="button" data-say="' + esc(word.w) + '" data-type="2" aria-label="朗读">🔊</button></div>';
  }

  function transText(word) {
    return (word.t || []).join('；') || '（暂无中文释义）';
  }

  function renderCard(stage, word) {
    stage.innerHTML =
      '<div class="big-word">' + esc(word.w) + '</div>' + ipaLine(word) +
      '<div id="back" hidden><p class="quiz-trans">' + esc(transText(word)) + '</p>' +
      (word.e && word.e[0] ? '<p class="sent-zh">' + esc(word.e[0][0]) + '<br>' + esc(word.e[0][1]) + '</p>' : '') +
      '</div>' +
      '<div class="stage-actions" id="front-actions">' +
      '<button class="btn btn-primary" id="flip">显示释义（空格）</button>' +
      '</div>' +
      '<div class="grade-row" id="grade" hidden>' +
      '<button class="btn" data-g="3">认识（1）</button>' +
      '<button class="btn" data-g="1">模糊（2）</button>' +
      '<button class="btn" data-g="0">不认识（3）</button>' +
      '</div>';
    say(word.w, '2');
    $('#flip').onclick = flip;
    $$('#grade [data-g]').forEach(function (btn) {
      btn.onclick = function () { answerCard(Number(btn.getAttribute('data-g'))); };
    });
    function flip() {
      $('#back').hidden = false;
      $('#front-actions').hidden = true;
      $('#grade').hidden = false;
    }
    stage._flip = flip;
    stage._answer = answerCard;
  }

  function answerCard(quality) {
    var word = session.words[session.idx];
    record(quality > 0, quality);
    nextWord();
  }

  function typingStage(word, prompt, autoPlay, showIpa) {
    var stage = $('#stage');
    stage.innerHTML =
      prompt + (showIpa === false ? '' : ipaLine(word)) +
      '<input class="answer-input" id="answer" autocomplete="off" autocorrect="off" ' +
      'autocapitalize="off" spellcheck="false" aria-label="输入英文单词">' +
      '<div class="diff" id="diff" aria-live="polite"></div>' +
      '<p class="hint" id="hint">回车提交 · 空格重听发音</p>' +
      '<div class="stage-actions"><button class="btn" id="give-up">看答案</button></div>';
    var input = $('#answer');
    input.focus();
    if (autoPlay) { say(word.w, '2'); }
    return input;
  }

  function norm(s) {
    return String(s || '').trim().toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, ' ');
  }

  function diffHTML(input, answer) {
    var a = norm(answer), b = norm(input);
    var out = '';
    var i = 0;
    while (i < b.length && i < a.length && a[i] === b[i]) { i += 1; }
    out += '<span class="ok">' + esc(answer.slice(0, i)) + '</span>';
    if (b.length > i) { out += '<span class="no">' + esc(input.slice(i, i + (b.length - i))) + '</span>'; }
    out += '<span class="rest">' + esc(answer.slice(i)) + '</span>';
    return out;
  }

  function submitTyping(word) {
    var input = $('#answer');
    var value = norm(input.value);
    if (!value) { return; }
    var answer = norm(word.w);
    if (value === answer) {
      if (session.retry) { session.retry = false; }
      input.classList.add('ok');
      $('#diff').innerHTML = '<span class="ok">' + esc(word.w) + '</span> ✓';
      session.answered = true;
      setTimeout(function () { record(true, 2); nextWord(); }, 420);
      return;
    }
    input.classList.add('bad');
    $('#diff').innerHTML = diffHTML(input.value, word.w) +
      ' <span class="hint">（照着上面的正确拼写再打一遍就算过）</span>';
    session.retry = true;
    if (!session.badThis) { record(false, 0); session.badThis = true; }
    $('#hint').innerHTML = '再打一遍正确的拼写：<b>' + esc(word.w) + '</b>';
    say(word.w, '2');
    // 清空刚才打错的内容，让用户直接重打；不清空的话会跟旧字母混在一起打不出来
    input.value = '';
    input.classList.remove('bad');
    input.focus();
  }

  function renderTyping(stage, word) {
    var prompt = '<p class="quiz-trans">' + esc(transText(word)) + '</p>' +
      '<p class="hint">看中文，敲出英文单词</p>';
    var input = typingStage(word, prompt, false);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); submitTyping(word); }
    });
    $('#give-up').onclick = function () {
      $('#hint').innerHTML = '正确拼写：<b>' + esc(word.w) + '</b>（再打一遍）';
      session.retry = true;
      if (!session.badThis) { record(false, 0); session.badThis = true; }
      input.value = '';
      input.focus();
    };
  }

  function renderDictation(stage, word) {
    var prompt = '<p class="hint">听发音，写出这个单词（可以反复听；答案揭晓前不显示音标）</p>';
    var input = typingStage(word, prompt, true, false);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); submitTyping(word); }
    });
    $('#give-up').onclick = function () {
      $('#hint').innerHTML = '正确拼写：<b>' + esc(word.w) + '</b>（再打一遍）';
      session.retry = true;
      if (!session.badThis) { record(false, 0); session.badThis = true; }
      say(word.w, '2');
      input.value = '';
      input.focus();
    };
  }

  function clozeSentence(word) {
    var sentences = word.e || [];
    var stem = norm(word.w).replace(/[^a-z]/g, '');
    for (var i = 0; i < sentences.length; i++) {
      var en = sentences[i][0] || '';
      var re = new RegExp('\\b(' + stem + '\\w{0,3})\\b', 'i');
      if (stem && re.test(en)) {
        return { en: en.replace(re, '______'), zh: sentences[i][1], hit: en.match(re)[1] };
      }
    }
    return null;
  }

  function renderCloze(stage, word) {
    var found = clozeSentence(word);
    if (!found) { renderTyping(stage, word); return; }
    var prompt = '<p class="blank-sent">' + esc(found.en) + '</p>' +
      '<p class="sent-zh">' + esc(found.zh) + '</p>' +
      '<p class="hint">把空填上（原形即可）</p>';
    var input = typingStage(word, prompt, false);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); submitTyping(word); }
    });
    $('#give-up').onclick = function () {
      $('#hint').innerHTML = '正确答案：<b>' + esc(word.w) + '</b>（再打一遍）';
      session.retry = true;
      if (!session.badThis) { record(false, 0); session.badThis = true; }
      input.value = '';
      input.focus();
    };
  }

  function distractors(word, n) {
    var pool = [];
    Object.keys(shards).forEach(function (key) {
      Object.keys(shards[key]).forEach(function (slug) {
        if (slug !== word.s) { pool.push(shards[key][slug]); }
      });
    });
    for (var i = pool.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = pool[i]; pool[i] = pool[j]; pool[j] = t;
    }
    return pool.slice(0, n);
  }

  function renderChoice(stage, word) {
    var toChinese = Math.random() < 0.5;
    var others = distractors(word, 3);
    if (others.length < 3) { renderTyping(stage, word); return; }
    var options = [{ w: word, right: true }].concat(others.map(function (w) { return { w: w, right: false }; }));
    for (var i = options.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = options[i]; options[i] = options[j]; options[j] = t;
    }
    var q = toChinese
      ? '<div class="quiz-word">' + esc(word.w) + '</div>' + ipaLine(word) +
        '<p class="hint">选出正确的中文意思</p>'
      : '<p class="quiz-trans">' + esc(transText(word)) + '</p><p class="hint">选出对应的英文单词</p>';
    stage.innerHTML = q + '<div class="choices" id="choices"></div>' +
      '<p class="hint">按数字键 1–4 也可以选</p>';
    var box = $('#choices');
    options.forEach(function (opt, idx) {
      var btn = document.createElement('button');
      btn.className = 'choice';
      btn.innerHTML = '<span class="k">' + (idx + 1) + '</span><span>' +
        esc(toChinese ? transText(opt.w) : opt.w.w) + '</span>';
      btn.onclick = function () { pick(btn, opt); };
      box.appendChild(btn);
    });
    stage._pick = pick;
    function pick(btn, opt) {
      if (session.answered) { return; }
      session.answered = true;
      $$('#choices .choice').forEach(function (b) { b.disabled = true; });
      if (opt.right) {
        btn.classList.add('right');
        record(true, session.idx < 3 ? 3 : 2);
        setTimeout(nextWord, 420);
      } else {
        btn.classList.add('wrong');
        $$('#choices .choice').forEach(function (b, i) { if (options[i].right) { b.classList.add('right'); } });
        record(false, 0);
        say(word.w, '2');
        setTimeout(nextWord, 1100);
      }
    }
  }

  /* ---------------- 键盘 ---------------- */
  document.addEventListener('keydown', function (e) {
    var tag0 = (e.target.tagName || '').toLowerCase();
    var typing0 = tag0 === 'input' || tag0 === 'textarea' || e.target.isContentEditable;
    if (!typing0 && e.key === '?') { e.preventDefault(); toggleKbdHelp(); return; }
    if (e.key === 'Escape') {
      var box = $('#kbd-help');
      if (box && !box.hidden) { e.preventDefault(); box.hidden = true; return; }
    }
    if (!session || $('#session').hidden) { return; }
    var tag = (e.target.tagName || '').toLowerCase();
    var typing = tag === 'input';
    if (session.mode === 'card') {
      // 按 1/2/3 直接评分，不必先按空格翻牌（1 认识 / 2 模糊 / 3 不认识）
      if (['1', '2', '3'].indexOf(e.key) >= 0) {
        e.preventDefault();
        answerCard(Number([3, 1, 0][Number(e.key) - 1]));
        return;
      }
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        var stage = $('#stage');
        if ($('#grade').hidden && stage._flip) { stage._flip(); }
      }
      return;
    }
    var 当前词 = session.words[session.idx];
    if (!当前词) { return; }
    // 空格＝重听发音。打字 / 填空时也在输入框里拦下来：本站的词都不含空格，
    // 所以输入框里的空格没有别的作用（真要遇到带空格的词就放行，别挡着打）。
    if (e.code === 'Space' && (!typing || 当前词.w.indexOf(' ') < 0)) {
      e.preventDefault();
      say(当前词.w, '2');
      return;
    }
    if (session.mode === 'choice' && !typing && ['1', '2', '3', '4'].indexOf(e.key) >= 0) {
      var btns = $$('#choices .choice');
      var btn = btns[Number(e.key) - 1];
      if (btn) { e.preventDefault(); btn.click(); }
    }
  });

  /* ---------------- 设置面板与统计 ---------------- */
  /* ---------------- 快捷键说明（按 ? 开关，Esc 收起） ---------------- */
  var 快捷键 = [
    ['空格', '发音（打字时也是发音）；卡牌翻牌'],
    ['回车', '提交答案 / 下一个'],
    ['1 2 3', '卡牌评分：1 认识 / 2 模糊 / 3 不认识'],
    ['1–4', '选择题直接选第几个'],
    ['?', '打开或收起这份说明'],
    ['Esc', '收起说明']
  ];

  function toggleKbdHelp() {
    var box = $('#kbd-help');
    if (!box) {
      box = document.createElement('div');
      box.className = 'kbd-help';
      box.id = 'kbd-help';
      box.setAttribute('role', 'dialog');
      box.setAttribute('aria-label', '键盘快捷键');
      box.innerHTML = '<h3>键盘快捷键</h3><table><tbody>' +
        快捷键.map(function (row) {
          return '<tr><td><kbd>' + esc(row[0]) + '</kbd></td><td>' + esc(row[1]) + '</td></tr>';
        }).join('') + '</tbody></table>' +
        '<p>打字的时候，空格键用来重听发音，不会往输入框里打空格。</p>' +
        '<button class="kbd-close" type="button" aria-label="关闭">×</button>';
      box.querySelector('.kbd-close').onclick = function () { box.hidden = true; };
      document.body.appendChild(box);
      box.hidden = false;
      return;
    }
    box.hidden = !box.hidden;
  }

  function refreshDashboard() {
    var book = currentBook();
    var due = dueWords(book).length;
    var learned = 0, mastered = 0;
    book.words.forEach(function (s) {
      var p = progress[s];
      if (!p) { return; }
      if (p.s) { learned += 1; }
      if (p.b >= 5) { mastered += 1; }
    });
    var t = meta.today || { n: 0, ok: 0 };
    var acc = t.n ? Math.round(t.ok * 100 / t.n) : 0;
    $('#dashboard').innerHTML =
      '<div class="result-grid">' +
      '<div><b>' + learned + '</b>已学（' + esc(book.name) + '）</div>' +
      '<div><b>' + due + '</b>待复习</div>' +
      '<div><b>' + mastered + '</b>已掌握</div>' +
      '<div><b>' + (meta.streak || 0) + '</b>连续天数</div>' +
      '</div>' +
      '<p class="hint" style="margin-top:12px">今天已练 ' + t.n + ' 次，正确率 ' + acc + '%</p>';
  }

  function renderChips() {
    var bookBox = $('#book-chips');
    bookBox.innerHTML = '';
    books.forEach(function (b) {
      var btn = document.createElement('button');
      btn.className = 'chip';
      btn.type = 'button';
      btn.textContent = b.name + '（' + b.count + '）';
      btn.setAttribute('aria-pressed', b.slug === state.book ? 'true' : 'false');
      btn.onclick = function () {
        state.book = b.slug;
        buildLookup(b);
        renderChips();
        refreshDashboard();
        savePrefs();
      };
      bookBox.appendChild(btn);
    });
    var modeBox = $('#mode-chips');
    modeBox.innerHTML = '';
    MODES.forEach(function (m) {
      var btn = document.createElement('button');
      btn.className = 'chip';
      btn.type = 'button';
      btn.textContent = m[1];
      btn.title = m[2];
      btn.setAttribute('aria-pressed', m[0] === state.mode ? 'true' : 'false');
      btn.onclick = function () { state.mode = m[0]; renderChips(); savePrefs(); };
      modeBox.appendChild(btn);
    });
  }

  function buildLookup(book) {
    if (book.lookup) { return; }
    book.lookup = {};
    book.words.forEach(function (s, i) { book.lookup[s] = i; });
  }

  function savePrefs() {
    prefs = { book: state.book, mode: state.mode, goal: currentGoal(),
              group: Number($('#group') ? $('#group').value : state.group) || state.group,
              onlyNew: $('#only-new') ? $('#only-new').checked : state.onlyNew,
              voice: $('#voice') ? $('#voice').value : (prefs.voice || 'auto'),
              voiceName: $('#voice-name') ? $('#voice-name').value : (prefs.voiceName || '') };
    write(K.prefs, prefs);
  }

  /* ---------------- 导出 ---------------- */
  function download(name, text) {
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function exportWords(scope) {
    var book = currentBook();
    var slugs = scope === 'star' ? stars : (scope === 'unlearned' ? book.words : book.words);
    return wordsFor(scope === 'star' ? slugs.slice(0, 500) : slugs.slice(0, 3000));
  }

  function ankiText(words) {
    var lines = ['#separator:tab', '#html:false',
                 '#columns:单词\t音标\t中文释义\t例句'];
    words.forEach(function (w) {
      var ex = (w.e && w.e[0]) ? w.e[0][0] : '';
      lines.push([w.w, w.u || w.k || '', (w.t || []).join('；'), ex].join('\t'));
    });
    return lines.join('\n');
  }

  function csvText(words) {
    var out = ['单词,音标,中文释义'];
    words.forEach(function (w) {
      var row = [w.w, w.u || w.k || '', (w.t || []).join('；')].map(function (x) {
        return '"' + String(x).replace(/"/g, '""') + '"';
      });
      out.push(row.join(','));
    });
    return out.join('\n');
  }

  /* ---------------- 浏览器语音列表 ---------------- */
  function fillVoiceOptions() {
    var box = $('#voice-name');
    if (!box || !window.V4U || !V4U.englishVoices) { return; }
    var paint = function () {
      var list = V4U.englishVoices() || [];
      var 当前 = V4U.currentVoice && V4U.currentVoice();
      var html = '<option value="">自动挑一个（推荐）</option>';
      list.sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
      list.forEach(function (v) {
        html += '<option value="' + esc(v.name) + '">' + esc(v.name) + '（' + esc(v.lang) + '）' +
          (当前 && 当前.name === v.name ? ' ← 当前用的' : '') + '</option>';
      });
      box.innerHTML = html;
      box.value = prefs.voiceName || '';
      if (box.value !== (prefs.voiceName || '')) { box.value = ''; }
    };
    paint();
    if (V4U.whenVoicesReady) { V4U.whenVoicesReady(paint); }
  }

  function 试听() {
    if (window.V4U && V4U.speak) {
      V4U.speak('This is the voice you will hear for sentences.', 'browser');
    }
  }

  /* ---------------- 启动 ---------------- */
  function bindUI() {
    $('#start').onclick = function () {
      savePrefs();
      buildQueue('plan').then(function (words) {
        if (!words.length) { toast('没有可学的词了'); return; }
        startSession(words, state.mode);
      });
    };
    $('#review').onclick = function () {
      buildQueue('review').then(function (words) {
        if (words.length) { startSession(words, state.mode); }
      });
    };
    $('#open-settings').onclick = function () { $('#settings').hidden = false; };
    $('#close-settings').onclick = function () { $('#settings').hidden = true; };
    $('#goal').onchange = savePrefs;
    $('#only-new').onchange = savePrefs;
    $('#group').onchange = savePrefs;
    $('#voice').onchange = savePrefs;
    $('#voice-name').onchange = function () { savePrefs(); 试听(); };
    $('#try-voice').onclick = 试听;
    $('#export-progress').onclick = function () {
      download('vocab4u-progress.json', JSON.stringify({ progress: progress, meta: meta, stars: stars }));
    };
    $('#import-progress').onclick = function () { $('#import-file').click(); };
    $('#import-file').onchange = function (e) {
      var file = e.target.files[0];
      if (!file) { return; }
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var data = JSON.parse(reader.result);
          progress = data.progress || progress;
          meta = data.meta || meta;
          stars = data.stars || stars;
          write(K.progress, progress); write(K.meta, meta); write(K.star, stars);
          refreshDashboard();
          toast('进度已导入');
        } catch (err) { toast('导入失败：文件读不出来'); }
      };
      reader.readAsText(file);
    };
    $('#export-anki').onclick = function () {
      exportWords('all').then(function (words) {
        download('vocab4u-anki.txt', ankiText(words));
        download('vocab4u-' + currentBook().slug + '.csv', csvText(words));
        toast('已导出 ' + words.length + ' 个词（Anki 用 tab 分隔的 txt）');
      });
    };
    $('#print-list').onclick = function () {
      window.open('/list/' + currentBook().slug, '_blank');
    };
  }

  function boot() {
    fetch('/data/books.json').then(function (r) { return r.json(); }).then(function (data) {
      booksData = data;
      books = data.books;
      var params = new URLSearchParams(location.search);
      if (params.get('book') && bookInfo(params.get('book'))) { state.book = params.get('book'); }
      if (params.get('mode')) { state.mode = params.get('mode'); }
      books.forEach(buildLookup);
      if (prefs.goal) { $('#goal').value = String(prefs.goal); }
      if (prefs.group) { $('#group').value = String(prefs.group); }
      if (prefs.voice) { $('#voice').value = prefs.voice; }
      fillVoiceOptions();
      $('#only-new').checked = !!prefs.onlyNew;
      bindUI();
      renderChips();
      refreshDashboard();
      var single = params.get('w');
      if (single) {
        wordsFor([single]).then(function (words) {
          if (words.length) { startSession(words, params.get('mode') || 'card'); }
        });
      }
    }).catch(function () {
      toast('词库加载失败，刷新页面试试');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }
})();
