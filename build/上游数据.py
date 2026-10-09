#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上游数据的下载与读取。

四个来源（全部公开、授权可商用）：
  gptwords.json  Ceelog/DictionaryByGPT4   词条正文          CC BY-SA 4.0
  ecdict.csv     skywind3000/ECDICT        音标/释义/分级/词频  MIT
  en_US.txt      open-dict-data/ipa-dict   音标兜底           MIT
  wordroot.json  skywind3000/ECDICT        词根词缀           MIT

原始文件统一放在 build/_raw/（已 gitignore），缺哪个下哪个。
"""
import csv
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '_raw')

URLS = {
    'gptwords.json': 'https://raw.githubusercontent.com/Ceelog/DictionaryByGPT4/main/gptwords.json',
    'ecdict.csv': 'https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv',
    'wordroot.json': 'https://raw.githubusercontent.com/skywind3000/ECDICT/master/wordroot.txt',
    'ipa_us.txt': 'https://raw.githubusercontent.com/open-dict-data/ipa-dict/master/data/en_US.txt',
    'ipa_uk.txt': 'https://raw.githubusercontent.com/open-dict-data/ipa-dict/master/data/en_UK.txt',
}
PROXY = os.environ.get('SUILANG_PROXY', 'http://127.0.0.1:7890')


def ensure(name):
    """确保 build/_raw/<name> 存在，返回本地路径。"""
    path = os.path.join(RAW, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(RAW, exist_ok=True)
    url = URLS[name]
    sys.stderr.write('正在下载 %s ……\n' % url)
    opener = urllib.request.build_opener()
    if PROXY:
        opener.add_handler(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
    with opener.open(url, timeout=300) as res, open(path, 'wb') as out:
        while True:
            chunk = res.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return path


# ---------------------------------------------------------------- 词条正文
def 读词典正文():
    """返回 [{'word': ..., 'content': ...}]。

    上游是「一行一条 JSON」，但部分正文里带裸换行，不能逐行 json.loads；
    改成按行首 {"word": 的位置切块再解析。
    """
    path = ensure('gptwords.json')
    raw = open(path, encoding='utf-8').read()
    starts = [m.start() for m in re.finditer(r'^\{"word":', raw, re.M)]
    if not starts:
        starts = [m.start() for m in re.finditer(r'\{"word":', raw)]
    out = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(raw)
        seg = raw[start:end].strip()
        if not seg:
            continue
        try:
            rec = json.loads(seg)
        except ValueError:
            continue
        if rec.get('word'):
            out.append({'word': rec['word'].strip(), 'content': rec.get('content') or ''})
    return out


# ---------------------------------------------------------------- ECDICT
_ECDICT = None


def 读ECDICT():
    """返回 {小写单词: {phonetic, translation, tag, frq, bnc, collins, exchange, definition}}。"""
    global _ECDICT
    if _ECDICT is not None:
        return _ECDICT
    path = ensure('ecdict.csv')
    csv.field_size_limit(10 ** 7)
    table = {}
    with open(path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            key = (row.get('word') or '').strip().lower()
            if key and key not in table:
                table[key] = row
    _ECDICT = table
    return table


# ---------------------------------------------------------------- 音标兜底
def 读音标():
    """返回 ({小写词: 美音 IPA}, {小写词: 英音 IPA})。"""
    out = []
    for name in ('ipa_us.txt', 'ipa_uk.txt'):
        path = ensure(name)
        table = {}
        for line in open(path, encoding='utf-8'):
            if '\t' not in line:
                continue
            word, ipa = line.rstrip('\n').split('\t', 1)
            word = word.strip().lower()
            if word and word not in table:
                table[word] = ipa.strip()
        out.append(table)
    return out[0], out[1]


# ---------------------------------------------------------------- 词根词缀
def 读词根():
    """返回 {词根: {meaning, class, origin, example:[...]}}。"""
    path = ensure('wordroot.json')
    data = json.load(open(path, encoding='utf-8'))
    out = {}
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        examples = val.get('example') or []
        if isinstance(examples, str):
            examples = [examples]
        out[key] = {
            'key': key,
            'meaning': (val.get('meaning') or '').strip(),
            'class': (val.get('class') or '').strip(),
            'origin': (val.get('origin') or '').strip(),
            'example': [str(x).strip() for x in examples if str(x).strip()],
        }
    return out
