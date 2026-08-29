#!/usr/bin/env python3
"""ESMTP-mimic survival probe server.

SMTP is server-speaks-first: the server greets with '220 ... ESMTP ...'
the instant a client connects. Real SMTP servers proved to survive
NetFree, so this tests whether a connection that merely *presents* a
valid SMTP conversation survives too - regardless of destination.

It speaks enough valid SMTP to look real: 220 greeting, EHLO ->
250 multiline, and 250 OK to NOOP (which the client uses as a
once-a-second heartbeat). The client's deliberate 25-35 s NOOP gap
tests idle teardown while staying valid SMTP the whole time.
"""

import socket
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2525


def log(m):
    print("[smtp %.3f] %s" % (time.time(), m), flush=True)


def handle(conn, addr):
    tag = "conn[%s:%d]" % addr
    log("%s OPEN" % tag)
    start = time.time()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    f = conn.makefile("rb")
    try:
        conn.sendall(b"220 mx.tsoolgee.uk ESMTP Postfix ready\r\n")
        while True:
            line = f.readline()
            if not line:
                log("%s client closed at t=%.2f" % (tag, time.time() - start))
                break
            cmd = line.strip().upper()
            t = time.time() - start
            if cmd.startswith(b"EHLO") or cmd.startswith(b"HELO"):
                conn.sendall(b"250-mx.tsoolgee.uk\r\n250-PIPELINING\r\n250 8BITMIME\r\n")
            elif cmd.startswith(b"NOOP"):
                conn.sendall(b"250 2.0.0 OK t=%.2f\r\n" % t)
            elif cmd.startswith(b"QUIT"):
                conn.sendall(b"221 Bye\r\n")
                break
            else:
                conn.sendall(b"250 OK\r\n")
    except OSError as e:
        log("%s error at t=%.2f: %s  <-- DIED" % (tag, time.time() - start, e))
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
    log("smtp-mimic server on 127.0.0.1:%d" % PORT)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
