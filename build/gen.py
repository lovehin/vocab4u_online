#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随浪背单词 · 整站生成器

输入：assets/config.js（站点配置）+ data/dictionary.json / books.json / roots.json
输出：
    /w/<slug>.html            7954 个词条页（单词 index 特殊，见 词条地址()）
    /w/index.html             A–Z 全部单词目录（线上地址就是 /w/）
    /letter/<a-z>.html        字母索引（26 页）
    /list/index.html          词书总览
    /list/<book>.html         词书词表（每页 300 词，分页）
    /roots.html + /roots/*.html  词根词缀（288 页）
    /learn.html               学习器（外壳）
    / /about /privacy /guide/* /404.html
    sitemap.xml robots.txt llms.txt manifest.webmanifest sw.js assets/version.js
    og/*.jpg icons/*.png      分享图与应用图标（需要 Pillow，缺了就跳过）
    data/words/*.json         学习器用的词书分片

运行：python3 build/gen.py
"""
import datetime
import hashlib
import html
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 文案_教程 as 教程            # noqa: E402

V = '10'                             # 改过 assets/ 下的 css/js 之后把这个数字加 1，再重新生成
PER_PAGE = 300                      # 词表页每页词数
SHARD = 500                         # 学习器数据分片大小
TODAY = datetime.date.today().isoformat()
STATE_FILE = os.path.join(BASE, 'build', '.生成状态.json')


# ---------------------------------------------------------------- 站点配置
DEFAULTS = {
    'domain': 'vocab4u.suilang.net',
    'name': '随浪背单词', 'nameEn': 'Vocab4U', 'shortName': '随浪背单词',
    'tagline': '', 'description': '', 'keywords': '',
    'contactEmail': 'contact@suilang.net', 'legalEmail': 'dmca@suilang.net',
    'startYear': 2026, 'brandColor': '#2ee6b8',
    'source': {}, 'books': [], 'learn': {}, 'analytics': {}, 'verify': {}, 'ads': {}, 'faq': [],
}


def read_config():
    script = ("global.window={};"
              "eval(require('fs').readFileSync(process.argv[1],'utf8'));"
              "process.stdout.write(JSON.stringify(window.SITE));")
    try:
        out = subprocess.check_output(['node', '-e', script,
                                       os.path.join(BASE, 'assets', 'config.js')],
                                      cwd=BASE, stderr=subprocess.DEVNULL)
        cfg = json.loads(out.decode('utf-8'))
    except Exception as exc:                                     # 没有 node 时的退化方案
        sys.stderr.write('读取 assets/config.js 失败（%s），改用最小配置。\n' % exc)
        raw = open(os.path.join(BASE, 'assets', 'config.js'), encoding='utf-8').read()
        m = re.search(r'domain:\s*"([^"]+)"', raw)
        cfg = dict(DEFAULTS)
        cfg['domain'] = m.group(1) if m else DEFAULTS['domain']
    merged = dict(DEFAULTS)
    merged.update(cfg)
    return merged


CFG = read_config()
DOMAIN = CFG['domain'].rstrip('/')
SITE_URL = 'https://' + DOMAIN
SITE_NAME = CFG['name']
LEARN = CFG['learn'] or {}


def esc(text):
    return html.escape(str(text if text is not None else ''), quote=True)


def U(path):
    """站内地址 → 完整网址（path 不带 .html）。"""
    if path in ('', '/'):
        return SITE_URL + '/'
    return SITE_URL + path


def _slug(w):
    return w['slug'] if isinstance(w, dict) else str(w)


def 词条文件(w):
    """词条页的文件名。单词 index 的 slug 会和 /w/ 这个目录首页抢 index.html，
    Cloudflare 又把 /w/index 归一成 /w/，所以它单独挪到 index-word。"""
    slug = _slug(w)
    return 'index-word.html' if slug == 'index' else '%s.html' % slug


def 词条地址(w):
    """词条页的站内地址（不带 .html）。"""
    slug = _slug(w)
    return '/w/index-word' if slug == 'index' else '/w/%s' % slug


# ---------------------------------------------------------------- 生成状态
_STATE = {}
try:
    _STATE = json.load(open(STATE_FILE, encoding='utf-8'))
except Exception:
    _STATE = {}

_dirty = False
TODAY_CACHE = {}


def write_file(rel, content, change_date=None):
    """写文件；内容变了才把 lastmod 推到今天（避免日期天天往前跑）。

    change_date 给定时（词条页用数据版本号）直接用这个日期。
    """
    global _dirty
    path = os.path.join(BASE, rel)
    os.makedirs(os.path.dirname(path) or BASE, exist_ok=True)
    data = content.encode('utf-8') if isinstance(content, str) else content
    digest = hashlib.sha1(data).hexdigest()
    old = _STATE.get(rel)
    if old and old.get('h') == digest:
        date = old.get('d') or TODAY
    else:
        date = change_date or TODAY
        _dirty = True
    _STATE[rel] = {'h': digest, 'd': date}
    if not os.path.exists(path) or open(path, 'rb').read() != data:
        with open(path, 'wb') as fh:
            fh.write(data)
        _dirty = True
    return date


def save_state():
    json.dump(_STATE, open(STATE_FILE, 'w', encoding='utf-8'), ensure_ascii=False)


# ---------------------------------------------------------------- 页头 / 页脚
NAVS = [('/', '首页'), ('/learn', '开始背单词'), ('/list', '词书'),
        ('/roots', '词根词缀'), ('/guide/', '背单词方法')]
# /guide 是目录首页（guide/index.html），Cloudflare 会把不带斜杠的地址 307 到
# /guide/，所以站内链接和 canonical 一律写成带斜杠的 /guide/，少一跳。
GUIDE_HUB = '/guide/'


def head_html(title, desc, path, og='og/word.jpg', jsonld=None, keywords=None, updated=None, noindex=False):
    验证 = CFG.get('verify') or {}
    统计 = CFG.get('analytics') or {}
    parts = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>%s</title>' % esc(title),
        '<meta name="description" content="%s">' % esc(desc),
    ]
    if keywords:
        parts.append('<meta name="keywords" content="%s">' % esc(keywords))
    parts += [
        '<link rel="canonical" href="%s">' % esc(U(path)),
        '<meta name="robots" content="noindex,follow">' if noindex else '<meta name="robots" content="index,follow">',
        '<meta name="theme-color" content="#f5f7fb">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="%s">' % esc(SITE_NAME),
        '<meta property="og:title" content="%s">' % esc(title),
        '<meta property="og:description" content="%s">' % esc(desc),
        '<meta property="og:url" content="%s">' % esc(U(path)),
        '<meta property="og:image" content="%s">' % esc(U('/' + og)),
        '<meta name="twitter:card" content="summary_large_image">',
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
        '<link rel="apple-touch-icon" href="/icons/icon-192.png">',
        '<link rel="manifest" href="/manifest.webmanifest">',
        '<link rel="stylesheet" href="/assets/style.css?v=%s">' % V,
    ]
    if 验证.get('baidu'):
        parts.append('<meta name="baidu-site-verification" content="%s">' % esc(验证['baidu']))
    if 验证.get('bytedance'):
        parts.append('<meta name="bytedance-verification-code" content="%s">' % esc(验证['bytedance']))
    if 验证.get('google'):
        parts.append('<meta name="google-site-verification" content="%s">' % esc(验证['google']))
    if 统计.get('baidu'):
        parts.append(
            '<script>var _hmt=_hmt||[];(function(){var hm=document.createElement("script");'
            'hm.src="https://hm.baidu.com/hm.js?%s";var s=document.getElementsByTagName("script")[0];'
            's.parentNode.insertBefore(hm,s);})();</script>' % esc(统计['baidu']))
    if jsonld:
        parts.append('<script type="application/ld+json">%s</script>'
                     % json.dumps(jsonld, ensure_ascii=False, separators=(',', ':')))
    return '\n'.join(parts)


def header_html(cur):
    links = []
    for href, label in NAVS:
        attr = ' aria-current="page"' if href == cur else ''
        links.append('<a href="%s"%s>%s</a>' % (href, attr, esc(label)))
    return ('<a class="skip" href="#main">跳到主要内容</a>'
            '<header class="site-header"><div class="wrap">'
            '<a class="brand" href="/"><span class="brand-mark" aria-hidden="true"></span>%s</a>'
            '<nav class="nav" aria-label="主导航">%s</nav>'
            '</div></header>' % (esc(SITE_NAME), ''.join(links)))


def footer_html():
    return (
        '<footer class="site-footer"><div class="wrap"><div class="cols">'
        '<div><h2>%s</h2>'
        '<p style="font-size:.82rem;margin:8px 0 0">本站是 <a href="https://suilang.net/">随浪工具站</a> 的一员 —— 还有图片转换、在线 Markdown 等更多免费小工具。</p>'
        '<p style="margin:10px 0 0">%s</p>'
        '</div>'
        '<div><h2>词书</h2><ul>%s</ul></div>'
        '<div><h2>关于</h2><ul>'
        '<li><a href="/learn">开始背单词</a></li>'
        '<li><a href="/roots">词根词缀</a></li>'
        '<li><a href="%s">背单词方法</a></li>'
        '<li><a href="/about">关于本站</a></li>'
        '<li><a href="/privacy">隐私说明</a></li>'
        '<li><a href="mailto:%s">联系我</a></li>'
        '</ul></div></div>%s'
        '<div class="legal"><span>© %s %s · 免费、免登录、无广告</span>'
        '<span>本站不收集个人信息，学习记录只存在你的浏览器里</span></div>'
        '</div></footer>' % (
            esc(SITE_NAME),
            esc(CFG['tagline']),
            ''.join('<li><a href="/list/%s">%s</a></li>' % (b['slug'], esc(b['name']))
                    for b in 词书展示()),
            GUIDE_HUB,
            esc(CFG['contactEmail']),
            赞赏块(),
            版权年份(), esc(SITE_NAME)))


def 版权年份():
    """起始年和今年一样时只写一个年份，避免页脚出现「© 2026–2026」。"""
    起 = int(CFG['startYear'])
    今 = datetime.date.today().year
    return str(起) if 起 >= 今 else '%s–%s' % (起, 今)


def 赞赏块():
    return (
        '<div class="no-print" style="border-top:1px solid rgba(22,35,60,.10);margin-top:22px;padding-top:18px">'
        '<details><summary>❤️ 支持随浪 · 请我喝杯奶茶</summary>'
        '<div style="margin-top:14px;font-size:.85rem;line-height:1.75">'
        '<p style="margin:0 0 14px">这个站一直免费，也没有注册墙。如果它帮到了你，可以请我喝杯奶茶 ☕ 你的支持就是它继续更新的动力。</p>'
        '<div class="pay-row">'
        '<figure><img class="pay-img" src="https://suilang.net/assets/pay/wechat.jpg" alt="微信赞赏码" width="540" height="733" loading="lazy">'
        '<figcaption style="margin-top:6px;font-size:.78rem">微信</figcaption></figure>'
        '<figure><img class="pay-img" src="https://suilang.net/assets/pay/alipay.jpg" alt="支付宝收款码" width="540" height="810" loading="lazy">'
        '<figcaption style="margin-top:6px;font-size:.78rem">支付宝</figcaption></figure>'
        '</div>'
        '<p style="margin:14px 0 0;font-size:.8rem;opacity:.72">放个收款码不是打赏墙 —— 一分钱不花也能用全部功能。想让我知道是谁支持了，付款时留个称呼就行。</p>'
        '</div></details></div>')


def shell(title, desc, path, body, og='og/word.jpg', jsonld=None, keywords=None,
          cur='', updated=None, noindex=False):
    up = ''
    if updated:
        up = '<p class="updated">最后更新：<time datetime="%s">%s</time></p>' % (esc(updated), esc(updated))
    return ('<!doctype html>\n<html lang="zh-CN">\n<head>\n%s\n</head>\n<body>\n%s\n'
            '<main id="main">\n%s\n%s\n</main>\n%s\n'
            '<script src="/assets/dict.js?v=%s" defer></script>\n</body>\n</html>\n'
            % (head_html(title, desc, path, og, jsonld, keywords, updated, noindex),
               header_html(cur), body, up, footer_html(), V))


# ---------------------------------------------------------------- 读数据
def load_data():
    dic = json.load(open(os.path.join(BASE, 'data', 'dictionary.json'), encoding='utf-8'))
    books = json.load(open(os.path.join(BASE, 'data', 'books.json'), encoding='utf-8'))['books']
    roots = json.load(open(os.path.join(BASE, 'data', 'roots.json'), encoding='utf-8'))
    return dic, books, roots


WORDS, BOOKS, ROOTS = load_data()
BY_SLUG = {w['slug']: w for w in WORDS}
BOOK_BY_SLUG = {b['slug']: b for b in BOOKS}
ORDER = {}                       # 词书 slug → {词 slug: 位次}
for _b in BOOKS:
    ORDER[_b['slug']] = {s: i for i, s in enumerate(_b['words'])}

TAG_TEXT = {'zk': '中考', 'gk': '高考', 'cet4': '四级', 'cet6': '六级',
            'ky': '考研', 'toefl': '托福', 'ielts': '雅思', 'gre': 'GRE'}
BOOK_OF_TAG = {'zk': 'zhongkao', 'gk': 'gaokao', 'cet4': 'cet4',
               'cet6': 'cet6', 'ky': 'kaoyan'}

ROOT_OF_WORD = {}                # 词 slug → [词根条目]
根页地址 = {}


def make_slug(text):
    s = re.sub(r'[^a-z0-9]+', '-', str(text).strip().lower()).strip('-')
    return s or 'root'


for _r in ROOTS:
    slug = make_slug(_r['key'])
    n = 1
    while slug in 根页地址 and 根页地址[slug]['key'] != _r['key']:
        n += 1
        slug = '%s-%d' % (make_slug(_r['key']), n)
    根页地址[slug] = _r
    _r['slug'] = slug
    for _w in _r['words']:
        ROOT_OF_WORD.setdefault(_w, []).append(_r)


# ---------------------------------------------------------------- 词形变化
词形标签 = {'p': '过去式', 'd': '过去分词', 'i': '现在分词',
            '3': '第三人称单数', 's': '复数', 'r': '比较级', 't': '最高级'}
词形次序 = ['p', 'd', 'i', '3', 's', 'r', 't']
_TOKEN = re.compile(r"[a-z][a-z'\-]*")


def load_forms():
    """读 data/forms.json：每个变形 → 原词、音标、释义，以及在本站语料里出现几次。

    ⚠️ 只给「在本站例句和小故事里真的出现过」的变形单独建页。变形是程序生成的，
       全量建页（一万多个）在搜索引擎眼里就是一堆空壳子，宁可少而实。
       没有 forms.json 时整块功能自动跳过（跑一次 build/取数据.py 就有）。
    """
    path = os.path.join(BASE, 'data', 'forms.json')
    if not os.path.exists(path):
        sys.stderr.write('没有 data/forms.json，跳过词形变化与形近词。跑一次 build/取数据.py 就能生成。\n')
        return {}, {}, [], {}, TODAY
    data = json.load(open(path, encoding='utf-8'))
    词形表, 基词词形, 词条别名 = {}, {}, {}
    占位, 待建 = set(BY_SLUG), []
    for raw in data.get('forms') or []:
        item = {'f': raw['f'], 'key': raw['f'].lower(), 'n': raw.get('n') or 0,
                'ipa': raw.get('ipa') or '', 'tr': raw.get('tr') or [],
                'w': raw.get('w') or '', 'bases': []}
        for slug, codes in raw.get('b') or []:
            if slug in BY_SLUG:
                item['bases'].append((slug, [c for c in 词形次序 if c in codes]))
        if not item['bases']:
            continue
        词形表[item['key']] = item
        for slug, _codes in item['bases']:
            基词词形.setdefault(slug, []).append(item)
        if item['w']:
            for slug, codes in item['bases']:
                词条别名.setdefault(item['w'], []).append((slug, codes))
            continue
        slug = make_slug(item['f'])
        if item['n'] > 0 and slug and slug not in 占位:
            占位.add(slug)
            item['slug'] = slug
            待建.append(item)
    return 词形表, 基词词形, 待建, 词条别名, data.get('generated') or TODAY


def 建语料索引():
    """语料索引：一个词形 → 本站例句（含中文）和小故事里带它的句子。"""
    索引 = {}
    for w in WORDS:
        for s in w.get('sentences') or []:
            en, zh = (s.get('en') or '').strip(), (s.get('zh') or '').strip()
            if not en:
                continue
            for tok in set(_TOKEN.findall(en.lower())):
                索引.setdefault(tok, []).append((w['slug'], en, zh))
        story = ((w.get('story') or {}).get('en') or '').strip()
        if story:
            for tok in set(_TOKEN.findall(story.lower())):
                索引.setdefault(tok, []).append((w['slug'], story, ''))
    return 索引


def 建形近词表():
    """拼写相近的词：首字母相同、长度差 ≤2、编辑距离 ≤2，按词频排。"""
    桶 = {}
    for w in WORDS:
        x = w['word'].lower()
        if x.isalpha():
            桶.setdefault((x[0], len(x)), []).append(w)

    def 距离(a, b, cap=2):
        if abs(len(a) - len(b)) > cap:
            return cap + 1
        上一行 = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            当前行 = [i]
            for j, cb in enumerate(b, 1):
                当前行.append(min(上一行[j] + 1, 当前行[j - 1] + 1, 上一行[j - 1] + (ca != cb)))
            if min(当前行) > cap:
                return cap + 1
            上一行 = 当前行
        return 上一行[-1]

    表 = {}
    for w in WORDS:
        x = w['word'].lower()
        if not x.isalpha():
            continue
        找到 = []
        for dl in (-2, -1, 0, 1, 2):
            for other in 桶.get((x[0], len(x) + dl), []):
                y = other['word'].lower()
                if y == x:
                    continue
                d = 距离(x, y)
                if d <= 2:
                    找到.append((d, other.get('frq') or 10 ** 9, y, other))
        # 先拼写最像的（编辑距离小），距离一样再按词频常见的排前面
        找到.sort(key=lambda t: (t[0], t[1], t[2]))
        表[w['slug']] = [t[3] for t in 找到[:5]]
    return 表


词形表, 基词词形, 词形页, 词条别名, 词形版本 = load_forms()
语料索引 = 建语料索引() if 词形页 else {}
形近词表 = 建形近词表()
词形页地址 = {it['key']: '/w/' + it['slug'] for it in 词形页}


def 词形链接(item):
    """一个变形词形该链到哪里：自己的词形页，或者它本身就是的那条词条。"""
    if item.get('slug'):
        return '/w/' + item['slug']
    if item['w'] and item['w'] in BY_SLUG:
        return 词条地址(BY_SLUG[item['w']])
    return ''


def 词形块(entry, 跳过=None):
    """词条页上的「词形变化」：列出全部变形，能点开的给链接。"""
    items = 基词词形.get(entry['slug'])
    if not items:
        return ''
    组 = []
    for it in sorted(items, key=lambda x: (min(词形次序.index(c) for c in x['bases'][0][1]), x['f'])):
        if 跳过 and it['key'] == 跳过:
            continue
        标签 = ' / '.join(词形标签[c] for c in it['bases'][0][1])
        正文 = '<b>%s</b>%s' % (esc(标签), esc(it['f']))
        链接 = 词形链接(it)
        组.append('<a class="f" href="%s">%s</a>' % (esc(链接), 正文) if 链接
                 else '<span class="f">%s</span>' % 正文)
    if not 组:
        return ''
    return ('<section class="entry-sec"><h2>词形变化</h2>'
            '<p class="hint">同一个词的不同形态；带链接的可以单独点开看这个形态的读音和释义。</p>'
            '<p class="forms">%s</p></section>' % ''.join(组))


def 原形块(entry):
    """这条词条本身也是别的词的变形时，指回原形。"""
    rels = 词条别名.get(entry['slug'])
    if not rels:
        return ''
    段 = []
    for slug, codes in rels:
        base = BY_SLUG.get(slug)
        if not base:
            continue
        段.append('<a href="%s">%s</a> 的%s'
                  % (esc(词条地址(base)), esc(base['word']),
                     '和'.join(词形标签[c] for c in codes)))
    if not 段:
        return ''
    return '<p class="hint">这个词也是 %s。</p>' % '、'.join(段)


def 形近块(entry):
    items = 形近词表.get(entry['slug'])
    if not items:
        return ''
    卡 = []
    for w in items:
        trans = 释义行(w)
        卡.append('<a href="%s">%s<small>%s</small></a>'
                  % (esc(词条地址(w)), esc(w['word']),
                     esc((trans[0][:20] if trans else w.get('us') or ''))))
    return ('<section class="entry-sec"><h2>形近词</h2>'
            '<p class="hint">拼写相近，别记混了。</p>'
            '<div class="rel-grid">%s</div></section>' % ''.join(卡))


def 词书展示():
    """把 config.js 里的展示信息与 data/books.json 的词数合并。"""
    out = []
    for item in CFG['books']:
        book = BOOK_BY_SLUG.get(item['slug'])
        if not book:
            continue
        out.append({'slug': item['slug'], 'name': item.get('name') or book['name'],
                    'note': item.get('note', ''), 'level': item.get('level', ''),
                    'count': book['count'], 'new': book.get('new', book['count'])})
    for book in BOOKS:                      # config 里漏掉的词书也补上
        if not any(x['slug'] == book['slug'] for x in out):
            out.append({'slug': book['slug'], 'name': book['name'], 'note': '',
                        'level': '', 'count': book['count'], 'new': book.get('new', book['count'])})
    return out


def 词书地址(slug):
    return '/list/%s' % slug


# ---------------------------------------------------------------- 文本 → HTML
def text_to_html(text):
    """把一节正文（可能含编号列表）转成段落 HTML。"""
    if not text:
        return ''
    out, buf = [], []

    def flush():
        if buf:
            body = '<br>'.join(esc(x) for x in buf)
            out.append('<p>%s</p>' % body)
            buf.clear()

    lines = text.split('\n')
    list_buf = []
    for line in lines:
        raw = line.strip()
        if not raw:
            flush()
            if list_buf:
                out.append('<ol>%s</ol>' % ''.join('<li>%s</li>' % x for x in list_buf))
                list_buf = []
            continue
        m = re.match(r'^\d{1,2}[.、)）]\s*(.+)$', raw)
        if m:
            flush()
            list_buf.append(esc(m.group(1)))
            continue
        if list_buf:
            out.append('<ol>%s</ol>' % ''.join('<li>%s</li>' % x for x in list_buf))
            list_buf = []
        buf.append(raw)
    flush()
    if list_buf:
        out.append('<ol>%s</ol>' % ''.join('<li>%s</li>' % x for x in list_buf))
    return ''.join(out)


def 释义行(entry):
    """中文释义按词性折成一行行。"""
    return [x for x in entry.get('trans', []) if x.strip()]


def 首段结论(entry):
    """GEO 要求：第一段就说清「这是什么、给谁用、关键参数」。"""
    levels = [TAG_TEXT[t] for t in entry.get('tags', []) if t in TAG_TEXT]
    bits = []
    if levels:
        bits.append('、'.join(levels) + '词汇')
    else:
        bits.append('通用词汇')
    trans = 释义行(entry)
    if trans:
        bits.append('意思是：' + '；'.join(t.strip()[:40] for t in trans[:2]))
    if entry.get('frq'):
        bits.append('词频排名 %d' % entry['frq'])
    if entry.get('collins'):
        bits.append('柯林斯 %d 星' % entry['collins'])
    if entry.get('sentences'):
        bits.append('配 %d 条中英对照例句' % len(entry['sentences']))
    return '%s。' % '，'.join(bits)


def 例句HTML(entry):
    items = entry.get('sentences') or []
    if not items:
        return ''
    out = []
    for it in items:
        en, zh = (it.get('en') or '').strip(), (it.get('zh') or '').strip()
        if not en and not zh:
            continue
        tools = []
        if en:
            tools.append('<button type="button" data-say="%s" data-type="en">🔊 朗读</button>' % esc(en))
            tools.append('<a href="/learn?mode=typing&amp;w=%s">⌨️ 用这条例句练打字</a>' % esc(entry['slug']))
        out.append('<li><div class="sent-en">%s</div>%s%s</li>' % (
            esc(en or zh),
            '<div class="sent-zh">%s</div>' % esc(zh) if zh else '',
            '<div class="sent-tools">%s</div>' % ' '.join(tools) if tools else ''))
    return '<ul class="sent-list">%s</ul>' % ''.join(out)


def 故事HTML(entry):
    story = entry.get('story') or {}
    en, zh = (story.get('en') or '').strip(), (story.get('zh') or '').strip()
    if not en and not zh:
        return ''
    parts = []
    if en:
        parts.append('<p class="story-en">%s <button type="button" class="speak" data-say="%s" data-type="en" aria-label="朗读小故事">🔊</button></p>' % (esc(en), esc(en)))
    if zh:
        parts.append('<p class="story-zh">%s</p>' % esc(zh))
    return ''.join(parts)


def 标签HTML(entry):
    tags = []
    for t in entry.get('tags', []):
        if t in TAG_TEXT:
            tags.append('<span class="tag tag-lv">%s</span>' % TAG_TEXT[t])
    if entry.get('frq'):
        tags.append('<span class="tag tag-frq">词频 %d</span>' % entry['frq'])
    if entry.get('collins'):
        tags.append('<span class="tag">柯林斯 %d 星</span>' % entry['collins'])
    if entry.get('oxford'):
        tags.append('<span class="tag">牛津核心</span>')
    return ''.join(tags)


def 发音HTML(entry, cls=''):
    us, uk = entry.get('us') or '', entry.get('uk') or ''
    bits = ['<button type="button" class="speak%s" data-say="%s" data-type="2" aria-label="朗读 %s（美音）">🔊</button>'
            % (cls, esc(entry['word']), esc(entry['word']))]
    if us:
        bits.append('<span>美 %s</span>' % esc(us))
    if uk and uk != us:
        bits.append('<span>英 %s</span>' % esc(uk))
    return ''.join(bits)


# ---------------------------------------------------------------- 词条页
SEC_ORDER = [('词义', '词义分析'), ('例句', '例句'), ('词根', '词根分析'), ('词缀', '词缀分析'),
             ('文化', '发展历史与文化背景'), ('变形', '单词变形'), ('记忆', '记忆辅助'),
             ('故事', '小故事')]


def 相关词(entry):
    out, seen = [], {entry['slug']}
    for r in ROOT_OF_WORD.get(entry['slug'], [])[:4]:
        for s in r['words'][:6]:
            w = BY_SLUG.get(s)
            if w and w['slug'] not in seen:
                seen.add(w['slug'])
                out.append(w)
            if len(out) >= 8:
                break
    book = (entry.get('books') or ['all'])[0]
    order = (BOOK_BY_SLUG.get(book) or {}).get('words') or []
    # 只挑首字母相同的词，频率也接近，比纯粹按频率取邻居更像「相关词」
    first = entry['word'][:1].lower()
    same = [s for s in order if s[:1] == first]
    if entry['slug'] in same:
        idx = same.index(entry['slug'])
        for j in list(range(max(0, idx - 4), idx)) + list(range(idx + 1, min(len(same), idx + 5))):
            w = BY_SLUG.get(same[j])
            if w and w['slug'] not in seen:
                seen.add(w['slug'])
                out.append(w)
            if len(out) >= 12:
                break
    return out[:12]


def page_word(entry):
    slug, word = entry['slug'], entry['word']
    path = 词条地址(entry)
    title = '%s 什么意思_%s 的音标、例句、词根词缀 - %s' % (word, word, SITE_NAME)
    desc = '%s：%s' % (word, 首段结论(entry))
    if len(desc) > 150:
        desc = desc[:148] + '…'
    secs = entry.get('sections') or {}

    body = ['<div class="crumbs wrap"><a href="/">首页</a><span>›</span>'
            '<a href="/list">词书</a><span>›</span><a href="/w/">全部单词</a>'
            '<span>›</span>%s</div>' % esc(word)]
    head = ['<article class="wrap-narrow"><header class="entry-head">',
            '<h1 class="entry-word">%s</h1>' % esc(word),
            '<p class="entry-ipa">%s</p>' % 发音HTML(entry),
            '<p class="entry-summary">%s</p>' % esc(首段结论(entry))]
    原形 = 原形块(entry)
    if 原形:
        head.append(原形)
    trans = 释义行(entry)
    if trans:
        head.append('<ul class="entry-trans">%s</ul>'
                    % ''.join('<li>%s</li>' % esc(t) for t in trans))
    tags = 标签HTML(entry)
    if tags:
        head.append('<p style="margin:14px 0 0">%s</p>' % tags)
    head.append('<div class="entry-actions">'
                '<a class="btn btn-primary" href="/learn?w=%s">开始背这个词</a>'
                '<button class="btn" type="button" data-star="%s">☆ 加入生词本</button>'
                '<a class="btn btn-ghost" href="%s">在词表里看</a></div>'
                % (esc(slug), esc(slug), esc(词书地址((entry.get('books') or ['all'])[0]))))
    head.append('</header><div class="entry-body">')

    for key, label in SEC_ORDER:
        if key in ('例句', '故事'):
            continue
        text = (secs.get(key) or '').strip()
        if not text:
            continue
        head.append('<section class="entry-sec"><h2>%s</h2>%s</section>' % (label, text_to_html(text)))

    if secs.get('例句'):
        head.append('<section class="entry-sec"><h2>例句</h2>%s</section>' % 例句HTML(entry))
    if secs.get('故事'):
        head.append('<section class="entry-sec"><h2>小故事</h2>%s</section>' % 故事HTML(entry))
    head.append('</div>')

    rel = 相关词(entry)
    if rel:
        head.append('<section class="entry-sec"><h2>相关词</h2><div class="rel-grid">%s</div></section>'
                    % ''.join('<a href="%s">%s<small>%s</small></a>'
                              % (esc(词条地址(w)), esc(w['word']),
                                 esc((释义行(w)[0][:18] if 释义行(w) else ''))) for w in rel))
    head.append(词形块(entry))
    head.append(形近块(entry))

    head.append('<p class="entry-credit">最后更新：'
                '<time datetime="%s">%s</time></p>'
                % (esc(entry.get('updated', TODAY)), esc(entry.get('updated', TODAY))))
    head.append('</article>')

    jsonld = {
        '@context': 'https://schema.org',
        '@graph': [
            {'@type': 'DefinedTerm', 'name': word,
             'description': 首段结论(entry),
             'url': U(path),
             'inDefinedTermSet': {'@type': 'DefinedTermSet', 'name': SITE_NAME, 'url': SITE_URL}},
            {'@type': 'BreadcrumbList', 'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': '首页', 'item': SITE_URL + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': '全部单词', 'item': U('/w/')},
                {'@type': 'ListItem', 'position': 3, 'name': word, 'item': U(path)}]},
        ],
    }
    return shell(title, desc, path, ''.join(body) + ''.join(head),
                 og='og/word.jpg', jsonld=jsonld,
                 keywords='%s,%s什么意思,%s的音标,%s例句,%s词根' % (word, word, word, word, word))


# ---------------------------------------------------------------- 词形页
def 高亮词形(英文, form):
    """把句子里的这个词形标出来（先切分再转义，免得转义把词形切断了）。"""
    模式 = re.compile(r'\b(%s)\b' % re.escape(form), re.I)
    出, 起点 = [], 0
    for m in 模式.finditer(英文):
        出.append(esc(英文[起点:m.start()]))
        出.append('<b class="hl">%s</b>' % esc(m.group(0)))
        起点 = m.end()
    出.append(esc(英文[起点:]))
    return ''.join(出)


def 词形例句(item):
    """从本站语料里挑几个用到这个形态的句子：先原词自己的例句，再其他词条的。"""
    全部 = 语料索引.get(item['key']) or []
    if not 全部:
        return ''
    主原词 = item['bases'][0][0]
    排队 = sorted(全部, key=lambda t: (0 if t[0] == 主原词 else 1, 0 if t[2] else 1, len(t[1])))
    取, 见过 = [], set()
    for _slug, en, zh in 排队:
        if en in 见过:
            continue
        见过.add(en)
        取.append((en, zh))
        if len(取) >= 4:
            break
    行 = ''.join('<li><div class="sent-en">%s</div>%s</li>'
                 % (高亮词形(en, item['f']),
                    '<div class="sent-zh">%s</div>' % esc(zh) if zh else '')
                 for en, zh in 取)
    return ('<section class="entry-sec"><h2>带 %s 的例句</h2>'
            '<p class="hint">下面这些句子都来自本站例句库，都用了这个形态。</p>'
            '<ul class="sent-list">%s</ul></section>' % (esc(item['f']), 行))


def 原词块(item, base):
    trans = 释义行(base)
    行 = '<ul class="entry-trans">%s</ul>' % ''.join('<li>%s</li>' % esc(t) for t in trans) if trans else ''
    return ('<section class="entry-sec"><h2>%s 是什么意思</h2>'
            '<p class="entry-summary">%s</p>%s'
            '<p style="margin:14px 0 0"><a class="btn btn-primary" href="/learn?w=%s">去背 %s</a> '
            '<a class="btn" href="%s">看 %s 的完整词条</a></p></section>'
            % (esc(base['word']), esc(首段结论(base)), 行,
               esc(base['slug']), esc(base['word']),
               esc(词条地址(base)), esc(base['word'])))


def page_form(item):
    """词形页：went、studying、advanced 这种。一个形态一页，好让人搜到。"""
    form, slug = item['f'], item['slug']
    path = '/w/' + slug
    base = BY_SLUG[item['bases'][0][0]]
    关系 = '、'.join('%s 的%s' % (BY_SLUG[s]['word'], '和'.join(词形标签[c] for c in cs))
                    for s, cs in item['bases'] if s in BY_SLUG)
    概括 = '%s 是 %s%s。' % (form, 关系, '，读音 %s' % item['ipa'] if item['ipa'] else '')
    desc = 概括 + ''.join(item['tr'])
    if len(desc) > 150:
        desc = desc[:148] + '…'
    title = '%s 什么意思_%s 的音标、中文释义和例句 - %s' % (form, form, SITE_NAME)

    body = ['<div class="crumbs wrap"><a href="/">首页</a><span>›</span>'
            '<a href="/w/">全部单词</a><span>›</span><a href="%s">%s</a>'
            '<span>›</span>%s</div>' % (esc(词条地址(base)), esc(base['word']), esc(form)),
            '<article class="wrap-narrow"><header class="entry-head">',
            '<h1 class="entry-word">%s</h1>' % esc(form),
            '<p class="entry-ipa"><button type="button" class="speak" data-say="%s" data-type="2" '
            'aria-label="朗读 %s">🔊</button>%s</p>'
            % (esc(form), esc(form), '<span>美 %s</span>' % esc(item['ipa']) if item['ipa'] else ''),
            '<p class="entry-summary">%s</p>' % esc(概括)]
    if item['tr']:
        body.append('<section class="entry-sec"><h2>%s 的意思</h2><ul class="entry-trans">%s</ul></section>'
                    % (esc(form), ''.join('<li>%s</li>' % esc(t) for t in item['tr'])))
    body.append(词形例句(item))
    body.append(原词块(item, base))
    body.append(词形块(base, 跳过=item['key']))
    body.append('<p class="entry-credit">最后更新：<time datetime="%s">%s</time></p>'
                % (esc(词形版本), esc(词形版本)))
    body.append('</article>')

    jsonld = {
        '@context': 'https://schema.org',
        '@graph': [
            {'@type': 'DefinedTerm', 'name': form, 'description': 概括, 'url': U(path),
             'inDefinedTermSet': {'@type': 'DefinedTermSet', 'name': SITE_NAME, 'url': SITE_URL}},
            {'@type': 'BreadcrumbList', 'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': '首页', 'item': SITE_URL + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': '全部单词', 'item': U('/w/')},
                {'@type': 'ListItem', 'position': 3, 'name': base['word'], 'item': U(词条地址(base))},
                {'@type': 'ListItem', 'position': 4, 'name': form, 'item': U(path)}]},
        ],
    }
    return shell(title, desc, path, ''.join(body), jsonld=jsonld,
                 keywords='%s,%s什么意思,%s的用法,%s例句' % (form, form, 关系.split('、')[0], form))


# ---------------------------------------------------------------- 词表页
def 词行(entry, idx=None):
    trans = 释义行(entry)
    return ('<tr>'
            '<td class="ip">%s</td>'
            '<td class="w"><a href="%s">%s</a></td>'
            '<td class="col-ipa ipa">%s</td>'
            '<td class="zh">%s</td>'
            '<td class="ip col-lv">%s</td>'
            '</tr>' % (idx if idx is not None else '',
                       esc(词条地址(entry)), esc(entry['word']),
                       esc(entry.get('us') or entry.get('uk') or ''),
                       esc('；'.join(trans)[:90]),
                       ' '.join(TAG_TEXT[t] for t in entry.get('tags', []) if t in TAG_TEXT)))


def 词表表格(entries):
    # 外面套一层可横向滚动的壳：手机上窄到放不下时能滑，不会把整页撑宽
    return ('<div class="table-scroll"><table class="word-table"><thead><tr>'
            '<th>#</th><th>单词</th><th class="col-ipa">音标</th><th>中文释义</th>'
            '<th class="col-lv">级别</th>'
            '</tr></thead><tbody>%s</tbody></table></div>'
            % ''.join(词行(e, i + 1) for i, e in enumerate(entries)))


def 分页HTML(base, page, total_pages):
    if total_pages <= 1:
        return ''
    bits = []
    lo = max(1, page - 3)
    hi = min(total_pages, page + 3)
    if page > 1:
        bits.append('<a href="%s">上一页</a>' % esc(base if page == 2 else '%s/%d' % (base, page - 1)))
    if lo > 1:
        bits.append('<a href="%s">1</a>' % esc(base))
        if lo > 2:
            bits.append('<span>…</span>')
    for p in range(lo, hi + 1):
        href = base if p == 1 else '%s/%d' % (base, p)
        bits.append('<span class="cur">%d</span>' % p if p == page else '<a href="%s">%d</a>' % (esc(href), p))
    if hi < total_pages:
        if hi < total_pages - 1:
            bits.append('<span>…</span>')
        bits.append('<a href="%s/%d">%d</a>' % (esc(base), total_pages, total_pages))
    if page < total_pages:
        bits.append('<a href="%s/%d">下一页</a>' % (esc(base), page + 1))
    return '<nav class="pager" aria-label="分页">%s</nav>' % ''.join(bits)


def page_book(book, page=1):
    slugs = book['words']
    total = max(1, (len(slugs) + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total))
    chunk = slugs[(page - 1) * PER_PAGE: page * PER_PAGE]
    entries = [BY_SLUG[s] for s in chunk if s in BY_SLUG]
    base = 词书地址(book['slug'])
    path = base if page == 1 else '%s/%d' % (base, page)
    title = '%s（%d 个单词）%s - %s' % (book['name'], book['count'],
                                    '' if page == 1 else ' 第 %d 页' % page, SITE_NAME)
    desc = '%s共 %d 个单词，其中 %d 个是本级别新增。每个单词都有音标、中文释义、例句、词根词缀和记忆方法，可在线打字默写、听写。' % (
        book['name'], book['count'], book.get('new', book['count']))
    body = ['<div class="crumbs wrap"><a href="/">首页</a><span>›</span><a href="/list">词书</a>'
            '<span>›</span>%s</div>' % esc(book['name']),
            '<div class="wrap"><h1 style="margin:18px 0 6px">%s</h1>'
            '<p class="lead">%s</p>'
            '<p><a class="btn btn-primary" href="/learn?book=%s">用这本词书开始背</a> '
            '<a class="btn" href="/list">换一本</a></p>'
            '<div class="toolbar"><input type="search" data-filter placeholder="在本页里搜单词或释义…" aria-label="搜索">'
            '<span class="hint">共 %d 词，每页 %d 词</span></div>'
            % (esc(book['name']), esc(desc), esc(book['slug']), book['count'], PER_PAGE),
            'AZNAV', 词表表格(entries), 分页HTML(base, page, total), '</div>']
    jsonld = {'@context': 'https://schema.org', '@type': 'ItemList',
              'name': '%s单词表' % book['name'], 'numberOfItems': book['count'],
              'itemListElement': [
                  {'@type': 'ListItem', 'position': i + 1, 'url': U(词条地址(e)), 'name': e['word']}
                  for i, e in enumerate(entries[:60])]}
    html_out = shell(title, desc, path, ''.join(body), jsonld=jsonld, cur='/list',
                     keywords='%s,%s单词表,%s词汇' % (book['name'], book['name'], book['name']),
                     updated=book.get('generated', TODAY))
    return html_out.replace('AZNAV', 字母导航())


def 字母导航(cur=''):
    letters = []
    for ch in 'abcdefghijklmnopqrstuvwxyz':
        cls = ' class="cur"' if ch == cur else ''
        letters.append('<a href="/letter/%s"%s>%s</a>' % (ch, cls, ch.upper()))
    return '<nav class="az" aria-label="按字母">%s</nav>' % ''.join(letters)


LETTER_WORDS = {}
for _w in WORDS:
    ch = _w['word'][:1].lower()
    if ch.isalpha():
        LETTER_WORDS.setdefault(ch, []).append(_w)
for _k in LETTER_WORDS:
    LETTER_WORDS[_k].sort(key=lambda w: w['word'].lower())


def page_letter(ch, page=1):
    entries = LETTER_WORDS.get(ch, [])
    total = max(1, (len(entries) + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total))
    chunk = entries[(page - 1) * PER_PAGE: page * PER_PAGE]
    base = '/letter/%s' % ch
    path = base if page == 1 else '%s/%d' % (base, page)
    title = '以 %s 开头的英语单词（%d 个）%s - %s' % (ch.upper(), len(entries),
                                                '' if page == 1 else ' 第 %d 页' % page, SITE_NAME)
    desc = '以字母 %s 开头的英语单词共 %d 个，全部带音标、中文释义、例句和词根词缀。' % (ch.upper(), len(entries))
    body = ['<div class="crumbs wrap"><a href="/">首页</a><span>›</span><a href="/w/">全部单词</a>'
            '<span>›</span>%s</div>' % ch.upper(),
            '<div class="wrap"><h1 style="margin:18px 0 6px">%s 开头的单词</h1>'
            '<p class="lead">共 %d 个，按字母顺序排列。</p>' % (ch.upper(), len(entries)),
            字母导航(ch), 词表表格(chunk), 分页HTML(base, page, total), '</div>']
    return shell(title, desc, path, ''.join(body), cur='/list',
                 keywords='%s开头的单词,%s开头的英语单词' % (ch.upper(), ch.upper()))


def page_w_index():
    cards = []
    for ch in 'abcdefghijklmnopqrstuvwxyz':
        n = len(LETTER_WORDS.get(ch, []))
        cards.append('<a class="root-card" href="/letter/%s"><b>%s</b><small>%d 个单词</small></a>'
                     % (ch, ch.upper(), n))
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>全部单词</div>'
            '<div class="wrap"><h1 style="margin:18px 0 6px">全部单词</h1>'
            '<p class="lead">词典里一共 %d 个英语单词，每个都有独立的词条页：'
            '音标、中文释义、中英对照例句、词根词缀、文化背景和记忆方法。</p>'
            '<p class="lead">另外还有 %d 个词形变化页 —— gone、went、studying 这种变形'
            '也各有一页，写清它是哪个词的什么形态。</p>'
            '<div class="toolbar"><input type="search" id="word-search" '
            'placeholder="输入单词或开头几个字母…" aria-label="搜索单词" '
            'autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">'
            '<span class="hint" id="search-hint">按字母往下翻，或者直接搜</span></div>'
            '<div class="rel-grid" id="search-result" hidden></div>'
            '<div id="letter-cards"><div class="root-grid">%s</div></div></div>'
            % (len(WORDS), len(词形页), ''.join(cards)))
    return shell('全部英语单词索引（A–Z，%d 个） - %s' % (len(WORDS), SITE_NAME),
                 '按字母浏览本站收录的 %d 个英语单词，每个词都有音标、释义、例句、词根词缀和记忆方法。' % len(WORDS),
                 '/w/', body, cur='/list')


def page_list_index():
    cards = []
    for b in 词书展示():
        cards.append(
            '<a class="book-card" href="%s"><span class="tag tag-lv">%s</span>'
            '<span class="n">%d<small>词</small></span>'
            '<b>%s</b><p>%s</p><p class="go">本级别新增 %d 词 →</p></a>'
            % (esc(词书地址(b['slug'])), esc(b['level'] or '词书'), b['count'],
               esc(b['name']), esc(b['note']), b['new']))
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>词书</div>'
            '<div class="wrap"><h1 style="margin:18px 0 6px">词书</h1>'
            '<p class="lead">七本词书按考试大纲全量收录，也可以只看本级别新增的词。'
            '选一本直接开背，或者先浏览词表。</p>'
            '<div class="book-grid" style="margin-top:18px">%s</div>'
            '<div class="tips"><b>怎么选？</b>初中生从「初中核心词」开始；高中生直接上「高中必备词」；'
            '考四六级就选对应那本。每本都可以只看本级别新增的词，避免重复背已经会的。</div>'
            '</div>' % ''.join(cards))
    return shell('英语词书（中考/高考/四级/六级/考研） - %s' % SITE_NAME,
                 '七本词书共 7954 个单词：初中核心词、高中必备词、四级、六级、考研、托福雅思 GRE。'
                 '每个单词都有音标、释义、例句、词根词缀，支持在线打字默写与听写。',
                 '/list', body, cur='/list', keywords='英语词书,四六级词汇表,高考词汇表,考研词汇表')


def page_roots_index():
    cards = []
    for r in sorted(ROOTS, key=lambda x: (x['key'].lower(), )):
        cards.append('<a class="root-card" href="/roots/%s"><b>%s</b>'
                     '<small>%s</small><span class="cnt">%d 个本站单词</span></a>'
                     % (esc(r['slug']), esc(r['key']), esc(r['meaning'] or r['class']), len(r['words'])))
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>词根词缀</div>'
            '<div class="wrap"><h1 style="margin:18px 0 6px">词根词缀</h1>'
            '<p class="lead">%d 个常用词根、前缀和后缀，每个都列出本站词表里的例词。'
            '记单词最省力的办法，是先记住这些「零件」。</p>'
            '<div class="root-grid">%s</div></div>' % (len(ROOTS), ''.join(cards)))
    return shell('英语词根词缀大全（%d 个） - %s' % (len(ROOTS), SITE_NAME),
                 '常用英语词根、前缀、后缀共 %d 条，每条列出本站词表里的例词，方便按词根记单词。' % len(ROOTS),
                 '/roots', body, cur='/roots', keywords='英语词根,词缀,词根词缀记忆法')


def page_root(root):
    path = '/roots/' + root['slug']
    title = '%s 是什么意思_%s 词根词缀与例词 - %s' % (root['key'], root['key'], SITE_NAME)
    desc = '%s：%s。本站收录 %d 个含这个词根/词缀的单词。' % (
        root['key'], root['meaning'] or root['class'] or '英语词根词缀', len(root['words']))
    items = []
    for s in root['words']:
        w = BY_SLUG.get(s)
        if not w:
            continue
        items.append('<a href="%s">%s<small>%s</small></a>'
                     % (esc(词条地址(w)), esc(w['word']),
                        esc((释义行(w)[0][:20] if 释义行(w) else w.get('us', '')))))
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>'
            '<a href="/roots">词根词缀</a><span>›</span>%s</div>'
            '<div class="wrap-narrow prose"><h1 style="margin:18px 0 6px">%s</h1>'
            '<p class="entry-summary">%s%s</p>'
            '<h2>本站例词（%d 个）</h2><div class="rel-grid">%s</div>'
            '<h2>怎么用</h2><p>先记住这个词根的意思，再回头看你正在背的词 —— '
            '同一个词根往往能一次串起十几个词，比一个字母一个字母硬背省力得多。'
            '点上面的词可以直接进词条页，里面有例句和记忆方法。</p></div>'
            % (esc(root['slug']), esc(root['key']),
               esc(root['meaning'] or ''), ('（%s）' % esc(root['origin'])) if root.get('origin') else '',
               len(items), ''.join(items)))
    jsonld = {'@context': 'https://schema.org', '@type': 'DefinedTerm', 'name': root['key'],
              'description': root['meaning'], 'url': U(path)}
    return shell(title, desc, path, body, cur='/roots', jsonld=jsonld)


# ---------------------------------------------------------------- 首页 / 学习器 / 说明页
MODES = [
    ('card', '卡牌速览', '正面单词、反面释义，自己判断认不认识。最快过一遍新词的方式。'),
    ('typing', '打字默写', '看中文敲英文，错一个字母都算错，专治「看着认识、写不出来」。'),
    ('dictation', '听写辨词', '只放发音不给拼写，把「音 → 形」这条路走通。'),
    ('cloze', '例句填空', '在真实例句里把词填回去，顺便记住搭配和用法。'),
    ('choice', '选择题', '英→中 或 中→英 四选一，通勤路上几秒钟一个词。'),
]


def page_home():
    books = 词书展示()
    cards = []
    for b in books:
        cards.append('<a class="book-card" href="%s"><span class="tag tag-lv">%s</span>'
                     '<span class="n">%d<small>词</small></span><b>%s</b><p>%s</p>'
                     '<p class="go">开始背 →</p></a>'
                     % (esc(词书地址(b['slug'])), esc(b['level'] or '词书'), b['count'],
                        esc(b['name']), esc(b['note'])))
    modes = ''.join('<div class="mode-card"><h3>%s</h3><p>%s</p></div>' % (esc(t), esc(d))
                    for _, t, d in MODES)
    faq = ''.join('<details class="faq"><summary>%s</summary><p>%s</p></details>'
                  % (esc(x['q']), esc(x['a'])) for x in CFG['faq'])
    guides = ''.join('<li><a href="/guide/%s">%s</a></li>' % (esc(g['slug']), esc(g['title']))
                     for g in 教程.GUIDES)
    body = (
        '<section class="hero"><div class="wrap"><h1>英语单词，免费背到会</h1>'
        '<p>%s。每个词都有音标、中文释义、中英对照例句、词根词缀、文化背景和记忆方法，'
        '还能用打字默写、听写、例句填空练到会写。不用注册，不装 App，没有广告。</p>'
        '<div class="actions"><a class="btn btn-primary" href="/learn">开始背单词</a>'
        '<a class="btn" href="/list">先看看词书</a></div>'
        '<div class="stat-row"><span><b>%d</b>个单词词条</span><span><b>%d</b>本词书</span>'
        '<span><b>5</b>种练习模式</span><span><b>%d</b>个词根词缀</span><span><b>0</b>广告</span></div>'
        '</div></section>'
        '<div class="wrap"><div class="section-title"><h2>选一本词书开始</h2><a href="/list">全部词书 →</a></div>'
        '<div class="book-grid">%s</div>'
        '<div class="section-title"><h2>五种练法</h2><span class="hint">键盘可以全程操作：空格发音、回车提交、数字键选答案</span></div>'
        '<div class="mode-grid">%s</div>'
        '<div class="section-title"><h2>为什么这个站记得住</h2></div>'
        '<div class="mode-grid">'
        '<div class="mode-card"><h3>内容够深</h3><p>每个词都有词义分析、3–6 条中英例句、词根、词缀、'
        '文化背景、单词变形、记忆方法和小故事——不是只有一行中文意思。</p></div>'
        '<div class="mode-card"><h3>只存在你浏览器里</h3><p>学过的词、答错的词、'
        '下次什么时候复习，全部记在本地。不登录、不上传，换设备可以用导出/导入搬家。</p></div>'
        '<div class="mode-card"><h3>离线也能用</h3><p>第一次打开后浏览器会缓存页面和词库，'
        '断网也能继续背。加载不出真人发音时自动切到浏览器语音朗读。</p></div>'
        '<div class="mode-card"><h3>永久免费</h3><p>没有会员墙、没有背单词上限、没有弹窗广告。'
        '内容由本站整理校对，词条页对搜索引擎和 AI 搜索都开放。</p></div>'
        '</div>'
        '<div class="section-title"><h2>背单词方法</h2><a href="%s">全部教程 →</a></div>'
        '<div class="tips"><ul style="padding-left:20px;margin:0">%s</ul></div>'
        '<div class="section-title"><h2>常见问题</h2></div>%s'
        '</div>' % (esc(CFG['tagline']), len(WORDS), len(词书展示()), len(ROOTS),
                    ''.join(cards), modes, GUIDE_HUB, guides, faq))
    jsonld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'WebSite', 'name': SITE_NAME, 'url': SITE_URL + '/',
         'inLanguage': 'zh-CN',
         'description': CFG['description'],
         'potentialAction': {'@type': 'SearchAction',
                             'target': U('/list/all') + '?q={search_term_string}',
                             'query-input': 'required name=search_term_string'}},
        {'@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': x['q'],
             'acceptedAnswer': {'@type': 'Answer', 'text': x['a']}} for x in CFG['faq']]},
    ]}
    return shell('%s —— 免费在线背单词（中考/高考/四级/六级/考研）' % SITE_NAME,
                 CFG['description'], '/', body, og='og/home.jpg', jsonld=jsonld,
                 keywords=CFG['keywords'])


def page_learn():
    books = 词书展示()
    options = ''.join('<option value="%s">%s（%d 词）</option>' % (esc(b['slug']), esc(b['name']), b['count'])
                      for b in books)
    body = (
        '<div class="crumbs wrap"><a href="/">首页</a><span>›</span>背单词</div>'
        '<div class="learn-app" id="app">'
        '<noscript><div class="panel"><p>学习器需要开启 JavaScript 才能使用。'
        '你仍然可以直接浏览 <a href="/list">词表</a> 和 <a href="/w/">词条页</a>。</p></div></noscript>'
        '<section class="panel" id="setup">'
        '<h2>① 选词书</h2><div class="chip-row" id="book-chips"></div>'
        '<p class="hint" style="text-align:left;margin:10px 0 0">'
        '词书按考试大纲全量收录；勾上「只看本级别新增」可以跳过已经会的基础词。</p>'
        '<p style="margin:12px 0 0"><label><input type="checkbox" id="only-new"> 只看本级别新增</label> '
        '<label style="margin-left:16px">每日目标 <select id="goal">'
        '<option>10</option><option selected>20</option><option>30</option><option>50</option>'
        '</select> 词</label></p>'
        '<h2 style="margin-top:20px">② 选练法</h2><div class="chip-row" id="mode-chips"></div>'
        '<h2 style="margin-top:20px">③ 开始</h2>'
        '<p style="margin:0 0 14px"><button class="btn btn-primary" id="start">开始学习</button> '
        '<button class="btn" id="review">复习到期的词</button> '
        '<button class="btn btn-ghost" id="open-settings">设置</button></p>'
        '<p class="hint" style="text-align:left">键盘可以全程操作：空格发音、回车提交、数字键选答案；'
        '按 <kbd>?</kbd> 看全部快捷键。</p>'
        '<div id="dashboard"></div>'
        '</section>'
        '<section class="panel" id="session" hidden>'
        '<div class="stage-top"><span id="progress-text"></span><span id="mode-name"></span></div>'
        '<div class="progress-line"><i id="progress-bar" style="width:0"></i></div>'
        '<div class="stage" id="stage"></div>'
        '</section>'
        '<section class="panel" id="summary" hidden></section>'
        '<div class="panel" id="settings" hidden>'
        '<h2>设置</h2>'
        '<p><label>发音方式：<select id="voice">'
        '<option value="auto">真人发音优先（联网时音质更好）</option>'
        '<option value="browser">只用浏览器语音（离线可用）</option>'
        '</select></label></p>'
        '<p><label>例句语音：<select id="voice-name">'
        '<option value="">自动挑一个（推荐）</option>'
        '</select></label> '
        '<button class="btn btn-ghost" id="try-voice" type="button">试听</button></p>'
        '<p class="hint" style="text-align:left">在线真人发音只覆盖单词；例句和小故事一律用'
        '浏览器自带的语音朗读。有些系统默认的英文语音很难听（macOS 上默认会挑到老合成音），'
        '这里可以自己换一个，换完点「试听」听听看。</p>'
        '<p><label>每组词数：<select id="group">'
        '<option>5</option><option selected>10</option><option>20</option><option>50</option>'
        '</select></label></p>'
        '<p><button class="btn" id="export-progress">导出学习进度</button> '
        '<button class="btn" id="import-progress">导入学习进度</button> '
        '<input type="file" id="import-file" accept=".json" hidden></p>'
        '<p><button class="btn" id="export-anki">导出 Anki / CSV</button> '
        '<button class="btn" id="print-list">打印当前词书词表</button></p>'
        '<p class="hint" style="text-align:left">学习进度只存在这台设备的浏览器里，'
        '清除浏览器数据会一并清掉。换设备时请先「导出学习进度」，到新设备上导入。</p>'
        '<p><button class="btn btn-ghost" id="close-settings">收起</button></p>'
        '</div>'
        '<datalist id="book-options">%s</datalist>'
        '<div class="toast" id="toast" role="status" aria-live="polite"></div>'
        '</div>'
        '<script src="/assets/learn.js?v=%s" defer></script>' % (options, V))
    return shell('在线背单词（打字默写/听写/例句填空，免登录） - %s' % SITE_NAME,
                 '免登录的在线背单词工具：选词书后可用卡牌速览、打字默写、听写辨词、例句填空、选择题五种模式，'
                 '学习进度存在本地，按遗忘曲线安排复习。', '/learn', body, cur='/learn',
                 keywords='在线背单词,打字背单词,单词听写,四六级背单词')


def page_about():
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>关于本站</div>'
            '<div class="wrap-narrow prose" style="margin-top:20px">'
            '<h1>关于本站</h1>'
            '<p>%s 是一个免费的在线背单词网站，覆盖初中、高中、四级、六级、考研和出国考试词汇，'
            '一共 %d 个单词。每个词都有独立的词条页：音标、中文释义、中英对照例句、词根分析、词缀分析、'
            '发展历史与文化背景、单词变形、记忆辅助，以及一个带中文翻译的小故事。</p>'
            '<p>学习器提供卡牌速览、打字默写、听写辨词、例句填空、选择题五种练法，'
            '并按简化的遗忘曲线安排复习。所有学习记录只保存在你自己的浏览器里，'
            '我们不设账号、不收集个人信息、不上传任何学习数据。</p>'
            '<h2>怎么用最有效</h2>'
            '<p>新词先用卡牌速览过一遍，再用打字默写练拼写，第二天用听写辨词复查，'
            '然后在例句填空里确认会用。具体安排见 <a href="%s">背单词方法</a>。</p>'
            '<h2>联系</h2>'
            '<p>内容纠错、版权问题、功能建议：<a href="mailto:%s">%s</a>；'
            '版权与删除请求：<a href="mailto:%s">%s</a>。</p>'
            '<p class="updated">本站创建于 %s 年，词库数据版本：%s。</p>'
            '</div>' % (SITE_NAME, len(WORDS),
                        GUIDE_HUB,
                        esc(CFG['contactEmail']), esc(CFG['contactEmail']),
                        esc(CFG['legalEmail']), esc(CFG['legalEmail']),
                        CFG['startYear'], DATA_VERSION))
    return shell('关于本站 - %s' % SITE_NAME,
                 '关于随浪背单词：%d 个单词的免费在线词典与背单词工具，免登录、无广告、不上传学习数据。'
                 % len(WORDS), '/about', body, updated=TODAY)


def page_privacy():
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>隐私说明</div>'
            '<div class="wrap-narrow prose" style="margin-top:20px">'
            '<h1>隐私说明</h1>'
            '<p>一句话：<b>你在这个站上做什么，只有你自己的浏览器知道。</b></p>'
            '<h2>我们收集什么</h2>'
            '<p>不收集。本站没有账号系统，不需要手机号或邮箱，不要求任何个人信息。'
            '你背了哪些词、答对答错、下次复习时间，全部存在浏览器的 localStorage 里，'
            '不会发送到服务器，我们也看不到。</p>'
            '<h2>本地存了什么</h2>'
            '<ul><li><code>v4u.progress.v1</code>：每个词的熟练度与复习时间</li>'
            '<li><code>v4u.meta.v1</code>：当前词书、每日目标、连续天数、每日统计</li>'
            '<li><code>v4u.star.v1</code>：你加入生词本的词</li>'
            '<li><code>v4u.prefs.v1</code>：发音方式、每组词数等设置</li></ul>'
            '<p>清除浏览器数据、换浏览器或换设备，这些记录就会消失（清除前可以在学习器里导出备份）。</p>'
            '<h2>第三方请求</h2>'
            '<ul><li>真人发音会向 <code>dict.youdao.com</code> 请求音频；不想联网时可在设置里切换为浏览器语音。</li>'
            '<li>页脚赞赏码图片来自本站主站 <code>suilang.net</code>。</li>'
            '<li>本站会记录匿名的访问统计（页面浏览量），不用于识别个人。</li></ul>'
            '<h2>Cookie</h2><p>本站自身不写 Cookie。</p>'
            '<h2>联系</h2><p><a href="mailto:%s">%s</a></p></div>'
            % (esc(CFG['contactEmail']), esc(CFG['contactEmail'])))
    return shell('隐私说明 - %s' % SITE_NAME,
                 '随浪背单词不上传任何学习数据：没有账号，进度只存在浏览器本地，发音之外的请求都不涉及个人信息。',
                 '/privacy', body, updated=TODAY)


def page_guide_index():
    cards = []
    for g in 教程.GUIDES:
        cards.append('<a class="mode-card" href="/guide/%s"><h3>%s</h3><p>%s</p></a>'
                     % (esc(g['slug']), esc(g['title']), esc(g['desc'][:80] + '…')))
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>背单词方法</div>'
            '<div class="wrap"><h1 style="margin:18px 0 6px">背单词方法</h1>'
            '<p class="lead">四篇实操向的教程：怎么排计划、怎么用词根、打字和听写怎么练。'
            '都是可以今天照着做的具体步骤，不讲空话。</p>'
            '<div class="mode-grid" style="margin-top:18px">%s</div></div>' % ''.join(cards))
    return shell('背单词方法教程（计划 / 词根 / 打字 / 听力） - %s' % SITE_NAME,
                 '四篇背单词实操教程：四级四周计划、词根词缀入门、打字默写训练、听力词汇与听写三步法。',
                 GUIDE_HUB, body, cur=GUIDE_HUB, keywords='背单词方法,背单词计划,词根词缀,听写训练')


def page_guide(g):
    path = '/guide/' + g['slug']
    parts = []
    for h, paras in g['sections']:
        parts.append('<h2>%s</h2>' % esc(h))
        for p in paras:
            parts.append('<p>%s</p>' % re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', esc(p)))
    faq = ''
    if g.get('faq'):
        faq = '<h2>常见问题</h2>' + ''.join(
            '<details class="faq"><summary>%s</summary><p>%s</p></details>' % (esc(q), esc(a))
            for q, a in g['faq'])
    body = ('<div class="crumbs wrap"><a href="/">首页</a><span>›</span>'
            '<a href="%s">背单词方法</a><span>›</span>%s</div>'
            '<article class="wrap-narrow prose" style="margin-top:18px">'
            '<h1>%s</h1><p class="entry-summary">%s</p>%s%s'
            '<p class="updated">最后更新：<time datetime="%s">%s</time></p>'
            '<p style="margin-top:20px"><a class="btn btn-primary" href="/learn">去背单词</a> '
            '<a class="btn" href="%s">看别的教程</a></p>'
            '</article>' % (GUIDE_HUB, esc(g['title']), esc(g['title']), esc(g['summary']),
                            ''.join(parts), faq, TODAY, TODAY, GUIDE_HUB))
    jsonld = {'@context': 'https://schema.org', '@type': 'Article',
              'headline': g['title'], 'description': g['desc'], 'inLanguage': 'zh-CN',
              'datePublished': TODAY, 'dateModified': TODAY,
              'author': {'@type': 'Organization', 'name': SITE_NAME},
              'publisher': {'@type': 'Organization', 'name': SITE_NAME},
              'mainEntityOfPage': U(path)}
    if g.get('faq'):
        jsonld = {'@context': 'https://schema.org', '@graph': [
            jsonld,
            {'@type': 'FAQPage', 'mainEntity': [
                {'@type': 'Question', 'name': q,
                 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in g['faq']]}]}
    return shell('%s - %s' % (g['title'], SITE_NAME), g['desc'], path, body,
                 cur=GUIDE_HUB, jsonld=jsonld, keywords=g.get('keywords'))


def page_404():
    body = ('<div class="center-page"><h1>404</h1>'
            '<p class="lead">这个地址没有对应的页面。可能是单词拼错了，或者链接过期了。</p>'
            '<p style="margin-top:20px"><a class="btn btn-primary" href="/learn">去背单词</a> '
            '<a class="btn" href="/list">看词书</a> '
            '<a class="btn btn-ghost" href="/w/">全部单词</a></p></div>')
    return shell('页面没找到（404） - %s' % SITE_NAME,
                 '这个地址没有对应的页面。', '/404', body, noindex=True)


# ---------------------------------------------------------------- 学习器数据分片
def gen_shards():
    os.makedirs(os.path.join(BASE, 'data', 'words'), exist_ok=True)
    total_files = 0
    for book in BOOKS:
        slugs = book['words']
        for n in range(0, len(slugs), SHARD):
            chunk = slugs[n:n + SHARD]
            payload = {'book': book['slug'], 'page': n // SHARD + 1,
                       'total': len(slugs), 'words': []}
            for s in chunk:
                w = BY_SLUG.get(s)
                if not w:
                    continue
                payload['words'].append({
                    's': w['slug'], 'w': w['word'],
                    'u': w.get('us') or '', 'k': w.get('uk') or '',
                    't': 释义行(w)[:3],
                    'e': [[x.get('en', ''), x.get('zh', '')] for x in (w.get('sentences') or [])[:3]],
                    'b': w.get('tags') or [], 'f': w.get('frq') or 0,
                    'x': w.get('exchange') or '',
                })
            rel = 'data/words/%s.%d.json' % (book['slug'], n // SHARD + 1)
            write_file(rel, json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
            total_files += 1
    return total_files


# ---------------------------------------------------------------- 站点文件
def gen_sitemap(entries):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, priority in entries:
        parts.append('<url><loc>%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>'
                     % (esc(U(path)), esc(lastmod), priority))
    parts.append('</urlset>')
    return '\n'.join(parts) + '\n'


def gen_robots():
    return ('User-agent: *\n'
            'Allow: /\n\n'
            '# 不限制任何爬虫（含 GPTBot、ClaudeBot、PerplexityBot 等 AI 搜索）：\n'
            '# 先被爬到，才有可能被引用。只挡掉纯资源目录，省点抓取配额。\n'
            'Disallow: /assets/\n'
            'Disallow: /data/\n\n'
            'Sitemap: %s/sitemap.xml\n' % SITE_URL)


def gen_word_index():
    """全部单词 + 全部词形的总索引：[[单词, 地址], ...]，给「全部单词」目录页的搜索框用。"""
    rows = [(w['word'], 词条地址(w)) for w in WORDS]
    rows += [(it['f'], '/w/' + it['slug']) for it in 词形页]
    return json.dumps(sorted(rows, key=lambda x: x[0].lower()), ensure_ascii=False,
                      separators=(',', ':'))


def gen_llms():
    lines = ['# %s（%s）' % (SITE_NAME, CFG['nameEn']), '',
             '> 免费在线背单词网站，收录 %d 个英语单词，覆盖初中、高中、四级、六级、考研。'
             '每个单词都有独立词条页：音标、中文释义、中英对照例句、词根分析、词缀分析、'
             '文化背景、单词变形、记忆方法和小故事。学习器提供卡牌速览、打字默写、听写辨词、'
             '例句填空、选择题五种模式，进度存在浏览器本地，不需要注册。' % len(WORDS),
             '', '## 词书', '']
    for b in 词书展示():
        lines.append('- %s（%d 词，本级新增 %d）：%s' % (b['name'], b['count'], b['new'], U(词书地址(b['slug']))))
    lines += ['', '## 主要页面', '',
              '- 首页：%s' % (SITE_URL + '/'),
              '- 学习器：%s' % U('/learn'),
              '- 全部单词索引：%s' % U('/w/'),
              '- 词形变化页（%d 个，比如 %s）：went、studying 这类变形各有一个页面' % (
                  len(词形页), '、'.join(U('/w/' + it['slug']) for it in 词形页[:2])),
              '- 词根词缀（%d 条）：%s' % (len(ROOTS), U('/roots')),
              '- 背单词方法：%s' % U(GUIDE_HUB),
              ]
    for g in 教程.GUIDES:
        lines.append('  - %s：%s' % (g['title'], U('/guide/' + g['slug'])))
    lines += ['', '## 词条页示例', '']
    for slug in ('abandon', 'increase', 'respect', 'environment', 'contribute'):
        w = BY_SLUG.get(slug)
        if w:
            lines.append('- %s：%s —— %s' % (w['word'], U(词条地址(w)), 首段结论(w)))
    lines += ['', '## 说明', '',
              '- 每个词条页都带有 DefinedTerm 与 BreadcrumbList 结构化数据。',
              '- 词条内容由本站整理维护；音标、词频与考试分级来自公开词库的整理结果。',
              '- 页面可自由抓取，站点不限制 AI 爬虫；robots.txt 只挡静态资源目录。',
              '']
    return '\n'.join(lines)


def gen_manifest():
    return json.dumps({
        'name': SITE_NAME, 'short_name': CFG['shortName'] or SITE_NAME,
        'description': CFG['description'], 'start_url': '/', 'scope': '/',
        'display': 'standalone', 'background_color': '#f5f7fb', 'theme_color': '#f5f7fb',
        'lang': 'zh-CN',
        'icons': [{'src': '/icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
                  {'src': '/icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
                  {'src': '/icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png',
                   'purpose': 'maskable'}],
    }, ensure_ascii=False, indent=2) + '\n'


def gen_sw():
    core = ['/', '/learn', '/list', '/w/', '/assets/style.css?v=%s' % V,
            '/assets/dict.js?v=%s' % V, '/assets/learn.js?v=%s' % V,
            '/data/books.json', '/manifest.webmanifest', '/icons/icon-192.png']
    return ("""/* 离线缓存：断网也能继续背单词（由 build/gen.py 生成） */
