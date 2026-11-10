import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auth  # noqa: E402
import seguranca  # noqa: E402
from seguranca import BaseAPI, log_evento  # noqa: E402

from calculo import listar  # noqa: E402


class handler(BaseAPI):
    permitido = "GET"

    def do_GET(self):
        self.executar(self._historico)

    def _historico(self):
        if not self.exigir("historico"):
            return
        self.enviar(200, listar())
