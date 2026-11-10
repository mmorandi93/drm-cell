import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from auth import login  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        tam = int(self.headers.get("Content-Length", 0))
        try:
            d = json.loads(self.rfile.read(tam) or b"{}")
            token = login(str(d.get("email", "")), str(d.get("senha", "")))
        except Exception:
            token = None
        if token:
            status, corpo = 200, {"token": token}
        else:
            status, corpo = 401, {"erro": "Email ou senha incorretos."}
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)
