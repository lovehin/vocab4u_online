#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析器的抽样验收：跑 python3 build/test_解析词条.py"""
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 解析词条 as P
import 上游数据 as U

CJK = re.compile(r'[\u4e00-\u9fff]')
ASCII = re.compile(r'[A-Za-z]')


def main():
    random.seed(20261008)
    recs = U.读词典正文()
    print('词条总数：%d' % len(recs))
    sample = random.sample(recs, 400)

    八节齐全 = 0
    有例句 = 0
    例句条目 = 0
    例句分离好 = 0
    例句只有中文 = 0
    例句只有英文 = 0
    坏例子 = []
    无标题 = 0

    for rec in sample:
        secs = P.split_sections(rec['content'])
        if not secs:
            continue
        if secs.get('例句'):
            有例句 += 1
        if all(secs.get(k) for k in ('词义', '例句', '词根', '词缀', '文化', '变形', '记忆', '故事')):
            八节齐全 += 1
        if list(secs.keys()) == ['词义']:
            无标题 += 1
        for item in P.split_examples(secs.get('例句', '')):
            例句条目 += 1
            en, zh = item['en'], item['zh']
            if ASCII.search(en) and CJK.search(zh) and not CJK.search(en):
                例句分离好 += 1
            elif not en:
                例句只有中文 += 1
            elif not zh:
                例句只有英文 += 1
            if len(坏例子) < 8 and CJK.search(en):
                坏例子.append((rec['word'], en[:90]))

    print('八节齐全：%d/%d' % (八节齐全, len(sample)))
    print('有例句节：%d/%d' % (有例句, len(sample)))
    print('完全不带小标题：%d/%d' % (无标题, len(sample)))
    print('例句条目：%d，中英分离成功：%d（%.1f%%）' % (
        例句条目, 例句分离好, 100.0 * 例句分离好 / max(1, 例句条目)))
    print('只有中文：%d，只有英文：%d' % (例句只有中文, 例句只有英文))
    if 坏例子:
        print('英文里混进中文的坏例：')
        for w, t in 坏例子:
            print('   ', w, '|', t)

    ok = True
    if 有例句 < len(sample) * 0.85:
        print('× 例句节覆盖率不足 85%'); ok = False
    if 例句分离好 < 例句条目 * 0.90:
        print('× 例句中英分离率不足 90%'); ok = False
    if 八节齐全 < len(sample) * 0.60:
        print('× 八节齐全率不足 60%'); ok = False
    print('解析器抽样验收：%s' % ('通过' if ok else '未通过'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
