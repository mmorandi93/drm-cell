"""Testes de segurança da API (rodam sem internet, com Supabase falso e SQLite temporário).
Uso:  python -m unittest discover -s tests -v
"""
import base64
import hashlib
import http.client
import importlib.util
import itertools
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests"))
import fake_supabase  # noqa: E402

FAKE = fake_supabase.iniciar()
os.environ.update({
    "SUPABASE_URL": "http://127.0.0.1:%d" % FAKE.server_address[1],
    "SUPABASE_ANON_KEY": "anon-teste", "OWNER_EMAIL": "dono@teste.com",
    "VIEWER_EMAILS": "leitor@teste.com", "LOG_SALT": "sal-de-teste",
})
os.environ.pop("DATABASE_URL", None)
BANCO = os.path.join(tempfile.mkdtemp(), "teste.db")

import auth  # noqa: E402
import calculo  # noqa: E402
import seguranca  # noqa: E402
seguranca.SQLITE_PATH = calculo.SQLITE_PATH = BANCO


def carregar(nome):
    spec = importlib.util.spec_from_file_location("api_" + nome, os.path.join(RAIZ, "api", nome + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def servir(modulo):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), modulo.handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


ROTAS = {n: servir(carregar(n)) for n in ("login", "mfa", "logout", "calcular", "historico")}
_ip = itertools.count(1)


def chamar(rota, metodo="POST", corpo=None, token=None, ip=None, bruto=None, extra=None, tipo="application/json"):
    ip = ip or "10.0.0.%d" % next(_ip)
    con = http.client.HTTPConnection("127.0.0.1", ROTAS[rota], timeout=10)
    h = {"x-forwarded-for": ip}
    if tipo:
        h["Content-Type"] = tipo
    if token:
        h["Authorization"] = "Bearer " + token
    h.update(extra or {})
    dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
    con.request(metodo, "/api/" + rota, body=dados, headers=h)
    r = con.getresponse()
    txt = r.read().decode()
    try:
        d = json.loads(txt)
    except ValueError:
        d = txt
    return r.status, d, dict((k.lower(), v) for k, v in r.getheaders())


def login_completo(email="dono@teste.com", senha="SenhaForte#1", ip=None):
    ip = ip or "10.9.9.%d" % next(_ip)
    s, d, _ = chamar("login", corpo={"email": email, "senha": senha}, ip=ip)
    assert s == 200, (s, d)
    t = d["token"]
    if d["proximo"] == "cadastrar":
        fid = chamar("mfa", corpo={"acao": "cadastrar"}, token=t, ip=ip)[1]["factor_id"]
    else:
        fid = d["factor_id"]
    s, d2, _ = chamar("mfa", corpo={"acao": "verificar", "factor_id": fid, "codigo": "123456"}, token=t, ip=ip)
    assert s == 200, (s, d2)
    return d2["token"]


def parcial(ip):
    """Login só com senha (aal1). Retorna (token, factor_id)."""
    _, d, _ = chamar("login", corpo={"email": "dono@teste.com", "senha": "SenhaForte#1"}, ip=ip)
    t = d["token"]
    fid = d["factor_id"] or chamar("mfa", corpo={"acao": "cadastrar"}, token=t, ip=ip)[1]["factor_id"]
    return t, fid


class AutenticacaoEAcesso(unittest.TestCase):
    def test_rotas_privadas_sem_token(self):
        self.assertEqual(chamar("historico", "GET")[0], 401)
        self.assertEqual(chamar("calcular", corpo={"custo": 1})[0], 401)

    def test_token_invalido_ou_forjado(self):
        self.assertEqual(chamar("historico", "GET", token="lixo")[0], 401)
        self.assertEqual(chamar("historico", "GET", token=fake_supabase.jwt("aal2"))[0], 401)

    def test_senha_sem_2fa_nao_acessa_dados(self):
        s, d, _ = chamar("login", corpo={"email": "dono@teste.com", "senha": "SenhaForte#1"})
        self.assertEqual(s, 200)
        self.assertIn(d["proximo"], ("cadastrar", "verificar"))
        self.assertEqual(chamar("historico", "GET", token=d["token"])[0], 401)
        self.assertEqual(chamar("calcular", corpo={"custo": 1}, token=d["token"])[0], 401)

    def test_login_ok_com_2fa_acessa(self):
        t = login_completo()
        s, _, h = chamar("historico", "GET", token=t)
        self.assertEqual(s, 200)
        self.assertEqual(h["cache-control"], "no-store")
        self.assertEqual(h["x-content-type-options"], "nosniff")
        corpo = {"custo": 100, "motoboy": 10, "mao_de_obra": 50, "qualidade": "OLED"}
        self.assertEqual(chamar("calcular", corpo=corpo, token=t)[0], 200)

    def test_codigo_2fa_errado_ou_mal_formado(self):
        ip = "10.1.1.1"
        t, fid = parcial(ip)
        s, _, _ = chamar("mfa", corpo={"acao": "verificar", "factor_id": fid, "codigo": "000000"}, token=t, ip=ip)
        self.assertEqual(s, 401)
        s, _, _ = chamar("mfa", corpo={"acao": "verificar", "factor_id": fid, "codigo": "abc"}, token=t, ip=ip)
        self.assertEqual(s, 400)

    def test_qr_code_entregue_como_svg_limpo(self):
        fake_supabase.estado["fatores"].clear()      # força o fluxo de primeiro cadastro
        _, d, _ = chamar("login", corpo={"email": "dono@teste.com", "senha": "SenhaForte#1"})
        self.assertEqual(d["proximo"], "cadastrar")
        c = chamar("mfa", corpo={"acao": "cadastrar"}, token=d["token"])[1]
        self.assertTrue(c["qr_svg"].startswith("<svg"))
        self.assertIn("#000", c["qr_svg"])

    def test_extracao_de_svg_em_varios_formatos(self):
        import base64 as b
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#000"/></svg>'
        for formato in ("data:image/svg+xml;utf-8," + svg, "data:image/svg+xml;utf8," + svg,
                        "data:image/svg+xml;charset=utf-8," + __import__("urllib.parse").parse.quote(svg),
                        "data:image/svg+xml;base64," + b.b64encode(svg.encode()).decode(), svg):
            self.assertEqual(auth._svg(formato), svg, formato)
        self.assertEqual(auth._svg("data:image/svg+xml,<svg><script>alert(1)</script></svg>"), "")
        self.assertEqual(auth._svg("https://evil.example/qr.svg"), "")

    def test_perfis(self):
        leitor = login_completo("leitor@teste.com", "SenhaLeitor#1")
        self.assertEqual(chamar("historico", "GET", token=leitor)[0], 200)
        self.assertEqual(chamar("calcular", corpo={"custo": 1}, token=leitor)[0], 403)

    def test_logout_revoga_token(self):
        t = login_completo()
        self.assertEqual(chamar("historico", "GET", token=t)[0], 200)
        self.assertEqual(chamar("logout", token=t, corpo={})[0], 200)
        self.assertEqual(chamar("historico", "GET", token=t)[0], 401)


class ForcaBrutaERateLimit(unittest.TestCase):
    def test_login_bloqueia_apos_5_falhas(self):
        ip = "10.2.2.2"
        cods = [chamar("login", corpo={"email": "dono@teste.com", "senha": "errada%d" % i}, ip=ip)[0] for i in range(6)]
        self.assertEqual(cods[:5], [401] * 5)
        self.assertEqual(cods[5], 429)
        s, _, h = chamar("login", corpo={"email": "dono@teste.com", "senha": "SenhaForte#1"}, ip=ip)
        self.assertEqual(s, 429)                      # senha certa também é barrada
        self.assertIn("retry-after", h)
        s, _, _ = chamar("login", corpo={"email": "dono@teste.com", "senha": "SenhaForte#1"}, ip="10.2.2.3")
        self.assertEqual(s, 200)                      # outro IP não é afetado

    def test_mensagem_igual_para_email_errado_e_senha_errada(self):
        a = chamar("login", corpo={"email": "dono@teste.com", "senha": "x"})
        b = chamar("login", corpo={"email": "outro@teste.com", "senha": "x"})
        self.assertEqual((a[0], a[1]), (b[0], b[1]))
        self.assertNotIn("supabase", json.dumps(a[1]).lower())

    def test_mfa_bloqueia_apos_5_falhas(self):
        ip = "10.3.3.3"
        t, fid = parcial(ip)
        r = [chamar("mfa", corpo={"acao": "verificar", "factor_id": fid, "codigo": "11111%d" % i},
                    token=t, ip=ip)[0] for i in range(6)]
        self.assertEqual(r[:5], [401] * 5)
        self.assertEqual(r[5], 429)

    def test_rate_limit_geral_da_api(self):
        t = login_completo()
        ip = "10.4.4.4"
        cods = [chamar("historico", "GET", token=t, ip=ip)[0] for _ in range(63)]
        self.assertEqual(cods[0], 200)
        self.assertIn(429, cods)


class ValidacaoEErros(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = login_completo()

    def calc(self, corpo, **kw):
        return chamar("calcular", corpo=corpo, token=self.t, **kw)

    def test_entradas_invalidas_sao_rejeitadas(self):
        for corpo in ({"custo": -5}, {"custo": "abc"}, {"custo": True}, {"custo": 1e12},
                      {"custo": 1, "qualidade": "Inexistente"}, {"modelo": 123}, {"custo": [1]}):
            s, d, _ = self.calc(corpo)
            self.assertEqual(s, 400, corpo)
            self.assertEqual(d, {"erro": "Dados inválidos."})

    def test_nan_infinito_rejeitados(self):
        for bruto in (b'{"custo": NaN}', b'{"custo": Infinity}', b'{"custo": -Infinity}'):
            self.assertEqual(chamar("calcular", bruto=bruto, token=self.t)[0], 400)

    def test_corpo_malformado_grande_ou_tipo_errado(self):
        self.assertEqual(chamar("calcular", bruto=b"{nao e json", token=self.t)[0], 400)
        self.assertEqual(chamar("calcular", bruto=b"[1,2,3]", token=self.t)[0], 400)
        self.assertEqual(chamar("calcular", bruto=b'{"modelo":"' + b"a" * 10000 + b'"}', token=self.t)[0], 400)
        self.assertEqual(chamar("calcular", corpo={"custo": 1}, token=self.t, tipo="text/plain")[0], 400)

    def test_csrf_origem_externa_bloqueada(self):
        s, _, _ = self.calc({"custo": 1}, extra={"Origin": "https://site-malicioso.com", "Host": "drm-cell.vercel.app"})
        self.assertEqual(s, 403)
        s, _, _ = self.calc({"custo": 1}, extra={"Origin": "https://drm-cell.vercel.app", "Host": "drm-cell.vercel.app"})
        self.assertEqual(s, 200)

    def test_sql_injection_e_xss_viram_texto(self):
        ataque = "x'); DROP TABLE calculos;-- <script>alert(1)</script>"
        self.assertEqual(self.calc({"custo": 10, "modelo": ataque, "qualidade": "OLED"})[0], 200)
        con = sqlite3.connect(BANCO)
        modelos = [r[0] for r in con.execute("SELECT modelo FROM calculos")]   # a tabela continua existindo
        con.close()
        gravado = [m for m in modelos if m.startswith("x')")][0]
        self.assertNotIn("<", gravado)
        self.assertNotIn(">", gravado)

    def test_metodos_nao_permitidos(self):
        s, d, _ = chamar("calcular", "GET", token=self.t)
        self.assertEqual((s, d), (405, {"erro": "Método não permitido."}))
        self.assertEqual(chamar("historico", "DELETE", token=self.t)[0], 405)

    def test_erro_interno_nao_vaza_detalhes(self):
        m = carregar("historico")
        m.listar = lambda: (_ for _ in ()).throw(RuntimeError("postgres://user:SENHA-SECRETA@host/db"))
        ROTAS["historico_erro"] = servir(m)
        s, d, _ = chamar("historico_erro", "GET", token=self.t)
        self.assertEqual(s, 500)
        self.assertNotIn("SECRETA", json.dumps(d))
        self.assertNotIn("Traceback", json.dumps(d))

    def test_configuracao_ausente_nao_expoe_nomes(self):
        antes, auth.ANON_KEY = auth.ANON_KEY, ""
        try:
            s, d, _ = chamar("login", corpo={"email": "dono@teste.com", "senha": "x"})
            self.assertEqual(s, 503)
            self.assertNotIn("SUPABASE", json.dumps(d))
        finally:
            auth.ANON_KEY = antes


class LogsDeSeguranca(unittest.TestCase):
    def test_eventos_registrados_sem_dados_sensiveis(self):
        chamar("login", corpo={"email": "dono@teste.com", "senha": "SENHA-PRIVADA-123"}, ip="10.5.5.5")
        chamar("historico", "GET", token="lixo", ip="10.5.5.5")
        con = sqlite3.connect(BANCO)
        linhas = con.execute("SELECT tipo, ip_hash, detalhe FROM eventos_seguranca").fetchall()
        con.close()
        tipos = {l[0] for l in linhas}
        self.assertIn("login_falha", tipos)
        self.assertIn("acesso_negado", tipos)
        tudo = json.dumps(linhas)
        self.assertNotIn("SENHA-PRIVADA-123", tudo)
        self.assertNotIn("10.5.5.5", tudo)            # IP guardado só como hash
        self.assertNotIn("dono@teste.com", tudo)


class ConfiguracaoEstatica(unittest.TestCase):
    def regras(self):
        cfg = json.load(open(os.path.join(RAIZ, "vercel.json"), encoding="utf-8"))
        return {r["source"]: {h["key"]: h["value"] for h in r["headers"]} for r in cfg["headers"]}

    def test_cabecalhos_http(self):
        regras = self.regras()
        for k in ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options",
                  "Referrer-Policy", "Permissions-Policy"):
            self.assertIn(k, regras["/(.*)"])
        csp = regras["/calculadora/(.*)"]["Content-Security-Policy"]
        self.assertIn("script-src 'self';", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_hash_csp_do_script_inline_do_site(self):
        html = open(os.path.join(RAIZ, "index.html"), encoding="utf-8").read()
        csp = [v["Content-Security-Policy"] for k, v in self.regras().items()
               if k.startswith("/((?!")][0]
        for s in re.findall(r"<script>(.*?)</script>", html, re.S):
            h = "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
            self.assertIn(h, csp)

    def test_frontend_sem_scripts_ou_handlers_inline(self):
        html = open(os.path.join(RAIZ, "calculadora", "index.html"), encoding="utf-8").read()
        self.assertIsNone(re.search(r"<script(?![^>]*src)", html))
        self.assertIsNone(re.search(r"\son\w+\s*=", html))
        self.assertNotIn("<style", html)

    def test_sem_segredos_no_frontend(self):
        for arq in ("calculadora/app.js", "calculadora/index.html", "index.html"):
            txt = open(os.path.join(RAIZ, arq), encoding="utf-8").read()
            self.assertIsNone(re.search(r"eyJ[A-Za-z0-9_-]{20,}|service_role|postgres(ql)?://|SUPABASE_ANON_KEY", txt), arq)

    def test_gitignore_protege_segredos(self):
        gi = open(os.path.join(RAIZ, ".gitignore")).read()
        for item in (".env", "calculos.db", ".vercel", "backups"):
            self.assertIn(item, gi)


if __name__ == "__main__":
    unittest.main()
