"""Lógica de cálculo e banco de dados.

- Com DATABASE_URL definida (Vercel/Neon): usa Postgres.
- Sem DATABASE_URL (rodando local): usa SQLite em calculos.db.
Cada cálculo feito é registrado na tabela "calculos".
"""
import os
import sqlite3

TAXA_CARTAO = 13.92  # % fixa da máquina de cartão de crédito
DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calculos.db")


def calcular(custo, motoboy, mao_de_obra):
    base = custo + motoboy + mao_de_obra
    preco = base / (1 - TAXA_CARTAO / 100)
    taxa_valor = preco * TAXA_CARTAO / 100
    return {
        "custo": round(custo, 2),
        "motoboy": round(motoboy, 2),
        "mao_de_obra": round(mao_de_obra, 2),
        "base": round(base, 2),
        "taxa_cartao_pct": TAXA_CARTAO,
        "taxa_cartao_valor": round(taxa_valor, 2),
        "preco_final": round(preco, 2),
    }


def salvar(modelo, qualidade, r):
    """Cria o banco/tabela se não existir e grava o cálculo."""
    valores = (modelo, qualidade, r["custo"], r["motoboy"], r["mao_de_obra"],
               r["taxa_cartao_valor"], r["preco_final"])
    if DATABASE_URL:
        import psycopg2
        con = psycopg2.connect(DATABASE_URL)
        try:
            with con, con.cursor() as cur:
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS calculos (
                        id SERIAL PRIMARY KEY,
                        criado_em TIMESTAMPTZ DEFAULT now(),
                        modelo TEXT, qualidade TEXT,
                        custo NUMERIC, motoboy NUMERIC, mao_de_obra NUMERIC,
                        taxa_cartao_valor NUMERIC, preco_final NUMERIC)"""
                )
                # Supabase: impede acesso público à tabela pela API (anon key).
                cur.execute("ALTER TABLE calculos ENABLE ROW LEVEL SECURITY")
                cur.execute(
                    """INSERT INTO calculos (modelo, qualidade, custo, motoboy,
                       mao_de_obra, taxa_cartao_valor, preco_final)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""", valores)
        finally:
            con.close()
    else:
        con = sqlite3.connect(SQLITE_PATH)
        try:
            with con:
                con.execute(
                    """CREATE TABLE IF NOT EXISTS calculos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                        modelo TEXT, qualidade TEXT,
                        custo REAL, motoboy REAL, mao_de_obra REAL,
                        taxa_cartao_valor REAL, preco_final REAL)""")
                con.execute(
                    """INSERT INTO calculos (modelo, qualidade, custo, motoboy,
                       mao_de_obra, taxa_cartao_valor, preco_final)
                       VALUES (?,?,?,?,?,?,?)""", valores)
        finally:
            con.close()


def listar(limite=5000):
    """Retorna os cálculos registrados (mais recentes primeiro)."""
    cols = ("id", "criado_em", "modelo", "qualidade", "custo", "motoboy",
            "mao_de_obra", "taxa_cartao_valor", "preco_final")
    sql = "SELECT %s FROM calculos ORDER BY id DESC LIMIT %d" % (", ".join(cols), int(limite))
    if DATABASE_URL:
        import psycopg2
        con = psycopg2.connect(DATABASE_URL)
        try:
            with con, con.cursor() as cur:
                cur.execute(sql)
                linhas = cur.fetchall()
        finally:
            con.close()
    else:
        if not os.path.exists(SQLITE_PATH):
            return []
        con = sqlite3.connect(SQLITE_PATH)
        try:
            linhas = con.execute(sql).fetchall()
        finally:
            con.close()
    saida = []
    for l in linhas:
        d = dict(zip(cols, l))
        d["criado_em"] = str(d["criado_em"])
        for k in ("custo", "motoboy", "mao_de_obra", "taxa_cartao_valor", "preco_final"):
            d[k] = float(d[k] or 0)
        saida.append(d)
    return saida


def processar(dados):
    r = calcular(float(dados.get("custo", 0)), float(dados.get("motoboy", 0)),
                 float(dados.get("mao_de_obra", 0)))
    try:
        salvar(str(dados.get("modelo", ""))[:200], str(dados.get("qualidade", ""))[:100], r)
    except Exception as e:  # o cálculo não deve falhar se o banco falhar
        print("Erro ao salvar no banco:", e)
    return r
