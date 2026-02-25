#!/usr/bin/env python3
"""Dev server that serves the workspace with correct MIME types.

The 'Random' file is served as text/html since it has no extension.
"""
import http.server
import os

PORT = 8080

class DevHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        base = os.path.basename(path)
        if base == "Random":
            return "text/html; charset=utf-8"
        return super().guess_type(path)

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with http.server.HTTPServer(("", PORT), DevHandler) as httpd:
        print(f"Serving on http://localhost:{PORT}")
        httpd.serve_forever()
