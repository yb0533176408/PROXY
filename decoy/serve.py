#!/usr/bin/env python3
"""Decoy site + transport diagnostics.

Serves the decoy page on '/', plus two endpoints that tell us what the
client's network does to ordinary HTTP:

  /sse    chunked text/event-stream, one line per second for 30s.
          If the client sees the lines trickle in one per second, the
          path does NOT buffer streamed responses -> XHTTP works.
          If all 30 lines arrive at once at the end, something on the
          way buffers the whole body -> streaming transports are dead
          and only request/response polling survives.

  /dl?mb=N  N megabytes of zeros, for a raw throughput check.
"""

import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8081


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nginx"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _index(self):
        path = os.path.join(HERE, "index.html")
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            body = b"<html><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        start = time.time()
        try:
            for i in range(30):
                line = ("data: tick %02d at %.3fs\n\n" % (i, time.time() - start))
                chunk = line.encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
                time.sleep(1)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _dl(self, qs):
        mb = min(int(qs.get("mb", ["8"])[0]), 128)
        total = mb * 1024 * 1024
        block = b"\0" * 65536
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(total))
        self.end_headers()
        try:
            sent = 0
            while sent < total:
                n = min(len(block), total - sent)
                self.wfile.write(block[:n])
                sent += n
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/sse":
            self._sse()
        elif u.path == "/dl":
            self._dl(parse_qs(u.query))
        else:
            self._index()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
