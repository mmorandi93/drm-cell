import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auth  # noqa: E402
import seguranca  # noqa: E402
from seguranca import BaseAPI, log_evento  # noqa: E402


class handler(BaseAPI):
    permitido = "POST"

    def do_POST(self):
        self.executar(self._logout)

    def _logout(self):
        if not self.origem_ok():
            raise PermissionError("origem")
        if self.exigir():
            auth.logout(self.token_bruto())
            log_evento("logout", self.ip())
            self.enviar(200, {"ok": True})
