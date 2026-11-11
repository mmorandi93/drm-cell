"""Ordens de serviço (OS) da assistência.

Mesmo padrão do calculo.py: com DATABASE_URL usa Postgres (Supabase),
sem ela usa SQLite local. Toda entrada é validada aqui (nunca confie no navegador).
"""
import os
import sqlite3

from seguranca import numero, texto

DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calculos.db")

STATUS = ["Aberta", "Em análise", "Aguardando aprovação", "Aguardando peça",
          "Em reparo", "Pronto", "Entregue", "Cancelada"]
FORMAS = ("", "Dinheiro", "Pix", "Débito", "Crédito")

# campo de texto -> tamanho máximo
TEXTO = {"cliente_nome": 100, "cliente_tel": 30, "cliente_doc": 30, "marca": 60, "modelo": 60,
         "cor": 40, "imei": 40, "senha_aparelho": 60, "acessorios": 200, "estado_aparelho": 200,
         "defeito": 400, "laudo": 400, "tecnico": 60, "previsao": 10, "observacao": 300}
NUM = ("valor_pecas", "valor_servico", "desconto")
COLS = (["id", "criado_em", "atualizado_em", "status", "pago", "forma_pagto", "garantia_dias"]
        + list(TEXTO) + list(NUM) + ["total"])


def _conectar():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, connect_timeout=5), "%s"
    return sqlite3.connect(SQLITE_PATH, timeout=5), "?"


def _criar_tabelas(cur, ph):
    pg = ph == "%s"
    pk = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMPTZ DEFAULT now()" if pg else "TEXT DEFAULT CURRENT_TIMESTAMP"
    num = "NUMERIC" if pg else "REAL"
    textos = ", ".join(f"{c} TEXT" for c in TEXTO)
    nums = ", ".join(f"{c} {num} DEFAULT 0" for c in NUM)
    cur.execute(f"""CREATE TABLE IF NOT EXISTS ordens (
        id {pk}, criado_em {ts}, atualizado_em {ts},
        status TEXT DEFAULT 'Aberta', pago INTEGER DEFAULT 0, forma_pagto TEXT,
        garantia_dias INTEGER DEFAULT 0, {textos}, {nums}, total {num} DEFAULT 0)""")
    cur.execute(f"""CREATE TABLE IF NOT EXISTS ordens_historico (
        id {pk}, os_id INTEGER, criado_em {ts}, texto TEXT)""")
    if pg:  # Supabase: bloqueia acesso público pela API (anon key)
        cur.execute("ALTER TABLE ordens ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE ordens_historico ENABLE ROW LEVEL SECURITY")


def _executar(fn):
    con, ph = _conectar()
    try:
        with con:
            cur = con.cursor()
            _criar_tabelas(cur, ph)
            return fn(cur, ph)
    finally:
        con.close()


def _validar(dados):
    """Valida e normaliza. Só inclui campos presentes em `dados`. Levanta ValueError."""
    d = {c: texto(dados[c], t) for c, t in TEXTO.items() if c in dados}
    for c in NUM:
        if c in dados:
            d[c] = round(numero(dados[c], c), 2)
    if "garantia_dias" in dados:
        d["garantia_dias"] = int(numero(dados["garantia_dias"], "garantia_dias", 0, 3650))
    if "forma_pagto" in dados:
        if dados["forma_pagto"] not in FORMAS:
            raise ValueError("forma_pagto")
        d["forma_pagto"] = dados["forma_pagto"]
    return d


def _total(d):
    return round(max(d["valor_pecas"] + d["valor_servico"] - d["desconto"], 0), 2)


def _linha(l):
    d = dict(zip(COLS, l))
    for k in ("criado_em", "atualizado_em"):
        d[k] = str(d[k])
    for k in list(NUM) + ["total"]:
        d[k] = float(d[k] or 0)
    d["pago"] = bool(d["pago"])
    d["garantia_dias"] = int(d["garantia_dias"] or 0)
    for k in TEXTO:
        d[k] = d[k] or ""
    d["forma_pagto"] = d["forma_pagto"] or ""
    return d


