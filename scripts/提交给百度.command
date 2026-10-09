#!/bin/bash
# 把 sitemap 里的地址推送给百度搜索资源平台。
# token 放在 scripts/.百度推送token.txt（已 gitignore，不会进仓库）。
cd "$(dirname "$0")/.." || exit 1
python3 - <<'PY'
import os, re, sys, urllib.request
BASE = os.path.dirname(os.path.abspath('.'))
TOKEN_FILE = 'scripts/.百度推送token.txt'
PUSHED_FILE = 'scripts/.百度已推送.txt'
SITE = 'https://vocab4u.suilang.net'
if not os.path.exists(TOKEN_FILE):
    print('没找到 %s，先把百度推送 token 存进去再运行。' % TOKEN_FILE)
    raise SystemExit(1)
token = open(TOKEN_FILE, encoding='utf-8').read().strip()
urls = re.findall(r'<loc>(.*?)</loc>', open('sitemap.xml', encoding='utf-8').read())
pushed = set()
if os.path.exists(PUSHED_FILE):
    pushed = set(open(PUSHED_FILE, encoding='utf-8').read().split())
todo = [u for u in urls if u not in pushed]
print('sitemap 共 %d 条，本次推送 %d 条' % (len(urls), len(todo)))
if not todo:
    print('没有新地址要推。')
    raise SystemExit(0)
ok = 0
for i in range(0, len(todo), 2000):
    batch = todo[i:i + 2000]
    req = urllib.request.Request(
        'http://data.zz.baidu.com/urls?site=%s&token=%s' % (SITE, token),
        data='\n'.join(batch).encode('utf-8'),
        headers={'Content-Type': 'text/plain'})
    with urllib.request.urlopen(req, timeout=60) as res:
        print(res.read().decode('utf-8'))
    ok += len(batch)
    pushed.update(batch)
open(PUSHED_FILE, 'w', encoding='utf-8').write('\n'.join(sorted(pushed)))
print('推送完成，共 %d 条。' % ok)
PY
read -r -p "按回车键关闭…"
