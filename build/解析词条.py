#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把《威威的 GPT 单词本》正文（Markdown 风格文本）拆成结构化数据。

上游正文的排版并不统一，同一节至少有四种写法：
    ### 分析词义        （三级标题）
    **分析词义**        （加粗）
    分析词义：          （中文冒号，正文换行在下面）
    词根分析：无词缀     （冒号后面直接跟正文）
还有相当一部分词条完全不带小标题，整段都是词义说明。

用法：
    from 解析词条 import split_sections, split_examples, split_story
"""
import re

# 上游所有可能出现的节标题 → 我们统一用的键
TITLES = [
    ('词义', ['分析词义', '词义分析', '词义', '释义', '单词分析', '单词释义']),
    ('例句', ['列举例句', '例句分析', '例句']),
    ('词根', ['词根分析', '词根']),
    ('词缀', ['词缀分析', '词缀']),
    ('文化', ['发展历史和文化背景', '发展历史与文化背景', '历史文化背景', '发展历史', '文化背景']),
    ('变形', ['单词变形', '词形变化', '变形']),
    ('记忆', ['记忆辅助', '记忆技巧', '记忆方法', '记忆']),
    ('故事', ['小故事', '例句故事', '故事']),
]

# 长的标题要排在前面，否则「词根」会先把「词根分析」吃掉
_TITLE_ALT = '|'.join(
    re.escape(t) for _, alts in TITLES for t in sorted(alts, key=len, reverse=True))
_TITLE2KEY = {t: k for k, alts in TITLES for t in alts}
_KEY_ALT = '|'.join(_TITLE2KEY)

# 行首的节标题：可带 # 号、可带 ** 加粗、可带「1.」这样的编号，可以只有标题，也可以「标题：正文」
# 上游正文里四种写法都出现过：
#     ### 分析词义
#     **1\. 分析词义**        （编号 + 加粗 + 转义的点）
#     词根分析：无词缀
#     小故事
_HEAD_TMPL = (
    r'^\s*(?:#{1,6}\s*)?'                     # 可选的 Markdown 标题号
    r'[_*]{0,2}\s*'                            # 可选的加粗/斜体起始
    r'(?:\d{1,2}\s*\\?\s*[.、)）]\s*)?'     # 可选的「1.」编号
    r'[_*]{0,2}\s*'
    r'[【\[]?'                                  # 有的写【分析词义】
    r'(?:[^\s_*]{1,20}的)?'                     # 「Marty的词义分析」这种带单词的前缀
    r'(?P<title>%s)'
    r'[】\]]?'
)
_TAIL = r'\s*[_*]{0,2}\s*'
_HEAD_INLINE = re.compile(_HEAD_TMPL % _TITLE_ALT + _TAIL +
                          r'[:：]\s*[_*]{0,2}\s*(?P<inline>\S.*?)\s*[_*]{0,2}\s*$')
_HEAD_ONLY = re.compile(_HEAD_TMPL % _TITLE_ALT + _TAIL +
                        r'[:：]?\s*[_*]{0,2}\s*$')

_CJK = re.compile(r'[\u3400-\u9fff]')
_ASCII_WORD = re.compile(r'[A-Za-z]')
# 例句条目开头的编号：1. / 1、 / 1) / ① / 例句1： / 例句二、
_NUM = re.compile(
    r'^\s*(?:[-*•·]\s*)?'
    r'(?:(?:例句|句子|Sentence|Example)\s*)?'
    r'(?:\(?\d{1,2}\)?[.、)）:]|\(\d{1,2}\)|[①②③④⑤⑥⑦⑧⑨⑩]'
    r'|[一二三四五六七八九十]{1,3}[、.)）:])\s*',
    re.I)
# 只由标点/符号组成的空条目
_JUNK = re.compile(r'^[\s*\-–—•·.、,，:：;；"“”\'‘’()（）\[\]【】]+$')
# 「名词用法：」「动词用法：」这类前缀
_LABEL = re.compile(r'^\s*[\u4e00-\u9fff A-Za-z]{1,8}\s*[:：]\s*')
# 英文与中文之间的分隔符
_SEP = re.compile(r'\s+(?:-|–|—|~|～|\||｜|／|/)\s+')


def _clean(text):
    """去掉正文里的 Markdown 残留与多余空白。"""
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_sections(content):
    """把整段正文切成 {节键: 正文文本}，节键见 TITLES。"""
    if not content:
        return {}
    text = content.replace('\r\n', '\n').replace('\r', '\n')
    out = {}
    cur = '词义'
    for raw_line in text.split('\n'):
        line = raw_line.rstrip()
        m = _HEAD_INLINE.match(line) or _HEAD_ONLY.match(line)
        if m:
            cur = _TITLE2KEY[m.group('title')]
            out.setdefault(cur, [])
            inline = (m.groupdict().get('inline') or '').strip()
            if inline:
                out[cur].append(inline)
            continue
        out.setdefault(cur, []).append(line)
    secs = {}
    for key, lines in out.items():
        body = _clean('\n'.join(lines))
        if body:
            secs[key] = body
    return secs


def split_examples(raw):
    """把「列举例句」一节拆成 [{'en': ..., 'zh': ...}]。"""
    if not raw:
        return []
    items, cur = [], []
    for line in raw.split('\n'):
        if _NUM.match(line) and cur:
            items.append('\n'.join(cur))
            cur = [_NUM.sub('', line)]
        elif _NUM.match(line):
            cur = [_NUM.sub('', line)]
        elif line.strip():
            cur.append(line.strip())
        else:
            cur.append('')
    if cur:
        items.append('\n'.join(cur))
    out = []
    for item in items:
        # 一条里塞了多组「英文（中文）」时先拆开
        for chunk in _split_multi(item):
            pair = _split_en_zh(chunk)
            # 丢掉「*」「——」这类只剩符号的空条目
            if len(re.sub(r'[^A-Za-z\u4e00-\u9fff]', '', pair['en'] + pair['zh'])) < 3:
                continue
            out.append(pair)
    return out


def _split_multi(text):
    """一条里出现两组以上「英文（中文）」时，按右括号切段。"""
    marks = list(re.finditer(r'[（(][^（()）]{2,}[)）]', text))
    if len(marks) < 2:
        return [text]
    out, pos = [], 0
    for mark in marks:
        out.append(text[pos:mark.end()])
        pos = mark.end()
    if text[pos:].strip():
        out.append(text[pos:])
    return out


def _split_en_zh(text):
    """一条例句拆成英文和中文。"""
    text = _clean(text).strip().strip('"“”\'')
    text = re.sub(r'^\s*[-*•·]\s+', '', text)          # 去掉句首的项目符号
    text = _LABEL.sub('', text).strip()
    if not text or _JUNK.match(text):
        return {'en': '', 'zh': ''}

    # 情况 A0：英文（可带引号）+ 括号里的中文
    m = re.match(r'^["“]?(?P<en>[A-Za-z][^"“”]*?[.!?"”])\s*[（(](?P<zh>.*)[)）]\s*$', text)
    if m and _CJK.search(m.group('zh')):
        return {'en': _tidy(m.group('en')), 'zh': _tidy(m.group('zh'))}

    # 情况 A：英文 - 中文（破折号/斜杠分隔）
    parts = _SEP.split(text, maxsplit=1)
    if len(parts) == 2 and _CJK.search(parts[1]) and not _CJK.search(parts[0]):
        return {'en': _tidy(parts[0]), 'zh': _tidy(parts[1])}

    # 情况 B：一行英文、一行中文
    lines = [x.strip() for x in text.split('\n') if x.strip()]
    if len(lines) > 1:
        first_cjk = next((i for i, x in enumerate(lines) if _CJK.search(x)), None)
        if first_cjk:
            en = ' '.join(lines[:first_cjk])
            zh = ' '.join(lines[first_cjk:])
            if _ASCII_WORD.search(en):
                return {'en': _tidy(en), 'zh': _tidy(zh)}

    # 情况 C：中文在前，英文被括号或引号包着
    if _CJK.search(text[0]):
        for m in re.finditer(r'[（(]([^（()）]+)[)）]|["“]([^"”]+)["”]', text):
            seg = m.group(1) or m.group(2) or ''
            if _ASCII_WORD.search(seg) and len(seg) >= 6:
                en = _tidy(seg)
                zh = _tidy(text[:m.start()] + ' ' + text[m.end():])
                return {'en': en, 'zh': zh}
        return {'en': '', 'zh': _tidy(text)}

    # 情况 D：英文句子后面直接跟中文
    m = _CJK.search(text)
    if m:
        return {'en': _tidy(text[:m.start()]), 'zh': _tidy(text[m.start():])}

    return {'en': _tidy(text).strip(), 'zh': ''}


def _tidy(text):
    """收尾清理：去掉首尾空白与孤零零的括号/引号。"""
    text = _clean(text or '').strip()
    while text and text[0] in '"“”\'（(【[':
        text = text[1:].strip()
    while text and text[-1] in '"“”\'）)】](（':
        text = text[:-1].strip()
    return re.sub(r'\s{2,}', ' ', text).strip()


def split_story(raw):
    """小故事：英文一段 + 中文一段。"""
    if not raw:
        return {'en': '', 'zh': ''}
    text = _clean(raw)
    pair = re.match(r'^["“]?(?P<en>[A-Za-z][\s\S]*?[.!?"”])\s*[（(](?P<zh>[\s\S]*)[)）]\s*$', text)
    if pair and _CJK.search(pair.group('zh')):
        return {'en': _tidy(pair.group('en')), 'zh': _tidy(pair.group('zh'))}
    m = _CJK.search(text)
    if not m:
        return {'en': text, 'zh': ''}
    en = text[:m.start()].strip()
    zh = text[m.start():].strip()
    if not en:
        # 中文在前，英文在后
        tail = re.search(r'([A-Z][^。！？]*[.!?])\s*$', zh)
        if tail:
            return {'en': tail.group(1).strip(), 'zh': zh[:tail.start()].strip()}
        return {'en': '', 'zh': zh}
    return {'en': en.strip(' ."“”\''), 'zh': zh}


def sentences_of(sections, word=''):
    """取例句列表；word 给定时，优先返回句子里真的出现了这个词的句子。"""
    items = split_examples(sections.get('例句', ''))
    if not word:
        return items
    stem = word.strip().lower()
    hit = [x for x in items if stem and stem in x['en'].lower()]
    return hit or items
