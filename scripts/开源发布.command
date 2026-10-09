#!/bin/bash
# 把可以公开的源码和词典数据同步到开源镜像库 lovehin/vocab4u_online。
# 哪些文件会公开、哪些不会，看 build/开源发布.py 开头的说明。
cd "$(dirname "$0")/.." || exit 1
python3 build/开源发布.py
echo
read -r -p "按回车键关闭…"
