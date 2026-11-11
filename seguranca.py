"""Utilidades de segurança compartilhadas pela API.

- Respostas JSON com cabeçalhos seguros e erros genéricos.
- Leitura de corpo com limite de tamanho, tipo e validação de origem (anti-CSRF).
- Rate limiting (contagem de falhas por IP, gravada no banco; memória como reserva).
- Log de eventos de segurança (stdout da Vercel + tabela eventos_seguranca).
- Validação de entradas numéricas e de texto.

Variáveis de ambiente opcionais:
  LOG_SALT   texto aleatório usado para anonimizar IPs nos logs (LGPD).
  DATABASE_URL  Postgres (Vercel/Supabase). Sem ela, usa SQLite local.
"""
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calculos.db")
LOG_SALT = os.environ.get("LOG_SALT", "")
MAX_CORPO = 4096              # bytes aceitos em qualquer requisição
RETENCAO_DIAS = 90            # logs de segurança são apagados depois disso (LGPD)

# limites: tipo de falha -> (máximo de falhas, janela em segundos)
LIMITES = {
    "login_falha": (5, 900),
}
LIMITE_REQ = (60, 60)         # 60 requisições por minuto por IP nas rotas privadas

_memoria = {}                 # reserva se o banco estiver fora do ar
_tabela_pronta = False


# ----------------------------------------------------------------- banco
def _conectar():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, connect_timeout=5), "%s"
    return sqlite3.connect(SQLITE_PATH, timeout=5), "?"


def _preparar(con, marcador):
    global _tabela_pronta
    if _tabela_pronta:
        return
    cur = con.cursor()
    if marcador == "%s":
        cur.execute("""CREATE TABLE IF NOT EXISTS eventos_seguranca (
            id SERIAL PRIMARY KEY, criado_em TIMESTAMPTZ DEFAULT now(),
            tipo TEXT NOT NULL, ip_hash TEXT, detalhe TEXT)""")
        cur.execute("ALTER TABLE eventos_seguranca ENABLE ROW LEVEL SECURITY")
        cur.execute("DELETE FROM eventos_seguranca WHERE criado_em < now() - (%s || ' days')::interval",
                    (str(RETENCAO_DIAS),))
    else:
        cur.execute("""CREATE TABLE IF NOT EXISTS eventos_seguranca (
            id INTEGER PRIMARY KEY AUTOINCREMENT, criado_em INTEGER NOT NULL,
            tipo TEXT NOT NULL, ip_hash TEXT, detalhe TEXT)""")
        cur.execute("DELETE FROM eventos_seguranca WHERE criado_em < ?",
                    (int(time.time()) - RETENCAO_DIAS * 86400,))
    con.commit()
    _tabela_pronta = True


def ip_hash(ip):
    """IP anonimizado (hash com sal): permite contar abusos sem guardar o IP."""
    return hashlib.sha256((LOG_SALT + (ip or "?")).encode()).hexdigest()[:16]


def log_evento(tipo, iph, detalhe=""):
    """Registra evento de segurança. Nunca inclua senha, token, e-mail ou IP puro."""
    detalhe = str(detalhe)[:200]
    print(json.dumps({"evento": tipo, "ip": iph, "detalhe": detalhe, "ts": int(time.time())}),
          file=sys.stdout, flush=True)
    _memoria.setdefault(tipo, []).append((iph, time.time()))
    try:
        con, m = _conectar()
        try:
            _preparar(con, m)
            agora = int(time.time())
            if m == "%s":
                con.cursor().execute(
                    "INSERT INTO eventos_seguranca (tipo, ip_hash, detalhe) VALUES (%s,%s,%s)",
                    (tipo, iph, detalhe))
            else:
                con.cursor().execute(
                    "INSERT INTO eventos_seguranca (criado_em, tipo, ip_hash, detalhe) VALUES (?,?,?,?)",
                    (agora, tipo, iph, detalhe))
            con.commit()
        finally:
            con.close()
    except Exception as e:  # o log nunca derruba a requisição
        print(json.dumps({"evento": "log_falhou", "erro": type(e).__name__}), flush=True)


def _contar_banco(tipo, iph, janela):
    con, m = _conectar()
    try:
        _preparar(con, m)
        cur = con.cursor()
        if m == "%s":
            cur.execute("SELECT count(*) FROM eventos_seguranca WHERE tipo=%s AND ip_hash=%s "
                        "AND criado_em > now() - (%s || ' seconds')::interval",
                        (tipo, iph, str(janela)))
        else:
            cur.execute("SELECT count(*) FROM eventos_seguranca WHERE tipo=? AND ip_hash=? AND criado_em > ?",
                        (tipo, iph, int(time.time()) - janela))
        return cur.fetchone()[0]
    finally:
        con.close()


def _contar_memoria(tipo, iph, janela):
    corte = time.time() - janela
    lista = [(i, t) for i, t in _memoria.get(tipo, []) if t > corte]
    _memoria[tipo] = lista
    return sum(1 for i, _ in lista if i == iph)


