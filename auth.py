"""Autenticação via Supabase Auth (e-mail + senha) e perfis de acesso.

Variáveis de ambiente (Vercel -> Settings -> Environment Variables):
  SUPABASE_URL       ex.: https://xxxx.supabase.co
  SUPABASE_ANON_KEY  chave "anon/publishable" (pública por design; a segurança vem do RLS)
  OWNER_EMAIL        e-mails com perfil "dono" (separe por vírgula)
  VIEWER_EMAILS      (opcional) e-mails com perfil "leitura": só veem o histórico
"""
import json
import os
import urllib.error
import urllib.request


def _lista(nome):
    return {e.strip().lower() for e in os.environ.get(nome, "").split(",") if e.strip()}


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
DONOS = _lista("OWNER_EMAIL")
LEITORES = _lista("VIEWER_EMAILS")

# perfil -> permissões
PERMISSOES = {
    "dono": ("calcular", "historico", "os"),
    "leitura": ("historico",),
}


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


def _usuario(token):
    """Consulta o Supabase (valida assinatura e expiração do token)."""
    u = _chamar("/auth/v1/user", token=token)
    perfil = perfil_de(u.get("email"))
    if not perfil:
        return None
    return {"email": (u.get("email") or "").lower(), "perfil": perfil}


def token_valido(authorization_header):
    """Retorna dict do usuário se o token for válido; senão None."""
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
    return u


def login(email, senha):
    """Retorna o token da sessão, ou None (a mensagem de erro é sempre genérica)."""
    if not configurado() or perfil_de(email) is None or not senha or len(senha) > 200:
        return None
    try:
        r = _chamar("/auth/v1/token?grant_type=password",
                    {"email": email.strip(), "password": senha})
        return r.get("access_token") or None
    except ErroSupabase:
        return None


def logout(token):
    """Revoga a sessão no Supabase (o token deixa de valer antes de expirar)."""
    try:
        _chamar("/auth/v1/logout", {}, token=token)
    except ErroSupabase:
        pass
