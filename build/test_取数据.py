#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据成品验收：跑 python3 build/test_取数据.py"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
期望词数 = 7954
期望词书 = {'zhongkao': 1588, 'gaokao': 3657, 'cet4': 3725, 'cet6': 5138,
            'kaoyan': 4539, 'chuguo': 309, 'all': 7954}


def main():
    words = json.load(open(os.path.join(BASE, 'data', 'dictionary.json'), encoding='utf-8'))
    books = json.load(open(os.path.join(BASE, 'data', 'books.json'), encoding='utf-8'))['books']
    roots = json.load(open(os.path.join(BASE, 'data', 'roots.json'), encoding='utf-8'))
    fails = []

    def check(ok, msg):
        print(('  √ ' if ok else '  × ') + msg)
        if not ok:
            fails.append(msg)

    print('词条数：%d' % len(words))
    check(len(words) == 期望词数, '词条数应为 %d' % 期望词数)

    slugs = [w['slug'] for w in words]
    check(len(set(slugs)) == len(slugs), 'slug 全局唯一')

    for book in books:
        want = 期望词书.get(book['slug'])
        if want is not None:
            check(book['count'] == want, '%s 应为 %d 词（实际 %d）' % (book['slug'], want, book['count']))

    check(all(len(b['words']) == b['count'] for b in books), '词书词数与 word 列表长度一致')

    with_ipa = sum(1 for w in words if w['us'] or w['uk'])
    check(with_ipa >= len(words) * 0.95, '音标覆盖率 ≥ 95%%（实际 %.1f%%）' % (100.0 * with_ipa / len(words)))

    with_trans = sum(1 for w in words if w['trans'])
    check(with_trans >= len(words) * 0.95, '中文释义覆盖率 ≥ 95%%（实际 %.1f%%）' % (100.0 * with_trans / len(words)))

    with_mean = sum(1 for w in words if (w['sections'].get('词义') or '').strip())
    check(with_mean >= len(words) * 0.99, '词义节覆盖率 ≥ 99%%（实际 %.1f%%）' % (100.0 * with_mean / len(words)))

    with_sent = sum(1 for w in words if w['sentences'])
    check(with_sent >= len(words) * 0.85, '例句覆盖率 ≥ 85%%（实际 %.1f%%）' % (100.0 * with_sent / len(words)))

    tagged = [w for w in words if w['tags']]
    check(len(tagged) >= len(words) * 0.85, '分级标签覆盖率 ≥ 85%%（实际 %.1f%%）' % (100.0 * len(tagged) / len(words)))

    check(len(roots) >= 250, '词根页 ≥ 250 条（实际 %d）' % len(roots))
    check(all(len(r['words']) >= 3 for r in roots), '每条词根至少 3 个本站例词')

    print('\n数据验收：%s' % ('通过' if not fails else '未通过（%d 项）' % len(fails)))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