def listar(limite=2000):
    def f(cur, ph):
        cur.execute("SELECT %s FROM ordens ORDER BY id DESC LIMIT %d" % (", ".join(COLS), int(limite)))
        return [_linha(l) for l in cur.fetchall()]
    return {"ordens": _executar(f), "status": STATUS}


def obter(os_id):
    def f(cur, ph):
        cur.execute(f"SELECT {', '.join(COLS)} FROM ordens WHERE id = {ph}", (os_id,))
        l = cur.fetchone()
        if not l:
            return None
        d = _linha(l)
        cur.execute(f"SELECT criado_em, texto FROM ordens_historico WHERE os_id = {ph} ORDER BY id DESC",
                    (os_id,))
        d["historico"] = [{"criado_em": str(a), "texto": b} for a, b in cur.fetchall()]
        return d
    return _executar(f)


def criar(dados):
    d = _validar(dados)
    if not d.get("cliente_nome"):
        raise ValueError("cliente_nome")
    for c in NUM:
        d.setdefault(c, 0.0)
    d["total"] = _total(d)
    if dados.get("status", "Aberta") not in STATUS:
        raise ValueError("status")
    d["status"] = dados.get("status", "Aberta")
    d["pago"] = 1 if dados.get("pago") is True else 0

    def f(cur, ph):
        cols = list(d)
        sql = f"INSERT INTO ordens ({', '.join(cols)}) VALUES ({', '.join([ph] * len(cols))})"
        if ph == "%s":
            cur.execute(sql + " RETURNING id", [d[c] for c in cols])
            novo = cur.fetchone()[0]
        else:
            cur.execute(sql, [d[c] for c in cols])
            novo = cur.lastrowid
        cur.execute(f"INSERT INTO ordens_historico (os_id, texto) VALUES ({ph},{ph})", (novo, "OS aberta"))
        return {"id": novo}
    return _executar(f)


def atualizar(os_id, dados):
    d = _validar(dados)
    notas = []
    if "status" in dados:
        if dados["status"] not in STATUS:
            raise ValueError("status")
        d["status"] = dados["status"]
        notas.append("Status: " + d["status"])
    if "pago" in dados:
        if not isinstance(dados["pago"], bool):
            raise ValueError("pago")
        d["pago"] = 1 if dados["pago"] else 0
        notas.append("Marcada como paga" if d["pago"] else "Pagamento desmarcado")
    if not d:
        raise ValueError("vazio")

    def f(cur, ph):
        cur.execute(f"SELECT valor_pecas, valor_servico, desconto, status, pago FROM ordens WHERE id = {ph}",
                    (os_id,))
        atual = cur.fetchone()
        if not atual:
            return None
        mix = dict(zip(NUM, map(float, atual[:3])))
        mix.update({k: d[k] for k in NUM if k in d})
        d["total"] = _total(mix)
        if "status" in d and d["status"] == atual[3]:
            notas[:] = [n for n in notas if not n.startswith("Status:")]
        if "pago" in d and bool(d["pago"]) == bool(atual[4]):
            notas[:] = [n for n in notas if "paga" not in n and "Pagamento" not in n]
        agora = "now()" if ph == "%s" else "CURRENT_TIMESTAMP"
        sets = ", ".join(f"{c} = {ph}" for c in d)
        cur.execute(f"UPDATE ordens SET {sets}, atualizado_em = {agora} WHERE id = {ph}",
                    [d[c] for c in d] + [os_id])
        for t in notas or ["OS editada"]:
            cur.execute(f"INSERT INTO ordens_historico (os_id, texto) VALUES ({ph},{ph})", (os_id, t))
        return {"ok": True}
    return _executar(f)
