"""Backup e teste de restauração do banco da calculadora.

  python backup.py fazer            cria backups/calculos-AAAAMMDD-HHMMSS.(db|dump)
  python backup.py restaurar ARQ DESTINO   restaura um backup SQLite em DESTINO
  python backup.py testar           faz um backup, restaura numa cópia e compara os dados

Com DATABASE_URL (Postgres) usa pg_dump/pg_restore (precisa do cliente PostgreSQL instalado).
Sem DATABASE_URL usa o SQLite local (calculos.db).
Os arquivos de backup contêm dados do negócio: NUNCA os envie para repositório público.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(RAIZ, "backups")
SQLITE_PATH = os.path.join(RAIZ, "calculos.db")
DATABASE_URL = os.environ.get("DATABASE_URL")
TABELAS = ("calculos", "eventos_seguranca")


def _nome(ext):
    os.makedirs(PASTA, exist_ok=True)
    return os.path.join(PASTA, "calculos-%s.%s" % (time.strftime("%Y%m%d-%H%M%S"), ext))


def fazer(origem=None):
    if DATABASE_URL:
        destino = _nome("dump")
        subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", destino, DATABASE_URL], check=True)
    else:
        destino = _nome("db")
        origem = sqlite3.connect(origem or SQLITE_PATH)
        copia = sqlite3.connect(destino)
        with copia:
            origem.backup(copia)          # cópia consistente mesmo com o banco em uso
        origem.close()
        copia.close()
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return destino


def _contagens(caminho):
    con = sqlite3.connect(caminho)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("integridade do backup falhou")
        existentes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: con.execute("SELECT count(*) FROM %s" % t).fetchone()[0] for t in TABELAS if t in existentes}
    finally:
        con.close()


def restaurar(arquivo, destino):
    if arquivo.endswith(".dump"):
        raise SystemExit("Backup Postgres: restaure com  pg_restore --clean --no-owner -d <URL> " + arquivo)
    shutil.copyfile(arquivo, destino)


def testar():
    """Backup -> restauração em arquivo temporário -> compara contagens e integridade."""
    if DATABASE_URL:
        arq = fazer()
        saida = subprocess.run(["pg_restore", "--list", arq], capture_output=True, text=True, check=True).stdout
        ok = "TABLE DATA" in saida or "TABLE" in saida
        print("Backup Postgres legível:", "OK" if ok else "FALHOU", "->", arq)
        return ok
    antes = _contagens(SQLITE_PATH)
    arq = fazer()
    with tempfile.TemporaryDirectory() as tmp:
        alvo = os.path.join(tmp, "restaurado.db")
        restaurar(arq, alvo)
        depois = _contagens(alvo)
    ok = antes == depois
    print("Original :", antes)
    print("Restaurado:", depois)
    print("Teste de restauração:", "OK" if ok else "FALHOU", "->", arq)
    return ok


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fazer":
        print(fazer())
    elif cmd == "restaurar" and len(sys.argv) == 4:
        restaurar(sys.argv[2], sys.argv[3])
        print("Restaurado em", sys.argv[3])
    elif cmd == "testar":
        sys.exit(0 if testar() else 1)
    else:
        print(__doc__)
        sys.exit(2)
