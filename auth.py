"""Autenticação via Supabase Auth, com 2FA (TOTP) e perfis de acesso.

Variáveis de ambiente (Vercel -> Settings -> Environment Variables):
  SUPABASE_URL       ex.: https://xxxx.supabase.co
  SUPABASE_ANON_KEY  chave "anon/publishable" (pública por design; a segurança vem do RLS)
  OWNER_EMAIL        e-mails com perfil "dono" (separe por vírgula)
  VIEWER_EMAILS      (opcional) e-mails com perfil "leitura": só veem o histórico
  REQUIRE_MFA        "1" (padrão) exige 2FA; "0" desliga (só para testes locais)

Fluxo: senha -> token nível aal1 -> código TOTP -> token nível aal2.
Rotas privadas só aceitam aal2 (ou aal1 nas rotas de cadastro/verificação do 2FA).
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request


def _lista(nome):
    return {e.strip().lower() for e in os.environ.get(nome, "").split(",") if e.strip()}


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
DONOS = _lista("OWNER_EMAIL")
LEITORES = _lista("VIEWER_EMAILS")
EXIGIR_MFA = os.environ.get("REQUIRE_MFA", "1") != "0"

# perfil -> permissões
PERMISSOES = {
    "dono": ("calcular", "historico"),
    "leitura": ("historico",),
}

_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_CODIGO = re.compile(r"^\d{6}$")


class ErroSupabase(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


def _chamar(caminho, corpo=None, token=None, metodo=None):
    headers = {"apikey": ANON_KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        SUPABASE_URL + caminho,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers=headers,
        method=metodo or ("POST" if corpo is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            bruto = r.read()
            return json.loads(bruto) if bruto else {}
    except urllib.error.HTTPError as e:
        raise ErroSupabase(e.code)
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ErroSupabase(0)


def configurado():
    return bool(SUPABASE_URL and ANON_KEY and DONOS)


def faltando():
    nomes = {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_ANON_KEY": ANON_KEY, "OWNER_EMAIL": DONOS}
    return [n for n, v in nomes.items() if not v]


def perfil_de(email):
    e = (email or "").strip().lower()
    if e in DONOS:
        return "dono"
    if e in LEITORES:
        return "leitura"
    return None


def _aal(token):
    """Nível de autenticação do JWT. Só é usado DEPOIS de o Supabase validar o token."""
    try:
        carga = token.split(".")[1]
        carga += "=" * (-len(carga) % 4)
        return json.loads(base64.urlsafe_b64decode(carga)).get("aal", "aal1")
    except Exception:
        return "aal1"


def _usuario(token):
    """Consulta o Supabase (valida assinatura e expiração do token)."""
    u = _chamar("/auth/v1/user", token=token)
    perfil = perfil_de(u.get("email"))
    if not perfil:
        return None
    fatores = [f for f in (u.get("factors") or [])
               if f.get("factor_type") == "totp" and f.get("status") == "verified"]
    return {"email": (u.get("email") or "").lower(), "perfil": perfil,
            "aal": _aal(token), "fatores": [f.get("id") for f in fatores]}


def token_valido(authorization_header, exigir_mfa=True):
    """Retorna dict do usuário se o token for válido (e aal2, se exigido); senão None."""
    if not configurado() or not authorization_header:
        return None
    partes = authorization_header.split(" ", 1)
    if len(partes) != 2 or partes[0].lower() != "bearer" or len(partes[1]) > 4096:
        return None
    try:
        u = _usuario(partes[1])
    except ErroSupabase:
        return None
    if not u:
        return None
    if exigir_mfa and EXIGIR_MFA and u["aal"] != "aal2":
        return None
    return u


def login(email, senha):
    """Retorna (token_aal1, proximo, factor_id). token None = falha (mensagem sempre genérica)."""
    if not configurado() or perfil_de(email) is None or not senha or len(senha) > 200:
        return None, None, None
    try:
        r = _chamar("/auth/v1/token?grant_type=password",
                    {"email": email.strip(), "password": senha})
        token = r.get("access_token")
        if not token:
            return None, None, None
        if not EXIGIR_MFA:
            return token, "ok", None
        u = _usuario(token)
        if not u:
            return None, None, None
    except ErroSupabase:
        return None, None, None
    if u["fatores"]:
        return token, "verificar", u["fatores"][0]
    return token, "cadastrar", None


def mfa_cadastrar(token):
    """Inicia o cadastro do app autenticador. Retorna {factor_id, qr, segredo}."""
    u = _usuario(token)
    if not u or u["fatores"]:      # já existe 2FA: não permite cadastrar outro com aal1
        raise PermissionError("mfa")
    import time
    r = _chamar("/auth/v1/factors",
                {"factor_type": "totp", "friendly_name": "DRM-%d" % int(time.time())}, token=token)
    t = r.get("totp") or {}
    return {"factor_id": r.get("id"), "qr": t.get("qr_code"), "segredo": t.get("secret")}


def mfa_verificar(token, factor_id, codigo):
    """Confirma o código TOTP. Retorna novo token aal2 ou None se o código estiver errado."""
    if not _UUID.match(factor_id or "") or not _CODIGO.match(codigo or ""):
        raise ValueError("mfa")
    u = _usuario(token)
    if not u:
        raise PermissionError("mfa")
    try:
        ch = _chamar("/auth/v1/factors/%s/challenge" % factor_id, {}, token=token)
        r = _chamar("/auth/v1/factors/%s/verify" % factor_id,
                    {"challenge_id": ch.get("id"), "code": codigo}, token=token)
    except ErroSupabase:
        return None
    return r.get("access_token")


def logout(token):
    """Revoga a sessão no Supabase (o token deixa de valer antes de expirar)."""
    try:
        _chamar("/auth/v1/logout", {}, token=token)
    except ErroSupabase:
        pass
