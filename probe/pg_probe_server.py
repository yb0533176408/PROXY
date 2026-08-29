#!/usr/bin/env python3
"""PostgreSQL-mimic survival probe server.

Unlike the generic probe server, this one speaks a *valid* PostgreSQL v3
server handshake, then keeps the connection alive with well-formed
NoticeResponse messages as heartbeats (with the usual 25-35 s idle gap).

Purpose: find out whether NetFree's auto-open for PostgreSQL validates
the actual protocol (both directions) or just the client's opening bytes.
If a genuine PG handshake makes the stream survive where the fake one
died, protocol-mimicry is a viable transport. If it still dies, NetFree
is doing something deeper (content validation or destination policy).
"""

import socket
import struct
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5432
IDLE_FROM, IDLE_TO, DURATION = 25.0, 35.0, 120.0

SSL_REQUEST = 80877103
PROTO_3 = 196608


def log(m):
    print("[pg %.3f] %s" % (time.time(), m), flush=True)


def msg(typ, payload):
    return typ + struct.pack("!I", len(payload) + 4) + payload


def notice(text):
    # a valid NoticeResponse: fields S/C/M then terminator
    body = (b"SNOTICE\x00" + b"C00000\x00" + b"M" + text.encode() + b"\x00" + b"\x00")
    return msg(b"N", body)


def recv_startup(conn):
    hdr = conn.recv(8)
    if len(hdr) < 8:
        return None
    length, code = struct.unpack("!II", hdr)
    rest = b""
    while len(rest) < length - 8:
        chunk = conn.recv(length - 8 - len(rest))
        if not chunk:
            break
        rest += chunk
    return code


def handle(conn, addr):
    tag = "conn[%s:%d]" % addr
    log("%s OPEN" % tag)
    start = time.time()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    try:
        code = recv_startup(conn)
        if code == SSL_REQUEST:
            conn.sendall(b"N")                       # refuse SSL, stay cleartext
            log("%s SSLRequest -> N" % tag)
            code = recv_startup(conn)
        log("%s startup code=%s" % (tag, code))
        if code != PROTO_3:
            log("%s unexpected startup, closing" % tag)
            conn.close(); return
        # a valid, complete handshake
        conn.sendall(msg(b"R", struct.pack("!I", 0)))                 # AuthenticationOk
        conn.sendall(msg(b"S", b"server_version\x0016.0\x00"))        # ParameterStatus
        conn.sendall(msg(b"S", b"client_encoding\x00UTF8\x00"))
        conn.sendall(msg(b"K", struct.pack("!II", 4242, 987654)))    # BackendKeyData
        conn.sendall(msg(b"Z", b"I"))                                # ReadyForQuery (Idle)
        log("%s handshake complete" % tag)
    except OSError as e:
        log("%s handshake error: %s" % (tag, e)); conn.close(); return

    # drain client input (queries) without blocking the heartbeat
    def drain():
        try:
            while True:
                d = conn.recv(4096)
                if not d:
                    log("%s client closed at t=%.2f" % (tag, time.time() - start)); return
                log("%s recv %d at t=%.2f: %r" % (tag, len(d), time.time() - start, d[:24]))
        except OSError:
            return
    threading.Thread(target=drain, daemon=True).start()

    i = 0
    try:
        while True:
            t = time.time() - start
            if t >= DURATION:
                log("%s done" % tag); break
            if not (IDLE_FROM <= t < IDLE_TO):
                conn.sendall(notice("hb %03d t=%.3f" % (i, t)))
            i += 1
            time.sleep(1.0)
    except OSError as e:
        log("%s send error at t=%.2f: %s  <-- DIED" % (tag, time.time() - start, e))
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
    log("pg-mimic server on 127.0.0.1:%d" % PORT)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
