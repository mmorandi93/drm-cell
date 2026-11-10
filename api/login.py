import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auth  # noqa: E402
import seguranca  # noqa: E402
from seguranca import BaseAPI, log_evento  # noqa: E402


class handler(BaseAPI):
    permitido = "POST"

    def do_POST(self):
        self.executar(self._login)

    def _login(self):
        iph = self.ip()
        if seguranca.bloqueado("login_falha", iph):
            log_evento("login_bloqueado", iph)
            return self.enviar(429, {"erro": "Muitas tentativas. Aguarde alguns minutos."}, {"Retry-After": 900})
        if not auth.configurado():
            log_evento("config_ausente", iph, ",".join(auth.faltando()))
            return self.enviar(503, {"erro": "Serviço indisponível."})
        d = self.ler_json()
        email, senha = d.get("email"), d.get("senha")
        if not isinstance(email, str) or not isinstance(senha, str) or len(email) > 254:
            raise ValueError("credenciais")
        token, proximo, factor_id = auth.login(email, senha)
        if not token:
            log_evento("login_falha", iph)
            return self.enviar(401, {"erro": "Email ou senha incorretos."})
        log_evento("login_senha_ok", iph)
        self.enviar(200, {"token": token, "proximo": proximo, "factor_id": factor_id})
