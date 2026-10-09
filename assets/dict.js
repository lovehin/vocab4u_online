/* ============================================================
   随浪背单词 —— 全站公共脚本
   ------------------------------------------------------------
   1. 发音：单词走在线真人发音，失败或离线时自动切浏览器语音；
           例句/小故事统一用浏览器语音 —— 语音按名字打分挑，别用系统默认那个。
   2. 生词本：收藏的词存在本地 localStorage（v4u.star.v1）。
   3. 词表页的即时搜索。
   4. 注册 Service Worker（离线可用）。
   ============================================================ */
(function () {
  'use strict';

  var STAR_KEY = 'v4u.star.v1';
  var PREF_KEY = 'v4u.prefs.v1';
  var audio = new Audio();
  audio.preload = 'none';

  function readJSON(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }

  function writeJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 隐私模式忽略 */ }
  }

  function prefs() { return readJSON(PREF_KEY, {}); }

  /* ---------------- 浏览器语音 ---------------- */
  // 语音表是异步加载的，而且各平台质量差得很远：macOS 上语音按名字排序，
  // 第一个 en-US 是上世纪的老合成音「Albert」，后面还跟着 Bad News / Bells /
  // Boing / Zarvox 这类纯特效音 —— 谁要是直接取「第一个英文语音」，例句就会读得很怪。
  // 所以按名字打分挑，并且把它单独挑出来的语音在设置里让用户自己改。
  var 好语音 = [
    'samantha', 'alex', 'ava', 'allison', 'susan', 'tom', 'nicky', 'aaron',
    'serena', 'zoe', 'karen', 'moira', 'tessa', 'fiona', 'daniel', 'oliver', 'kate',
    'google us english', 'google uk english',
    'microsoft aria', 'microsoft jenny', 'microsoft guy', 'microsoft zira',
    'microsoft david', 'microsoft mark', 'microsoft hazel', 'microsoft george',
    'microsoft ryan', 'microsoft sonia'
  ];
  var 怪语音 = [
    'albert', 'bad news', 'bahh', 'bells', 'boing', 'bubbles', 'cellos', 'deranged',
    'good news', 'hysterical', 'jester', 'junior', 'organ', 'superstar', 'trinoids',
    'whisper', 'wobble', 'zarvox', 'grandmaster', 'banging', 'pipe organ',
    'princess', 'bruce', 'fred', 'ralph', 'kathy'
  ];
  var voices = [];

  function loadVoices() {
    if (!window.speechSynthesis) { return; }
    var list = window.speechSynthesis.getVoices() || [];
    if (list.length) { voices = list; }
  }
  if (window.speechSynthesis) {
    loadVoices();
    window.speechSynthesis.addEventListener('voiceschanged', loadVoices);
  }

  /* 语音表没准备好就先等等：Chrome 刚进页面时 getVoices() 还是空的，
     这时朗读会落到系统默认语音上（中文系统的默认语音读英文最怪）。 */
  function whenVoicesReady(cb) {
    if (!window.speechSynthesis || voices.length) { cb(); return; }
    var done = false;
    function run() {
      if (done) { return; }
      done = true;
      loadVoices();
      cb();
    }
    window.speechSynthesis.addEventListener('voiceschanged', run);
    setTimeout(run, 700);
  }

  function 语音分(v, want) {
    var lang = String(v.lang || '').replace('_', '-').toLowerCase();
    if (lang.indexOf('en') !== 0) { return -1; }          // 非英文语音一律不碰
    var name = String(v.name || '').toLowerCase();
    var score = lang.indexOf(want) === 0 ? 30 : 10;
    var i;
    for (i = 0; i < 好语音.length; i++) {
      if (name.indexOf(好语音[i]) >= 0) { score += 200 - i; break; }
    }
    for (i = 0; i < 怪语音.length; i++) {
      if (name.indexOf(怪语音[i]) >= 0) { score -= 120; break; }
    }
    return score;
  }

  function pickVoice() {
    if (!voices.length) { loadVoices(); }
    var 指定 = String(prefs().voiceName || '');
    if (指定) {
      for (var k = 0; k < voices.length; k++) {
        if (voices[k].name === 指定) { return voices[k]; }
      }
    }
    var want = prefs().accent === 'uk' ? 'en-gb' : 'en-us';
    var best = null, bestScore = -1000;
    for (var i = 0; i < voices.length; i++) {
      var sc = 语音分(voices[i], want);
      if (sc > bestScore) { bestScore = sc; best = voices[i]; }
    }
    return best;
  }

  function 英文语音列表() {
    if (!voices.length) { loadVoices(); }
    return voices.filter(function (v) { return /^en/i.test(v.lang || ''); });
  }

  function 朗读(text) {
    var synth = window.speechSynthesis;
    if (!synth) { return; }
    try {
      var utter = new SpeechSynthesisUtterance(text);
      var v = pickVoice();
      if (v) { utter.voice = v; }
      utter.lang = (v && v.lang) || 'en-US';
      utter.pitch = 1;
      utter.rate = /[.!?,;]$/.test(text) || text.length > 24 ? 0.95 : 0.9;
      var busying = synth.speaking || synth.pending;      // cancel() 之后再判断就不准了
      synth.cancel();
      // Chrome 里 cancel() 紧接着 speak() 偶尔会哑掉，正在读的时候让开一拍
      if (busying) { setTimeout(function () { synth.speak(utter); }, 90); }
      else { synth.speak(utter); }
    } catch (e) { /* 浏览器不给用就算了 */ }
  }

  function speakBrowser(text) {
    if (!window.speechSynthesis) { return false; }
    whenVoicesReady(function () { 朗读(text); });
    return true;
  }

  function speakOnline(text, type) {
    if (prefs().voice === 'browser') { return false; }
    var url = 'https://dict.youdao.com/dictvoice?audio=' + encodeURIComponent(text) +
      '&type=' + (type === '1' ? 1 : 2);
    audio.pause();
    delete audio.dataset.fell;
    audio.src = url;
    var p = audio.play();
    if (p && p.catch) { p.catch(在线回落); }
    return true;
  }

  /* 在线发音失败 → 浏览器语音。error 事件和 play() 的 reject 可能同时来，
     用 dataset 标记挡住，免得同一句话读两遍。 */
  function 在线回落() {
    if (audio.dataset.fell) { return; }
    audio.dataset.fell = '1';
    speakBrowser(audio.dataset.text);
  }
  audio.addEventListener('error', 在线回落);

  function speak(text, mode) {
    text = String(text || '').trim();
    if (!text) { return; }
    // 句子、短语一律用浏览器语音；单词优先真人发音
    var isWord = text.indexOf(' ') < 0 && text.length <= 20 && /^[A-Za-z'’.\- ]+$/.test(text);
    audio.dataset.text = text;
    if (isWord && mode !== 'browser' && speakOnline(text, mode === 'uk' ? '1' : '2')) { return; }
    speakBrowser(text);
  }

  /* ---------------- 生词本 ---------------- */
  function stars() { var s = readJSON(STAR_KEY, []); return Object.prototype.toString.call(s) === '[object Array]' ? s : []; }

  function toggleStar(slug) {
    var list = stars();
    var i = list.indexOf(slug);
    if (i >= 0) { list.splice(i, 1); } else { list.push(slug); }
    writeJSON(STAR_KEY, list);
    return i < 0;
  }

  function paintStar(btn) {
    var slug = btn.getAttribute('data-star');
    var on = stars().indexOf(slug) >= 0;
    btn.textContent = (on ? '★' : '☆') + ' ' + (on ? '已加入生词本' : '加入生词本');
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  /* ---------------- 气泡提示 ---------------- */
  function toast(text) {
    var box = document.getElementById('toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast';
      box.className = 'toast';
      box.setAttribute('role', 'status');
      document.body.appendChild(box);
    }
    box.textContent = text;
    box.classList.add('show');
    clearTimeout(box._timer);
    box._timer = setTimeout(function () { box.classList.remove('show'); }, 1800);
  }

  /* ---------------- 事件 ---------------- */
  document.addEventListener('click', function (event) {
    var speakBtn = event.target.closest('[data-say]');
    if (speakBtn) {
      event.preventDefault();
      var type = speakBtn.getAttribute('data-type') || '2';
      speak(speakBtn.getAttribute('data-say'), type === 'en' ? 'browser' : type);
      return;
    }
    var starBtn = event.target.closest('[data-star]');
    if (starBtn) {
      event.preventDefault();
      var added = toggleStar(starBtn.getAttribute('data-star'));
      paintStar(starBtn);
      toast(added ? '已加入生词本 ★' : '已从生词本移除');
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('[data-star]'), paintStar);
    initWordSearch();

    var filter = document.querySelector('[data-filter]');
    if (filter) {
      var table = document.querySelector('.word-table tbody');
      var rows = table ? Array.prototype.slice.call(table.rows) : [];
      var run = function () {
        var q = filter.value.trim().toLowerCase();
        rows.forEach(function (row) {
          row.style.display = !q || row.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
        });
      };
      filter.addEventListener('input', run);
      // 搜索引擎的站内搜索框（SearchAction）会带 ?q= 过来，直接填进筛选框
      var q = '';
      try { q = new URLSearchParams(location.search).get('q') || ''; } catch (e) { q = ''; }
      if (q) { filter.value = q; run(); }
    }
  });

  /* ---------------- 全部单词目录页的搜索框 ---------------- */
  function initWordSearch() {
    var box = document.getElementById('word-search');
    if (!box) { return; }
    var out = document.getElementById('search-result');
    var letters = document.getElementById('letter-cards');
    var hint = document.getElementById('search-hint');
    var list = null, loading = false, MAX = 80;

    function paint() {
      var q = box.value.trim().toLowerCase();
      if (!q) {
        out.hidden = true; out.innerHTML = '';
        if (letters) { letters.hidden = false; }
        hint.textContent = '按字母往下翻，或者直接搜';
        return;
      }
      if (!list) { return; }
      var hit = [];
      for (var i = 0; i < list.length && hit.length < MAX; i++) {
        if (list[i][0].toLowerCase().indexOf(q) >= 0) { hit.push(list[i]); }
      }
      if (letters) { letters.hidden = true; }
      out.hidden = false;
      out.innerHTML = hit.length
        ? hit.map(function (it) {
            return '<a href="' + it[1] + '">' + it[0] + '</a>';
          }).join('')
        : '<p class="hint">没找到匹配的词，换个写法试试。</p>';
      hint.textContent = hit.length ? '找到 ' + hit.length + ' 个' +
        (hit.length >= MAX ? '（只显示前 ' + MAX + ' 个）' : '') : '没找到';
    }

    function load() {
      if (list || loading) { return; }
      loading = true;
      hint.textContent = '正在加载词表…';
      fetch('/data/index.json').then(function (r) { return r.json(); }).then(function (data) {
        list = data || []; loading = false; paint();
      }).catch(function () {
        loading = false; hint.textContent = '词表没加载出来，刷新页面试试';
      });
    }

    box.addEventListener('input', function () { load(); paint(); });
    var q = '';
    try { q = new URLSearchParams(location.search).get('q') || ''; } catch (e) { q = ''; }
    if (q) { box.value = q; load(); }
  }

  document.addEventListener('keydown', function (event) {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') { return; }
    if (event.code === 'Space' && document.querySelector('[data-say]')) {
      var w = document.querySelector('.entry-word');
      if (w) { event.preventDefault(); speak(w.textContent.trim(), '2'); }
    }
  });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () { });
    });
  }

  window.V4U = { speak: speak, toast: toast, stars: stars, toggleStar: toggleStar,
                 englishVoices: 英文语音列表, whenVoicesReady: whenVoicesReady,
                 currentVoice: pickVoice };
})();
