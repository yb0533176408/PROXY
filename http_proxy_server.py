from flask import Flask, request, Response
import socket
import uuid

app = Flask(__name__)
SQUID_ADDR = ('127.0.0.1', 3128)
SESSIONS = {}

@app.route('/tunnel', methods=['POST'])
def tunnel():
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        session_id = str(uuid.uuid4())

    # פתיחת חיבור חדש מול Squid במידה ולא קיים סשן פעיל
    if session_id not in SESSIONS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(SQUID_ADDR)
            s.settimeout(5.0)
            SESSIONS[session_id] = s
        except Exception as e:
            return f"Squid Connection Error: {e}", 502

    s = SESSIONS[session_id]
    
    try:
        data = request.get_data()
        if data:
            s.sendall(data)

        def generate():
            while True:
                try:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    yield chunk
                except socket.timeout:
                    break
                except Exception:
                    break

        resp = Response(generate(), content_type='application/octet-stream')
        resp.headers['X-Session-ID'] = session_id
        return resp

    except Exception as e:
        SESSIONS.pop(session_id, None)
        return f"Error: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
