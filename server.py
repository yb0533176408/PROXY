import asyncio
import numpy as np
import uvloop
from aiohttp import web

SQUID_HOST = '127.0.0.1'
SQUID_PORT = 3128
SESSIONS: dict = {}

XOR_KEY    = b'MySecretKey12345'
_CHUNK_MAX = 131072  # 128 KB
_KEY_TILE  = np.frombuffer(
    XOR_KEY * (_CHUNK_MAX // len(XOR_KEY) + 1), dtype=np.uint8
)[:_CHUNK_MAX]


def xor_crypt(data: bytes) -> bytes:
    n = len(data)
    return (np.frombuffer(data, dtype=np.uint8) ^ _KEY_TILE[:n]).tobytes()


async def handle_stream(request: web.Request) -> web.StreamResponse:
    sid = request.headers.get('X-Session-ID')
    if not sid:
        return web.Response(status=400)

    if sid not in SESSIONS:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(SQUID_HOST, SQUID_PORT),
                timeout=5.0,
            )
            SESSIONS[sid] = (reader, writer)
        except Exception:
            return web.Response(status=502)

    reader, _ = SESSIONS[sid]

    resp = web.StreamResponse(
        status=200,
        headers={
            'Content-Type':      'application/octet-stream',
            'Cache-Control':     'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
    await resp.prepare(request)

    try:
        while True:
            data = await reader.read(_CHUNK_MAX)
            if not data:
                break
            await resp.write(xor_crypt(data))
    except Exception:
        pass
    finally:
        SESSIONS.pop(sid, None)

    return resp


async def handle_send(request: web.Request) -> web.Response:
    sid = request.headers.get('X-Session-ID')
    if not sid or sid not in SESSIONS:
        return web.Response(status=400)

    _, writer = SESSIONS[sid]
    try:
        raw = await request.read()
        if raw:
            writer.write(xor_crypt(raw))
            await writer.drain()
        return web.Response(status=200)
    except Exception:
        return web.Response(status=500)


app = web.Application(client_max_size=4 * 1024 * 1024)
app.router.add_get('/api/v1/stream', handle_stream)
app.router.add_post('/api/v1/send',  handle_send)

if __name__ == '__main__':
    uvloop.install()
    web.run_app(app, host='0.0.0.0', port=8080, access_log=None)
