import base64
import zlib
import asyncio
from aiohttp import web

SQUID_HOST = '127.0.0.1'
SQUID_PORT = 3128
SESSIONS = {}

async def handle_update(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({'status': 'error', 'message': 'invalid json'}, status=400)

    session_id = data.get('session_id')
    raw_payload = data.get('payload', '')

    if not session_id:
        return web.json_response({'status': 'error', 'message': 'missing session'}, status=400)

    # פתיחת חיבור אסינכרוני מול Squid במידה ולא קיים סשן
    if session_id not in SESSIONS:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(SQUID_HOST, SQUID_PORT), timeout=4.0
            )
            SESSIONS[session_id] = (reader, writer)
        except Exception as e:
            return web.json_response({'status': 'error', 'details': str(e)}, status=502)

    reader, writer = SESSIONS[session_id]

    # פענוח, חילוץ דחיסה ושליחה ל-Squid
    if raw_payload:
        try:
            compressed_data = base64.b64decode(raw_payload)
            decompressed_data = zlib.decompress(compressed_data)
            writer.write(decompressed_data)
            await writer.drain()
        except Exception:
            pass

    # קריאת התשובה מ-Squid, דחיסה וקידוד ל-Base64
    response_bytes = b""
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(65536), timeout=0.05)
            if not chunk:
                break
            response_bytes += chunk
        except asyncio.TimeoutError:
            break
        except Exception:
            SESSIONS.pop(session_id, None)
            break

    encoded_response = ""
    if response_bytes:
        compressed_res = zlib.compress(response_bytes)
        encoded_response = base64.b64encode(compressed_res).decode('utf-8')

    return web.json_response({'status': 'ok', 'data': encoded_response})

app = web.Application()
app.router.add_post('/api/v1/update', handle_update)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080)
