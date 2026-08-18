import threading, time, uuid, requests
BASE="http://localhost:8080"; KEY=b"MySecretKey12345"
def xor(d):
    if not d: return d
    n=len(d); kt=(KEY*(n//16+1))[:n]
    return (int.from_bytes(d,'big')^int.from_bytes(kt,'big')).to_bytes(n,'big')

# also do a plain Squid sanity check (does Squid itself work at all?)
squid_ok="?"
try:
    pr=requests.get("http://ipinfo.io/ip", proxies={"http":"http://127.0.0.1:3128"}, timeout=12)
    squid_ok=f"{pr.status_code}:{pr.text.strip()[:20]}"
except Exception as e:
    squid_ok="ERR:"+type(e).__name__

sid=uuid.uuid4().hex; recv=[]; ready=threading.Event(); st={}
def down():
    try:
        with requests.get(BASE+"/api/v1/stream", headers={"X-Session-ID":sid}, stream=True, timeout=(10,15)) as r:
            st['code']=r.status_code; ready.set()
            for ch in r.iter_content(4096):
                if ch: recv.append(xor(ch))
    except Exception as e:
        st.setdefault('code','ERR:'+type(e).__name__); ready.set()
t=threading.Thread(target=down,daemon=True); t.start(); ready.wait(10); time.sleep(0.5)
try:
    pr=requests.post(BASE+"/api/v1/send", headers={"X-Session-ID":sid,"Content-Type":"application/octet-stream"},
                  data=xor(b"GET http://ipinfo.io/ip HTTP/1.1\r\nHost: ipinfo.io\r\nProxy-Connection: close\r\n\r\n"), timeout=15)
    st['post']=pr.status_code
except Exception as e:
    st['post']='ERR:'+type(e).__name__
t.join(timeout=12)
blob=b"".join(recv)
out=(f"SQUID_DIRECT={squid_ok}\n"
     f"STREAM_STATUS={st.get('code')} POST_STATUS={st.get('post')} BYTES_VIA_TUNNEL={len(blob)}\n"
     f"DECODED={blob[:300].decode('utf-8','replace')!r}\n")
open("selftest.txt","w",encoding="utf-8").write(out)
print(out)
