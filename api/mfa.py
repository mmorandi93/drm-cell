import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auth  # noqa: E402
import seguranca  # noqa: E402
from seguranca import BaseAPI, log_evento  # noqa: E402


class handler(BaseAPI):
    permitido = "POST"

    def do_POST(self):
        self.executar(self._mfa)

    def _mfa(self):
        iph = self.ip()
        if seguranca.bloqueado("mfa_falha", iph):
            log_evento("mfa_bloqueado", iph)
            return self.enviar(429, {"erro": "Muitas tentativas. Aguarde alguns minutos."}, {"Retry-After": 900})
        if not self.exigir(mfa=False):       # basta senha correta (aal1) para cadastrar/verificar 2FA
            return
        d = self.ler_json()
        token = self.token_bruto()
        acao = d.get("acao")
        if acao == "cadastrar":
            try:
                r = auth.mfa_cadastrar(token)
            except PermissionError:
                log_evento("mfa_cadastro_negado", iph)
                return self.enviar(403, {"erro": "Acesso negado."})
            log_evento("mfa_cadastro_iniciado", iph)
            return self.enviar(200, r)
        if acao == "verificar":
            novo = auth.mfa_verificar(token, str(d.get("factor_id", "")), str(d.get("codigo", "")))
            if not novo:
                log_evento("mfa_falha", iph)
                return self.enviar(401, {"erro": "Código incorreto."})
            log_evento("login_completo", iph)
            return self.enviar(200, {"token": novo})
        raise ValueError("acao")
