import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from auth import token_valido  # noqa: E402
from calculo import listar  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not token_valido(self.headers.get("Authorization")):
            status, corpo = 401, {"erro": "Não autorizado"}
        else:
            try:
                status, corpo = 200, listar()
            except Exception:
                status, corpo = 500, {"erro": "Não foi possível ler o banco."}
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)
