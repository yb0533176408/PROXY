import asyncio
from aiohttp import web

SQUID_HOST = '127.0.0.1'
SQUID_PORT = 3128
SESSIONS = {}

# מפתח הצפנה קל (XOR Key) - ניתן לשנות למפתח באורך רצוי
XOR_KEY = b'MySecretKey12345'

def xor_crypt(data: bytes) -> bytes:
    key_len = len(XOR_KEY)
    return bytes([b ^ XOR_KEY[i % key_len] for i, b in enumerate(data)])

async def handle_stream(request):
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return web.Response(status=400)

    if session_id not in SESSIONS:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(SQUID_HOST, SQUID_PORT), timeout=5.0
            )
            SESSIONS[session_id] = (reader, writer)
        except Exception:
            return web.Response(status=502)

    reader, _ = SESSIONS[session_id]

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'application/octet-stream',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
    await response.prepare(request)

    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            # הצפנת הנתונים לפני השליחה
            encrypted = xor_crypt(data)
            await response.write(encrypted)
    except Exception:
        pass
    finally:
        SESSIONS.pop(session_id, None)

    return response

async def handle_send(request):
    session_id = request.headers.get('X-Session-ID')
    if not session_id or session_id not in SESSIONS:
        return web.Response(status=400)

    _, writer = SESSIONS[session_id]

    try:
        # קריאת בייטים גולמיים מגוף הבקשה
        encrypted_data = await request.read()
        if encrypted_data:
            # פענוח ה-XOR וכתיבה ל-Squid
            decrypted_data = xor_crypt(encrypted_data)
            writer.write(decrypted_data)
            await writer.drain()
        return web.Response(status=200)
    except Exception:
        return web.Response(status=500)

app = web.Application()
app.router.add_get('/api/v1/stream', handle_stream)
app.router.add_post('/api/v1/send', handle_send)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080)
