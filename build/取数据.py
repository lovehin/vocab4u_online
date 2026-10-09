#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把四个上游数据源合成站点要用的数据文件：

    data/dictionary.json   8027 个词条（生成器用，进 Git）
    data/books.json        七本词书 + 词序（生成器、学习器都用，进 Git）
    data/roots.json        词根词缀索引（生成器用，进 Git）
    data/forms.json        词形变化索引（生成器用，进 Git）
    data/words/*.json      学习器分片（由 build/gen.py 生成，不进 Git）

原始文件放 build/_raw/（gitignore），缺哪个自动下哪个。
运行：python3 build/取数据.py
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 解析词条 as P            # noqa: E402
import 上游数据 as U            # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')
数据版本 = '2026-10-08'

# 词书定义：slug → (名称, 一句话说明, 取词标签, 是否排除更基础的书)
词书 = [
    ('zhongkao', '初中核心词', '中考大纲词汇', ['zk'], []),
    ('gaokao', '高中必备词', '高考大纲词汇', ['gk'], []),
    ('cet4', '大学四级', '四级大纲词汇', ['cet4'], []),
    ('cet6', '大学六级', '六级大纲词汇', ['cet6'], []),
    ('kaoyan', '考研词汇', '考研英语大纲词汇', ['ky'], []),
    ('chuguo', '托福雅思 GRE', '出国考试高频词', ['toefl', 'ielts', 'gre'],
     ['zk', 'gk', 'cet4', 'cet6', 'ky']),
]
SLUG_RE = re.compile(r'[^a-z0-9]+')


def make_slug(word):
    slug = SLUG_RE.sub('-', word.strip().lower()).strip('-')
    return slug or 'word'


def unique_slugs(words):
    """给每个词一个站内唯一 slug，撞车时追加 -2、-3。"""
    used, out = {}, {}
    for word in words:
        base = make_slug(word)
        slug = base
        n = 1
        while slug in used and used[slug] != word:
            n += 1
            slug = '%s-%d' % (base, n)
        used[slug] = word
        out[word] = slug
    return out


# ECDICT 的 exchange 字段用单字母代码标记变形，这里按展示顺序排好
词形代码 = [
    ('p', '过去式'), ('d', '过去分词'), ('i', '现在分词'),
    ('3', '第三人称单数'), ('s', '复数'), ('r', '比较级'), ('t', '最高级'),
]
词形标签 = dict(词形代码)
词形次序 = {code: i for i, (code, _) in enumerate(词形代码)}
词形格式 = re.compile(r"^[a-z][a-z'\-]*$")
_TOKEN = re.compile(r"[a-z][a-z'\-]*")


def 拆词形(exchange):
    """ECDICT 的 exchange 字段 → [(代码, 词形), ...]。"""
    out = []
    for part in (exchange or '').split('/'):
        code, sep, form = part.partition(':')
        form = form.strip()
        if sep and code in 词形标签 and form:
            out.append((code, form))
    return out


def 建词形索引(words, ecdict, ipa_us, ipa_uk):
    """把所有词条的变形收成一张表：变形词形 → 原词 / 音标 / 释义 / 在语料里出现的句子数。

    变形本身也是词条的（比如 advanced 同时是 advance 的过去式）不重复建页，
    只记下关系，两边互相链接；生成器只给「在本站例句和小故事里真的出现过」的
    变形单独建页，其余照样列在原词条页的「词形变化」里，只是不给链接 ——
    免得给搜索引擎塞一堆空壳页面。
    """
    词条slug = {}
    for w in words:
        词条slug.setdefault(w['word'].lower(), w['slug'])
    语料 = collections.Counter()
    for w in words:
        for s in w.get('sentences') or []:
            for tok in set(_TOKEN.findall((s.get('en') or '').lower())):
                语料[tok] += 1
        en = (w.get('story') or {}).get('en') or ''
        for tok in set(_TOKEN.findall(en.lower())):
            语料[tok] += 1

    频率 = {w['slug']: (w['frq'] or 10 ** 9, w['slug']) for w in words}
    表 = {}
    for w in words:
        for code, form in 拆词形(w.get('exchange')):
            key = form.lower()
            if not 词形格式.match(key) or key == w['slug']:
                continue
            slot = 表.get(key)
            if slot is None:
                slot = {'f': form, 'b': {}, 'n': 语料.get(key, 0)}
                本身 = 词条slug.get(key)
                if 本身:
                    slot['w'] = 本身          # 这个变形本身就是一条词条
                else:
                    # 音标优先用 ipa-dict（带斜杠、覆盖变形词），再退回 ECDICT；
                    # ECDICT 里有些变形词的 phonetic 就是单词本身（bled、did 这种），别用
                    音 = ipa_us.get(key, '') or ipa_uk.get(key, '')
                    if not 音:
                        raw = ((ecdict.get(key) or {}).get('phonetic') or '').strip()
                        if raw and raw.lower() != key:
                            音 = '/' + raw + '/'
                    slot['ipa'] = 规范音标(音)
                    slot['tr'] = 拆中文释义((ecdict.get(key) or {}).get('translation'))
                表[key] = slot
            slot['b'].setdefault(w['slug'], set()).add(code)

    出 = []
    for key in sorted(表):
        slot = 表[key]
        bases = sorted(slot['b'], key=lambda s: 频率.get(s, (10 ** 9, s)))
        条目 = {'f': slot['f'], 'n': slot['n'],
                'b': [[s, sorted(slot['b'][s], key=lambda c: 词形次序[c])] for s in bases]}
        if slot.get('w'):
            条目['w'] = slot['w']
        else:
            条目['ipa'] = slot.get('ipa', '')
            条目['tr'] = slot.get('tr') or []
        出.append(条目)
    return 出


def 合并重复词(recs):
    """同一个词（不分大小写）可能有多条记录，合并成一条：取最长的那条为主，缺的节从别的补。"""
    groups = {}
    for rec in recs:
        key = rec['word'].strip().lower()
        groups.setdefault(key, []).append(rec)
    merged = []
    for key, group in groups.items():
        parsed = []
        for rec in group:
            secs = P.split_sections(rec['content'])
            parsed.append((len(rec['content']), rec['word'], secs))
        parsed.sort(key=lambda x: -x[0])
        main_word = parsed[0][1]
        secs = {}
        for _, _, s in sorted(parsed, key=lambda x: -x[0]):
            for k, v in s.items():
                if k not in secs or len(v) > len(secs[k]):
                    secs[k] = v
        merged.append({'word': main_word, 'sections': secs,
                       'length': parsed[0][0]})
    return merged


def 拆中文释义(raw):
    if not raw:
        return []
    lines = []
    for line in re.split(r'\\n|\n', raw):
        line = line.strip().lstrip('*').strip()
        if not line or line.startswith('[网络]'):
            continue
        lines.append(line)
    return lines[:8]


def 规范音标(text):
    """上游音标里常见的形近字符统一一下，显示更好看。"""
    if not text:
        return ''
    for a, b in (('ә', 'ə'), ('ɡ', 'g'), ('∶', ':'), ('’', "'"), ('‘', "'"), ('–', '-'), ('—', '-')):
        text = text.replace(a, b)
    return re.sub(r'\s{2,}', ' ', text).strip()


def 转数字(value):
    try:
        return int(str(value).strip() or 0)
    except ValueError:
        return 0


def main():
    print('读取上游数据……')
    recs = U.读词典正文()
    ecdict = U.读ECDICT()
    ipa_us, ipa_uk = U.读音标()
    roots = U.读词根()

    merged = 合并重复词(recs)
    print('词条记录 %d 条 → 去重后 %d 个词' % (len(recs), len(merged)))
    slug_of = unique_slugs([m['word'] for m in merged])

    words = []
    for item in merged:
        word = item['word']
        key = word.lower()
        row = ecdict.get(key) or {}
        tags = [t for t in (row.get('tag') or '').split() if t]
        phonetic_uk = 规范音标((row.get('phonetic') or '').strip() or ipa_uk.get(key, ''))
        phonetic_us = 规范音标(ipa_us.get(key, '') or (row.get('phonetic') or '').strip())
        sections = item['sections']
        entry = {
            'word': word,
            'slug': slug_of[word],
            'us': phonetic_us,
            'uk': phonetic_uk,
            'trans': 拆中文释义(row.get('translation')),
            'definition': (row.get('definition') or '').strip(),
            'tags': tags,
            'frq': 转数字(row.get('frq')),
            'bnc': 转数字(row.get('bnc')),
            'collins': 转数字(row.get('collins')),
            'oxford': 转数字(row.get('oxford')),
            'exchange': (row.get('exchange') or '').strip(),
            'sections': sections,
            'sentences': P.sentences_of(sections, word)[:6],
            'story': P.split_story(sections.get('故事', '')),
            'updated': 数据版本,
        }
        entry['books'] = [b[0] for b in 词书
                          if set(tags) & set(b[3]) and not (set(tags) & set(b[4]))]
        entry['books'].append('all')
        words.append(entry)

    words.sort(key=lambda w: w['slug'])
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, 'dictionary.json'), 'w', encoding='utf-8') as fh:
        json.dump(words, fh, ensure_ascii=False, separators=(',', ':'))

    # 词书 + 词序（高频优先）
    def 频率(w):
        return (w['frq'] or 10 ** 9, w['bnc'] or 10 ** 9, w['slug'])

    books = []
    for slug, name, desc, tags, exclude in 词书:
        picked = [w for w in words if set(w['tags']) & set(tags) and not (set(w['tags']) & set(exclude))]
        books.append({'slug': slug, 'name': name, 'desc': desc,
                      'count': len(picked), 'tags': tags, 'exclude': exclude,
                      'words': [w['slug'] for w in sorted(picked, key=频率)]})
    books.append({'slug': 'all', 'name': '全部词库', 'desc': '词典里全部单词',
                  'count': len(words), 'tags': [], 'exclude': [],
                  'words': [w['slug'] for w in sorted(words, key=频率)]})
    # 「本级新增」= 不在更基础那几本里的词（初中 ⊂ 高中 ⊂ 四级 ⊂ 六级 ⊂ 考研）
    已收录 = set()
    for book in books:
        if book['slug'] == 'all':
            book['new'] = book['count']
            book['newWords'] = list(book['words'])          # 「全部词库」没有新增一说
            continue
        fresh = [s for s in book['words'] if s not in 已收录]
        book['new'] = len(fresh)
        book['newWords'] = fresh                            # 学习器的「只看本级别新增」用
        已收录 |= set(book['words'])
    with open(os.path.join(DATA, 'books.json'), 'w', encoding='utf-8') as fh:
        json.dump({'generated': 数据版本, 'books': books}, fh,
                  ensure_ascii=False, separators=(',', ':'))

    # 词形变化（过去式 / 过去分词 / 现在分词 / 三单 / 复数 / 比较级 / 最高级）
    forms = 建词形索引(words, ecdict, ipa_us, ipa_uk)
    会建页 = [f for f in forms if f['n'] > 0 and 'w' not in f]
    with open(os.path.join(DATA, 'forms.json'), 'w', encoding='utf-8') as fh:
        json.dump({'generated': 数据版本, 'codes': dict(词形代码), 'forms': forms},
                  fh, ensure_ascii=False, separators=(',', ':'))

    # 词根词缀：只留本站有 ≥3 个例词的
    by_lower = {w['word'].lower(): w for w in words}
    root_out = []
    for key, info in roots.items():
        hits = [by_lower[x.lower()]['slug'] for x in info['example'] if x.lower() in by_lower]
        if len(hits) < 3:
            continue
        root_out.append({'key': key, 'meaning': info['meaning'], 'class': info['class'],
                         'origin': info['origin'], 'words': sorted(set(hits))})
    root_out.sort(key=lambda r: (r['key'].strip('-').lower()))
    with open(os.path.join(DATA, 'roots.json'), 'w', encoding='utf-8') as fh:
        json.dump(root_out, fh, ensure_ascii=False, separators=(',', ':'))

    print('输出：dictionary %d 词 / books %d 本 / roots %d 条 / 词形 %d 条（建页 %d 条）' % (
        len(words), len(books), len(root_out), len(forms), len(会建页)))
    for book in books:
        print('   %-10s %-12s %5d 词' % (book['slug'], book['name'], book['count']))


if __name__ == '__main__':
    main()
