from flask import Flask, request, jsonify, Response
import socket
import base64

app = Flask(__name__)
SQUID_ADDR = ('127.0.0.1', 3128)
SESSIONS = {}

@app.route('/api/v1/update', methods=['POST'])
def update_api():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    raw_payload = data.get('payload', '')

    if not session_id:
        return jsonify({'status': 'error', 'message': 'missing session'}), 400

    # התחברות ל-Squid עבור הסשן
    if session_id not in SESSIONS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(SQUID_ADDR)
            s.settimeout(4.0)
            SESSIONS[session_id] = s
        except Exception as e:
            return jsonify({'status': 'error', 'details': str(e)}), 502

    s = SESSIONS[session_id]

    # פענוח הנתונים ושליחה ל-Squid
    if raw_payload:
        try:
            decoded_bytes = base64.b64decode(raw_payload)
            s.sendall(decoded_bytes)
        except Exception:
            pass

    # קריאת התשובה מ-Squid וקידוד חזרה ל-Base64
    response_bytes = b""
    while True:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            response_bytes += chunk
        except socket.timeout:
            break
        except Exception:
            SESSIONS.pop(session_id, None)
            break

    encoded_response = base64.b64encode(response_bytes).decode('utf-8')
    return jsonify({'status': 'ok', 'data': encoded_response})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
