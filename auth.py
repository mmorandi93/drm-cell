"""Login do proprietário via Supabase Auth.

Variáveis de ambiente (Vercel):
  SUPABASE_URL       ex.: https://xxxx.supabase.co
  SUPABASE_ANON_KEY  chave "anon/publishable" do projeto (é pública por design)
  OWNER_EMAIL        único email autorizado a usar a calculadora
"""
import json
import os
import urllib.error
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "").strip().lower()


def _chamar(caminho, corpo=None, token=None):
    headers = {"apikey": ANON_KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        SUPABASE_URL + caminho,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers=headers,
        method="POST" if corpo is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def configurado():
    return bool(SUPABASE_URL and ANON_KEY and OWNER_EMAIL)


def faltando():
    nomes = {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_ANON_KEY": ANON_KEY, "OWNER_EMAIL": OWNER_EMAIL}
    return [n for n, v in nomes.items() if not v]


def login(email, senha):
    """Retorna (token, erro). token só existe se for o dono."""
    f = faltando()
    if f:
        return None, "Login não configurado no servidor. Faltam variáveis: " + ", ".join(f)
    if email.strip().lower() != OWNER_EMAIL:
        return None, "[DIAGNÓSTICO] Este email não é igual ao OWNER_EMAIL da Vercel."
    try:
        r = _chamar("/auth/v1/token?grant_type=password",
                    {"email": email.strip(), "password": senha})
    except urllib.error.HTTPError as e:
        if e.code == 400:
            try:
                msg = json.loads(e.read()).get("msg") or json.loads("{}")
            except Exception:
                msg = ""
            return None, "[DIAGNÓSTICO] O Supabase recusou: %s" % (msg or "credenciais inválidas")
        return None, "Erro no Supabase (código %s). Confira SUPABASE_URL e SUPABASE_ANON_KEY." % e.code
    except (urllib.error.URLError, ValueError):
        return None, "Não foi possível falar com o Supabase. Confira SUPABASE_URL."
    return r.get("access_token"), None


def token_valido(authorization_header):
    """True só se o token for de uma sessão real do email do dono."""
    if not configurado() or not authorization_header:
        return False
    partes = authorization_header.split(" ", 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return False
    try:
        u = _chamar("/auth/v1/user", token=partes[1])
    except (urllib.error.URLError, ValueError):
        return False
    return (u.get("email") or "").strip().lower() == OWNER_EMAIL