const VERSION = '%s';
const CACHE = 'v4u-' + VERSION;
const CORE = %s;

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return Promise.all(CORE.map(function (url) {
      return cache.add(new Request(url, { cache: 'reload' })).catch(function () { });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (event) {
  const req = event.request;
  if (req.method !== 'GET') { return; }
  const url = new URL(req.url);
  if (url.origin !== location.origin) { return; }
  const isCacheable = url.pathname.indexOf('/assets/') === 0 ||
    url.pathname.indexOf('/data/words/') === 0 ||
    url.pathname.indexOf('/w/') === 0 ||
    /\\.(css|js|json|svg|png|jpg|jpeg|webp|ico|woff2)$/.test(url.pathname);

  if (isCacheable) {
    event.respondWith(caches.match(req).then(function (hit) {
      if (hit) { return hit; }
      return fetch(req).then(function (res) {
        const copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
        return res;
      });
    }));
    return;
  }

  event.respondWith(fetch(req).then(function (res) {
    const copy = res.clone();
    caches.open(CACHE).then(function (c) { c.put(req, copy); });
    return res;
  }).catch(function () {
    return caches.match(req).then(function (hit) { return hit || caches.match('/learn'); });
  }));
});
""" % (V, json.dumps(core, ensure_ascii=False, indent=2)))


def gen_version_js():
    return "window.ASSET_V = '%s';\n" % V


# ---------------------------------------------------------------- 分享图与图标
def _font(size, cjk=True):
    from PIL import ImageFont
    paths = (['/System/Library/Fonts/PingFang.ttc',
              '/System/Library/Fonts/Hiragino Sans GB.ttc',
              '/System/Library/Fonts/STHeiti Medium.ttc',
              '/Library/Fonts/Arial Unicode.ttf'] if cjk else
             ['/System/Library/Fonts/Supplemental/Georgia.ttf',
              '/Library/Fonts/Arial.ttf'])
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def 生成分享图(标题, 副标题, 文件名):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    W, H = 1200, 630
    img = Image.new('RGB', (W, H), '#f5f7fb')
    draw = ImageDraw.Draw(img)
    for y in range(H):                                  # 纵向渐变（浅色，顶部略微偏蓝）
        t = y / float(H)
        r = int(245 - (245 - 238) * t)
        g = int(247 - (247 - 242) * t)
        b = int(251 - (251 - 249) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    draw.rectangle([0, 0, 14, H], fill='#0e9f7d')
    draw.text((90, 150), 标题, font=_font(76), fill='#16233c')
    draw.text((92, 268), 副标题, font=_font(34), fill='#57688a')
    draw.text((92, 470), SITE_NAME, font=_font(30), fill='#0e9f7d')
    draw.text((92, 516), DOMAIN, font=_font(24), fill='#8492ab')
    path = os.path.join(BASE, 文件名)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, 'JPEG', quality=88, optimize=True)
    return True


def 生成图标():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    os.makedirs(os.path.join(BASE, 'icons'), exist_ok=True)
    for size in (192, 512):
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for y in range(size):                           # 渐变方块（近似圆角由遮罩完成）
            t = y / float(size)
            color = (int(46 + (79 - 46) * t), int(230 + (141 - 230) * t), int(184 + (255 - 184) * t), 255)
            draw.line([(0, y), (size, y)], fill=color)
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                               radius=int(size * 0.22), fill=255)
        img.putalpha(mask)
        d = ImageDraw.Draw(img)
        d.text((size * 0.5, size * 0.47), '背', font=_font(int(size * 0.5)), fill='#0b1220', anchor='mm')
        img.save(os.path.join(BASE, 'icons', 'icon-%d.png' % size))
    return True


# ---------------------------------------------------------------- 主流程
DATA_VERSION = json.load(open(os.path.join(BASE, 'data', 'books.json'),
                              encoding='utf-8')).get('generated', TODAY)


def main():
    import time
    t0 = time.time()
    pages = []                       # (path, lastmod, priority) 给 sitemap

    def add(rel, html, path, priority, lastmod=None):
        date = write_file(rel, html, change_date=lastmod)
        pages.append((path, date, priority))
        return date

    print('生成静态页……')
    add('index.html', page_home(), '/', '1.0')
    add('learn.html', page_learn(), '/learn', '0.9')
    add('list/index.html', page_list_index(), '/list', '0.8')
    add('w/index.html', page_w_index(), '/w/', '0.6')
    add('roots.html', page_roots_index(), '/roots', '0.6')
    add('guide/index.html', page_guide_index(), GUIDE_HUB, '0.6')
    add('about.html', page_about(), '/about', '0.3')
    add('privacy.html', page_privacy(), '/privacy', '0.3')
    add('404.html', page_404(), '/404', '0.1')
    for g in 教程.GUIDES:
        add('guide/%s.html' % g['slug'], page_guide(g), '/guide/' + g['slug'], '0.5')

    print('生成词条页（%d 个）……' % len(WORDS))
    for i, w in enumerate(WORDS, 1):
        path = 词条地址(w)
        add('w/' + 词条文件(w), page_word(w), path, '0.6', lastmod=w.get('updated'))
        if i % 1000 == 0:
            print('   已完成 %d / %d（%.0f 秒）' % (i, len(WORDS), time.time() - t0))

    print('生成词形页（%d 个）……' % len(词形页))
    for it in 词形页:
        add('w/%s.html' % it['slug'], page_form(it), '/w/' + it['slug'], '0.4', lastmod=词形版本)

    print('生成词表页……')
    for b in BOOKS:
        total = max(1, (len(b['words']) + PER_PAGE - 1) // PER_PAGE)
        for p in range(1, total + 1):
            path = 词书地址(b['slug']) if p == 1 else '%s/%d' % (词书地址(b['slug']), p)
            rel = 'list/%s.html' % b['slug'] if p == 1 else 'list/%s/%d.html' % (b['slug'], p)
            add(rel, page_book(b, p), path, '0.7' if p == 1 else '0.4',
                lastmod=DATA_VERSION)
    for ch, items in LETTER_WORDS.items():
        total = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
        for p in range(1, total + 1):
            path = '/letter/%s' % ch if p == 1 else '/letter/%s/%d' % (ch, p)
            rel = 'letter/%s.html' % ch if p == 1 else 'letter/%s/%d.html' % (ch, p)
            add(rel, page_letter(ch, p), path, '0.4')

    print('生成词根页（%d 个）……' % len(ROOTS))
    for r in ROOTS:
        add('roots/%s.html' % r['slug'], page_root(r), '/roots/' + r['slug'], '0.5')

    print('生成学习器数据分片……')
    n = gen_shards()
    print('   %d 个分片' % n)

    print('生成站点文件……')
    write_file('data/index.json', gen_word_index())
    write_file('sitemap.xml', gen_sitemap(
        sorted(pages, key=lambda x: (-float(x[2]), x[0]))))
    write_file('robots.txt', gen_robots())
    write_file('llms.txt', gen_llms())
    write_file('manifest.webmanifest', gen_manifest())
    write_file('sw.js', gen_sw())
    write_file('assets/version.js', gen_version_js())

    print('生成分享图与图标……')
    if 生成分享图('英语单词，免费背到会', '7954 个单词 · 音标 · 例句 · 词根词缀 · 打字默写', 'og/home.jpg'):
        print('   og/home.jpg')
    else:
        print('   跳过（没装 Pillow）')
    生成分享图('英语单词词条', '音标 · 释义 · 例句 · 词根词缀 · 记忆方法', 'og/word.jpg')
    for b in 词书展示():
        生成分享图(b['name'], '%d 个单词 · 打地基 / 提分 / 冲刺' % b['count'],
                'og/book-%s.jpg' % b['slug'])
    生成分享图('背单词方法', '计划 · 词根 · 打字 · 听写', 'og/guide.jpg')
    生成分享图('词根词缀', '%d 个常用词根前缀后缀' % len(ROOTS), 'og/roots.jpg')
    if 生成图标():
        print('   icons/icon-192.png / icon-512.png')

    save_state()
    print('\n完成：%d 个页面，用时 %.0f 秒' % (len(pages), time.time() - t0))
    print('本地预览：python3 -m http.server 8848')


if __name__ == '__main__':
    main()
