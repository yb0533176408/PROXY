from flask import Flask, request, Response
import socket
import threading

app = Flask(__name__)
SQUID_ADDR = ('127.0.0.1', 3128)

@app.route('/tunnel', methods=['POST'])
def tunnel():
    # פתיחת חיבור מול Squid
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(SQUID_ADDR)
    except Exception as e:
        return f"Squid Connection Error: {e}", 502

    def generate():
        # שליחת המידע שהתקבל מהלקוח אל Squid
        s.sendall(request.get_data())
        
        # קריאת התשובה מ-Squid והזרמתה חזרה ללקוח כ-HTTP Stream
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            yield chunk
        s.close()

    return Response(generate(), content_type='application/octet-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
