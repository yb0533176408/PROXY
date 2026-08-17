import base64
import zlib
import asyncio
from aiohttp import web

SQUID_HOST = '127.0.0.1'
SQUID_PORT = 3128
SESSIONS = {}

async def handle_stream(request):
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return web.json_response({'status': 'error'}, status=400)

    if session_id not in SESSIONS:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(SQUID_HOST, SQUID_PORT), timeout=5.0
            )
            SESSIONS[session_id] = (reader, writer)
        except Exception as e:
            return web.json_response({'status': 'error', 'details': str(e)}, status=502)

    reader, writer = SESSIONS[session_id]

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-cache'}
    )
    await response.prepare(request)

    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            compressed = zlib.compress(data)
            encoded = base64.b64encode(compressed) + b'\n'
            await response.write(encoded)
    except Exception:
        pass
    finally:
        SESSIONS.pop(session_id, None)

    return response

async def handle_send(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({'status': 'error'}, status=400)

    session_id = data.get('session_id')
    raw_payload = data.get('payload', '')

    if session_id in SESSIONS and raw_payload:
        _, writer = SESSIONS[session_id]
        try:
            decompressed = zlib.decompress(base64.b64decode(raw_payload))
            writer.write(decompressed)
            await writer.drain()
        except Exception:
            pass

    return web.json_response({'status': 'ok'})

app = web.Application()
app.router.add_get('/api/v1/stream', handle_stream)
app.router.add_post('/api/v1/send', handle_send)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080)
