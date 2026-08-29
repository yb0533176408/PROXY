#!/usr/bin/env python3
"""Raw-TCP survival probe server.

Runs on the GitHub Actions runner, exposed to the public internet through
a raw-TCP tunnel (bore). Its only job is to let a client behind the
filter measure whether a CONTINUOUS, long-lived TCP stream survives -
including an idle gap and traffic in both directions.

Per connection it:
  * sends a heartbeat line once a second for 120 s,
  * goes deliberately SILENT from t=25 s to t=35 s (the idle-teardown
    test - a filter that kills idle tunnels drops the connection here),
  * echoes anything the client sends back, prefixed ECHO:, so the client
    can confirm the uplink direction works mid-stream.

Everything is logged with timestamps so the Actions log is a full record.
"""

import socket
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5432

IDLE_FROM = 25.0
IDLE_TO = 35.0
DURATION = 120.0


def log(msg):
    print("[srv %.3f] %s" % (time.time(), msg), flush=True)


def reader(conn, start, tag):
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                log("%s client closed (recv empty) at t=%.2f" % (tag, time.time() - start))
                return
            log("%s recv %d bytes at t=%.2f: %r" % (tag, len(data), time.time() - start, data[:48]))
            try:
                conn.sendall(b"ECHO:" + data)
            except OSError:
                return
    except OSError as e:
        log("%s reader error: %s" % (tag, e))


def handle(conn, addr):
    tag = "conn[%s:%d]" % addr
    log("%s OPEN" % tag)
    start = time.time()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    threading.Thread(target=reader, args=(conn, start, tag), daemon=True).start()
    i = 0
    try:
        while True:
            t = time.time() - start
            if t >= DURATION:
                log("%s done (duration reached)" % tag)
                break
            if not (IDLE_FROM <= t < IDLE_TO):
                conn.sendall(b"HB %03d t=%.3f\n" % (i, t))
            i += 1
            time.sleep(1.0)
    except OSError as e:
        log("%s send error at t=%.2f: %s  <-- connection died" % (tag, time.time() - start, e))
    finally:
        log("%s CLOSE at t=%.2f" % (tag, time.time() - start))
        try:
            conn.close()
        except OSError:
            pass


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(16)
    log("probe server listening on 127.0.0.1:%d" % PORT)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
