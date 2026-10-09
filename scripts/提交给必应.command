#!/bin/bash
# 把 sitemap 里的地址提交给必应站长工具。
# API Key 放在 scripts/.必应APIKey.txt（已 gitignore，不会进仓库）。
cd "$(dirname "$0")/.." || exit 1
python3 - <<'PY'
import json, os, re, urllib.request
KEY_FILE = 'scripts/.必应APIKey.txt'
PUSHED_FILE = 'scripts/.必应已推送.txt'
SITE = 'https://vocab4u.suilang.net'
if not os.path.exists(KEY_FILE):
    print('没找到 %s，先把必应 API Key 存进去再运行。' % KEY_FILE)
    raise SystemExit(1)
key = open(KEY_FILE, encoding='utf-8').read().strip()
urls = re.findall(r'<loc>(.*?)</loc>', open('sitemap.xml', encoding='utf-8').read())
pushed = set()
if os.path.exists(PUSHED_FILE):
    pushed = set(open(PUSHED_FILE, encoding='utf-8').read().split())
todo = [u for u in urls if u not in pushed]
print('sitemap 共 %d 条，本次提交 %d 条' % (len(urls), len(todo)))
if not todo:
    print('没有新地址要提交。')
    raise SystemExit(0)
for i in range(0, len(todo), 500):
    batch = todo[i:i + 500]
    body = json.dumps({'siteUrl': SITE, 'urlList': batch}).encode('utf-8')
    req = urllib.request.Request(
        'https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey=' + key,
        data=body, headers={'Content-Type': 'application/json; charset=utf-8'})
    with urllib.request.urlopen(req, timeout=60) as res:
        print(res.status, res.read().decode('utf-8')[:200])
    pushed.update(batch)
open(PUSHED_FILE, 'w', encoding='utf-8').write('\n'.join(sorted(pushed)))
print('提交完成。')
PY
read -r -p "按回车键关闭…"
