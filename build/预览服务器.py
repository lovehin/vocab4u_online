#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地预览用的简易服务器。

Cloudflare 会把 /learn 对到 learn.html、/list/cet4 对到 list/cet4.html，
Python 自带的 http.server 不会，直接用它预览会满屏 404。
这个脚本按 Cloudflare 的规则找文件，预览效果和线上一致。

用法：python3 build/预览服务器.py [端口]
"""
import http.server
import os
import socketserver
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def translate_path(self, path):
        local = super().translate_path(path)
        if os.path.exists(local) and not os.path.isdir(local):
            return local
        if not os.path.splitext(local)[1]:
            for cand in (local + '.html', os.path.join(local, 'index.html')):
                if os.path.isfile(cand):
                    return cand
        return local

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            page = os.path.join(BASE, '404.html')
            if os.path.isfile(page):
                body = open(page, 'rb').read()
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(body)
                return
        super().send_error(code, message, explain)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8848
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', port), Handler) as httpd:
        print('预览地址：http://127.0.0.1:%d' % port)
        print('（看完按 Control + C 结束）')
        httpd.serve_forever()


if __name__ == '__main__':
    main()
