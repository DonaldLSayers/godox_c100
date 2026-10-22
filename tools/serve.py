#!/usr/bin/env python3
"""Serve site/ locally with caching off, so edits to the page, the editor's scripts and its
JSON show up on a plain reload.

  python3 tools/serve.py [PORT]      (default 8765; http://127.0.0.1:PORT/)
"""
import http.server, os, sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'site')


class NoCache(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kw):
        super().__init__(*args, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
http.server.ThreadingHTTPServer(('127.0.0.1', port), NoCache).serve_forever()