def bloqueado(tipo, iph):
    """True se este IP excedeu o limite de falhas do tipo informado."""
    maximo, janela = LIMITES[tipo]
    try:
        n = _contar_banco(tipo, iph, janela)
    except Exception:
        n = _contar_memoria(tipo, iph, janela)
    return n >= maximo


def limitar_requisicoes(iph):
    """Limite simples por minuto, em memória (vale por instância serverless)."""
    maximo, janela = LIMITE_REQ
    agora = time.time()
    lista = [t for i, t in _memoria.get("req", []) if i == iph and t > agora - janela]
    outros = [(i, t) for i, t in _memoria.get("req", []) if i != iph and t > agora - janela]
    lista.append(agora)
    _memoria["req"] = outros + [(iph, t) for t in lista]
    return len(lista) > maximo


# ------------------------------------------------------------- validação
def numero(valor, nome, minimo=0.0, maximo=100000.0):
    """Converte para float validando tipo, finitude e faixa. Ausente = 0."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(nome)
    v = float(valor)
    if not math.isfinite(v) or v < minimo or v > maximo:
        raise ValueError(nome)
    return v


_CONTROLE = re.compile(r"[\x00-\x1f\x7f<>]")


def texto(valor, tamanho):
    """Texto simples: remove caracteres de controle e < >, limita o tamanho."""
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise ValueError("texto")
    return _CONTROLE.sub("", valor).strip()[:tamanho]


# --------------------------------------------------------------- handler
class BaseAPI(BaseHTTPRequestHandler):
    """Base das rotas /api: JSON, cabeçalhos seguros, sem vazar detalhes."""

    server_version = "DRM"
    sys_version = ""

    def log_message(self, *args):  # não escreve IP/URL no log padrão
        pass

    # --- utilidades
    def ip(self):
        h = self.headers
        bruto = (h.get("x-vercel-forwarded-for") or h.get("x-real-ip")
                 or (h.get("x-forwarded-for") or "").split(",")[0].strip()
                 or self.client_address[0])
        return ip_hash(bruto.strip())

    def enviar(self, status, corpo, extras=None):
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extras or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(dados)

    def origem_ok(self):
        """Bloqueia requisições de outro site (defesa extra contra CSRF)."""
        origem = self.headers.get("Origin")
        if not origem:
            return True
        return urlsplit(origem).netloc == (self.headers.get("Host") or "")

    def ler_json(self):
        if not self.origem_ok():
            raise PermissionError("origem")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("tipo")
        try:
            tam = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("tamanho")
        if tam < 0 or tam > MAX_CORPO:
            raise ValueError("tamanho")
        corpo = json.loads(self.rfile.read(tam) or b"{}")
        if not isinstance(corpo, dict):
            raise ValueError("formato")
        return corpo

    def executar(self, funcao):
        """Roda a rota com tratamento seguro de erros."""
        try:
            funcao()
        except PermissionError:
            self.enviar(403, {"erro": "Acesso negado."})
        except ValueError:
            self.enviar(400, {"erro": "Dados inválidos."})
        except Exception as e:
            log_evento("erro_interno", self.ip(), type(e).__name__)
            try:
                self.enviar(500, {"erro": "Erro interno. Tente novamente."})
            except Exception:
                pass

    def token_bruto(self):
        h = self.headers.get("Authorization") or ""
        return h.split(" ", 1)[1] if h.lower().startswith("bearer ") else ""

    def exigir(self, permissao=None):
        """Valida o token e a permissão. Retorna o usuário ou None (já respondeu)."""
        import auth
        iph = self.ip()
        if limitar_requisicoes(iph):
            log_evento("rate_limit_api", iph)
            self.enviar(429, {"erro": "Muitas requisições. Aguarde um instante."}, {"Retry-After": 60})
            return None
        if not auth.configurado():
            log_evento("config_ausente", iph, ",".join(auth.faltando()))
            self.enviar(503, {"erro": "Serviço indisponível."})
            return None
        usuario = auth.token_valido(self.headers.get("Authorization"))
        if not usuario:
            log_evento("acesso_negado", iph, "token ausente ou inválido")
            self.enviar(401, {"erro": "Não autorizado"})
            return None
        if permissao and permissao not in auth.PERMISSOES.get(usuario["perfil"], ()):
            log_evento("permissao_negada", iph, permissao)
            self.enviar(403, {"erro": "Sem permissão."})
            return None
        return usuario

    # --- métodos não suportados respondem 405 em JSON
    def _nao_permitido(self):
        self.enviar(405, {"erro": "Método não permitido."}, {"Allow": getattr(self, "permitido", "POST")})

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _nao_permitido

    def send_error(self, code, message=None, explain=None):  # erros do parser HTTP
        self.enviar(code, {"erro": "Requisição inválida."})
