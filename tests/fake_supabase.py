"""Supabase falso (só para testes locais): senha, TOTP, sessões e logout."""
import base64
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USUARIOS = {"dono@teste.com": "SenhaForte#1", "leitor@teste.com": "SenhaLeitor#1"}
CODIGO_CERTO = "123456"
estado = {"tokens": {}, "fatores": {}, "desafios": {}}   # tokens: token -> {email, aal, vivo}


def jwt(aal):
    p = base64.urlsafe_b64encode(json.dumps({"aal": aal, "jti": uuid.uuid4().hex}).encode()).decode().rstrip("=")
    return "h.%s.s" % p


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, status, corpo):
        d = json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _sessao(self):
        t = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        s = estado["tokens"].get(t)
        return (t, s) if s and s["vivo"] else (t, None)

    def do_GET(self):
        t, s = self._sessao()
        if not s:
            return self._json(401, {})
        fat = [{"id": f, "factor_type": "totp", "status": st}
               for f, (e, st) in estado["fatores"].items() if e == s["email"]]
        self._json(200, {"email": s["email"], "factors": fat})

    def do_POST(self):
        c = self._corpo()
        if self.path.startswith("/auth/v1/token"):
            if USUARIOS.get(c.get("email")) != c.get("password"):
                return self._json(400, {"error": "invalid_grant"})
            t = jwt("aal1")
            estado["tokens"][t] = {"email": c["email"], "aal": "aal1", "vivo": True}
            return self._json(200, {"access_token": t})
        t, s = self._sessao()
        if not s:
            return self._json(401, {})
        if self.path == "/auth/v1/factors":
            fid = str(uuid.uuid4())
            estado["fatores"][fid] = (s["email"], "unverified")
            return self._json(200, {"id": fid, "totp": {"qr_code": "data:image/svg+xml;utf-8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"10\" height=\"10\"><rect fill=\"#000\" width=\"5\" height=\"5\"/></svg>", "secret": "ABCDEF"}})
        if self.path.endswith("/challenge"):
            ch = str(uuid.uuid4())
            estado["desafios"][ch] = True
            return self._json(200, {"id": ch})
        if self.path.endswith("/verify"):
            fid = self.path.split("/")[-2]
            if c.get("code") != CODIGO_CERTO or fid not in estado["fatores"]:
                return self._json(400, {"error": "invalid"})
            estado["fatores"][fid] = (s["email"], "verified")
            novo = jwt("aal2")
            estado["tokens"][novo] = {"email": s["email"], "aal": "aal2", "vivo": True}
            return self._json(200, {"access_token": novo})
        if self.path == "/auth/v1/logout":
            s["vivo"] = False
            return self._json(200, {})
        self._json(404, {})


def iniciar():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
