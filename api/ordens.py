import os
import sys
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auth  # noqa: E402,F401
import seguranca  # noqa: E402,F401
from seguranca import BaseAPI  # noqa: E402

import ordens  # noqa: E402


class handler(BaseAPI):
    permitido = "GET, POST, PUT"

    def _id(self):
        v = (parse_qs(urlsplit(self.path).query).get("id") or [None])[0]
        if v is None:
            return None
        if not v.isdigit() or len(v) > 9:
            raise ValueError("id")
        return int(v)

    def do_GET(self):
        self.executar(self._get)

    def do_POST(self):
        self.executar(self._post)

    def do_PUT(self):
        self.executar(self._put)

    def _get(self):
        if not self.exigir("os"):
            return
        os_id = self._id()
        if os_id is None:
            return self.enviar(200, ordens.listar())
        d = ordens.obter(os_id)
        if d:
            self.enviar(200, d)
        else:
            self.enviar(404, {"erro": "OS não encontrada."})

    def _post(self):
        if not self.exigir("os"):
            return
        self.enviar(200, ordens.criar(self.ler_json()))

    def _put(self):
        if not self.exigir("os"):
            return
        os_id = self._id()
        if os_id is None:
            raise ValueError("id")
        r = ordens.atualizar(os_id, self.ler_json())
        if r:
            self.enviar(200, r)
        else:
            self.enviar(404, {"erro": "OS não encontrada."})
