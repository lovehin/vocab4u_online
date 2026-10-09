#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把可以公开的文件同步到开源镜像仓库 lovehin/vocab4u_online。

和普通「复制整个目录」不一样，这里用的是**白名单式**同步，原因有两个：

1. 私有仓库里混着不适合公开的东西（`AGENTS.md` 是给 AI 看的工作约定、
   `build/.生成状态.json` 是本机构建缓存），得按名单剔掉；
2. 万一以后误把带密钥的文件提交进私有仓库，也能靠下面那道密钥扫描拦住。

清单以 `git ls-files` 为准 —— 没被跟踪的文件本来就不该进任何仓库。
README / LICENSE / .gitignore 从 `docs/公开仓库/` 里取，避免同一个文件维护两份。

用法：`python3 build/开源发布.py`（或双击 scripts/开源发布.command）
"""

import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT = os.path.join(os.path.dirname(BASE), 'vocab4u_online')
REMOTE = 'https://github.com/lovehin/vocab4u_online.git'
PROXY = 'http://127.0.0.1:7890'          # 这台机器上直连 GitHub 会被中断
公开源目录 = 'docs/公开仓库'

# 不同步的私有文件
私有 = {
    'AGENTS.md',                    # 给 AI 看的工作约定，含部署与运维细节
    'build/.生成状态.json',          # 本地构建缓存，用来判断页面正文有没有真的改过
}

# 只有开源仓库才有的文件：私有仓库里的路径 → 开源仓库里的文件名
替换文件 = {
    公开源目录 + '/README.md': 'README.md',
    公开源目录 + '/LICENSE': 'LICENSE',
    公开源目录 + '/gitignore': '.gitignore',
}
截图目录 = 公开源目录 + '/截图'
截图目标 = 'screenshots'

# 疑似密钥：命中就中止发布，宁可误报也不能漏
疑密钥 = re.compile((
    rb'gh[pousr]_[A-Za-z0-9]{20,}'
    rb'|sk-[A-Za-z0-9]{24,}'
    rb'|AKIA[0-9A-Z]{16}'
    rb'|-----BEGIN [A-Z ]*PRIVATE KEY-----'
    rb'|token=[A-Za-z0-9]{16,}'
    rb'|apikey=[A-Za-z0-9]{16,}'
    rb'|api[_-]?key["\']?\s*[:=]\s*["\'][A-Za-z0-9]{20,}'
))
跳过的二进制 = ('.png', '.jpg', '.jpeg', '.webp', '.ico', '.gif', '.woff', '.woff2')


def 列跟踪文件(仓库):
    """列仓库里被跟踪的文件。

    ⚠️ 必须用 -z：文件名里有中文，不加 -z 时 git 会把它们转义成
    "build/\344\270\212\346\270\270..." 这种八进制形式，后面 os.path.isfile 全部落空，
    中文名文件会静默漏掉（真踩过）。
    """
    out = subprocess.run(['git', '-C', 仓库, 'ls-files', '-z'],
                         capture_output=True, text=True).stdout
    return [x for x in out.split('\0') if x]


def 列公开文件():
    文件 = []
    for f in 列跟踪文件(BASE):
        if not f or f in 私有:
            continue
        if f.startswith(公开源目录 + '/'):
            continue                    # 这一整个目录都是「给开源仓库用的素材」，不原样同步
        if os.path.isfile(os.path.join(BASE, f)):
            文件.append(f)
    return 文件


def 扫密钥(路径):
    if 路径.lower().endswith(跳过的二进制):
        return None
    命中 = 疑密钥.search(open(路径, 'rb').read())
    return 命中.group(0)[:60].decode('utf-8', 'replace') if 命中 else None


def 写入(相对, 内容字节):
    目标 = os.path.join(EXPORT, 相对)
    os.makedirs(os.path.dirname(目标), exist_ok=True)
    if os.path.exists(目标) and open(目标, 'rb').read() == 内容字节:
        return False
    open(目标, 'wb').write(内容字节)
    return True


def 复制(相对, 源相对=None):
    内容 = open(os.path.join(BASE, 源相对 or 相对), 'rb').read()
    return 写入(相对, 内容)


def 主流程():
    if not os.path.isdir(os.path.join(BASE, '.git')):
        sys.exit('这里不是 git 仓库，认不出该同步哪些文件。')

    print('私有仓库：%s' % BASE)
    print('开源镜像：%s\n' % EXPORT)

    文件 = 列公开文件()
    print('准备同步 %d 个文件……' % len(文件))

    # 1. 先扫密钥，命中就整体中止
    命中 = []
    for f in 文件:
        h = 扫密钥(os.path.join(BASE, f))
        if h:
            命中.append((f, h))
    if 命中:
        print('\n⚠️ 疑似密钥，已中止，什么都没上传：')
        for f, h in 命中:
            print('   %s  →  %s' % (f, h))
        sys.exit(1)

    # 2. 复制（目录不存在就先建）
    os.makedirs(EXPORT, exist_ok=True)
    改动 = 0
    for f in 文件:
        if 复制(f):
            改动 += 1
    for 源, 目标 in 替换文件.items():
        if os.path.exists(os.path.join(BASE, 源)):
            if 复制(目标, 源):
                改动 += 1
        else:
            print('   ⚠️ 少了 %s，开源仓库不会有 %s' % (源, 目标))
    if os.path.isdir(os.path.join(BASE, 截图目录)):
        for 名 in sorted(os.listdir(os.path.join(BASE, 截图目录))):
            源 = os.path.join(截图目录, 名)
            if 名.lower().endswith('.png'):
                if 复制('%s/%s' % (截图目标, 名), 源):
                    改动 += 1
    print('内容有变化的文件：%d 个' % 改动)

    # 3. 清理：开源仓库里跟踪过、但这次不在清单里的旧文件（同步删除）
    if os.path.isdir(os.path.join(EXPORT, '.git')):
        清单 = set(文件) | set(替换文件.values())
        if os.path.isdir(os.path.join(EXPORT, 截图目标)):
            清单 |= {'%s/%s' % (截图目标, n) for n in os.listdir(os.path.join(EXPORT, 截图目标))}
        旧 = 列跟踪文件(EXPORT)
        删 = 0
        for f in 旧:
            if f not in 清单:
                os.remove(os.path.join(EXPORT, f))
                删 += 1
        if 删:
            print('删掉已下架的 %d 个文件' % 删)

    # 4. 提交并推送
    初始化 = not os.path.isdir(os.path.join(EXPORT, '.git'))
    if 初始化:
        subprocess.run(['git', '-C', EXPORT, 'init', '-b', 'main'], check=True,
                       capture_output=True)
        subprocess.run(['git', '-C', EXPORT, 'remote', 'add', 'origin', REMOTE], check=True,
                       capture_output=True)
        print('已在 %s 建好仓库，远端指向 %s' % (EXPORT, REMOTE))

    subprocess.run(['git', '-C', EXPORT, 'add', '-A'], check=True)
    状态 = subprocess.run(['git', '-C', EXPORT, 'status', '--porcelain'],
                          capture_output=True, text=True).stdout.strip()
    if not 状态:
        print('\n没有变化，不用提交。')
        if not 初始化:
            return
    else:
        件数 = len([x for x in 状态.splitlines()])
        备注 = '同步站点源码与词典数据'
        subprocess.run(['git', '-C', EXPORT, 'commit', '-q', '-m',
                        '%s（%d 个文件）' % (备注, 件数)], check=True)
        print('已提交：%s（%d 个文件）' % (备注, 件数))

    print('\n正在推送（走本机代理 %s）……' % PROXY)
    推 = subprocess.run(['git', '-c', 'http.proxy=' + PROXY, '-C', EXPORT, 'push', '-u', 'origin', 'main'],
                        capture_output=True, text=True)
    sys.stdout.write(推.stdout)
    sys.stderr.write(推.stderr)
    if 推.returncode != 0:
        sys.exit('推送失败（上面有 git 的报错）。')
    print('\n完成：https://github.com/lovehin/vocab4u_online')
    print('（顺手检查一下仓库的 About 简介和 Topics，这两处是给人搜到的入口。）')


if __name__ == '__main__':
    主流程()
