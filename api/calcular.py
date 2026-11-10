import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from auth import token_valido  # noqa: E402
from calculo import processar  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not token_valido(self.headers.get("Authorization")):
            status, corpo = 401, {"erro": "Não autorizado"}
        else:
            tam = int(self.headers.get("Content-Length", 0))
            try:
                status, corpo = 200, processar(json.loads(self.rfile.read(tam) or b"{}"))
            except Exception:
                status, corpo = 400, {"erro": "Dados inválidos"}
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)
