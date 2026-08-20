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

    def _probe(self, qs):
        """Parametrized stream probe for locating a buffering threshold.

        GET /probe?pad=N&interval_ms=M&count=C&linelen=L&ct=TYPE&sse=1

          pad         bytes of filler written as the very first body chunk
          interval_ms delay between the timestamped lines that follow
          count       how many timestamped lines to write
          linelen     each timestamped line is padded to this many bytes
          ct          Content-Type to advertise (default text/plain)
          sse=1       wrap each line in SSE framing ("data: ...\n\n")

        The client stamps the arrival time of every line. Comparing arrival
        times across pad/linelen/interval combinations separates a byte
        threshold (release depends on bytes accumulated) from a time
        threshold (release depends on wall-clock seconds).
        """

        def num(name, default, lo, hi):
            try:
                v = int(qs.get(name, [str(default)])[0])
            except (TypeError, ValueError):
                v = default
            return max(lo, min(hi, v))

        pad = num("pad", 0, 0, 8 * 1024 * 1024)
        interval_ms = num("interval_ms", 1000, 0, 60000)
        count = num("count", 15, 1, 300)
        linelen = num("linelen", 0, 0, 1024 * 1024)

        ct = qs.get("ct", ["text/plain; charset=utf-8"])[0]
        ct = "".join(c for c in ct if 32 <= ord(c) < 127)[:120] or "text/plain"
        sse = qs.get("sse", ["0"])[0] == "1"

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("X-Accel-Buffering", "no")
        # xpad=N reproduces xray's own X-Padding response header, the one
        # visible difference between a decoy stream (which streams fine
        # through the filter) and xray's XHTTP downlink (which does not).
        xpad = num("xpad", 0, 0, 4000)
        if xpad:
            self.send_header("X-Padding", "X" * xpad)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        start = time.time()
        self._cum = 0

        def emit(payload):
            self.wfile.write(b"%x\r\n%s\r\n" % (len(payload), payload))
            self.wfile.flush()
            self._cum += len(payload)

        try:
            if pad:
                emit(b"P" * pad)
            for i in range(count):
                # 'prev' = body bytes already written before this line.
                line = "L %03d srv %.3f prev %d\n" % (
                    i, time.time() - start, self._cum)
                if sse:
                    line = "data: " + line[:-1] + "\n\n"
                b = line.encode()
                if linelen > len(b):
                    b = b[:-1] + b"x" * (linelen - len(b)) + b"\n"
                emit(b)
                if i != count - 1 and interval_ms:
                    time.sleep(interval_ms / 1000.0)
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
        elif u.path == "/probe":
            self._probe(parse_qs(u.query))
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
