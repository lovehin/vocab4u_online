#!/bin/bash
# ============================================
#  把网站的最新版本传到网上（Cloudflare）
#
#  线上地址： https://vocab4u.suilang.net
#
#  什么时候用：改过网站里的东西之后，双击一次这个文件，
#  等它跑完，线上就是最新的了。
#
#  第一次运行会打开浏览器让你登录 Cloudflare，点一下允许就行。
# ============================================
cd "$(dirname "$0")/.." || exit 1

echo "=========================================="
echo "  随浪背单词 —— 上传最新版"
echo "=========================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "这台电脑还没有 python3，没法生成页面。"
  read -r -p "按回车键关闭…"
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "这台电脑还没有 Node.js，没法读取配置和上传。"
  echo "到 https://nodejs.org/zh-cn 下载安装（一路点下一步），装完再双击这个文件。"
  read -r -p "按回车键关闭…"
  exit 1
fi

if [ ! -f data/dictionary.json ]; then
  echo "正在准备词库数据（第一次会比较慢，要下载几十兆）……"
  python3 build/取数据.py || { echo; echo "准备数据出错，先看看上面的提示。"; read -r -p "按回车键关闭…"; exit 1; }
  echo
fi

echo "正在生成页面（七千多个词条，要跑一会儿）……"
python3 build/gen.py || { echo; echo "生成页面出错，先看看上面的提示。"; read -r -p "按回车键关闭…"; exit 1; }
echo

if ! npx --yes wrangler@latest whoami >/dev/null 2>&1; then
  echo "第一次使用，需要先登录 Cloudflare。马上会打开浏览器，点「允许 / Allow」就好。"
  echo
  npx --yes wrangler@latest login || { echo; echo "登录没成功，再试一次这个文件。"; read -r -p "按回车键关闭…"; exit 1; }
  echo
fi

echo "正在上传……"
echo
npx --yes wrangler@latest deploy
status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "上传完成 ✔"
  echo "线上地址：https://vocab4u.suilang.net"
  echo "（如果还看到旧内容，按 ⌘ + Shift + R 强制刷新一下）"
else
  echo "上传失败（错误码 $status）。把窗口里的红字截图发我，我来处理。"
fi
echo
read -r -p "按回车键关闭…"
