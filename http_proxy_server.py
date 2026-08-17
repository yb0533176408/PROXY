from flask import Flask, request, Response
import socket

app = Flask(__name__)
SQUID_ADDR = ('127.0.0.1', 3128)

@app.route('/tunnel', methods=['POST'])
def tunnel():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(SQUID_ADDR)
        
        # העברת הנתונים שהתקבלו מהלקוח המקומי אל Squid
        s.sendall(request.get_data())
        
        # החזרת התשובה מ-Squid באופן מוזרם (Streaming)
        def generate():
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                yield chunk
            s.close()

        return Response(generate(), content_type='application/octet-stream')
    except Exception as e:
        return f"Proxy Error: {e}", 502

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
