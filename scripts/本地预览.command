#!/bin/bash
# 在本地起一个预览服务：http://127.0.0.1:8848
# 改完页面双击一次，然后到浏览器里刷新看效果。
cd "$(dirname "$0")/.." || exit 1
echo "正在生成页面……"
python3 build/gen.py || { echo "生成出错，先看上面的提示。"; read -r -p "按回车键关闭…"; exit 1; }
echo
echo "预览地址：http://127.0.0.1:8848"
echo "（看完按 Control + C 结束）"
echo
python3 build/预览服务器.py 8848
