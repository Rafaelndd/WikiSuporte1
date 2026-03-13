"""
Serviço de clientes e telefones para cruzar com Goto/Multi360.
"""
import re
from typing import Optional

from modules.database import get_connection
from sqlalchemy import text

try:
    from modules.processador_csv import gerar_hash_lgpd
except ImportError:

    def gerar_hash_lgpd(t):
        return ""


def extrair_numeros(texto) -> str:
    return re.sub(r"\D", "", str(texto)) if texto else ""


def obter_mapa_hash_cliente():
    """Retorna dict telefone_hash -> razao_social para cruzamento."""
    engine = get_connection()
    try:
        df = __import__("pandas").read_sql(
            """
            SELECT t.telefone_hash, c.razao_social
            FROM clientes_telefones t
            JOIN clientes_crm c ON t.id_cliente = c.id_cliente
            WHERE t.telefone_hash IS NOT NULL AND t.telefone_hash != ''
            """,
            engine,
        )
        return dict(zip(df["telefone_hash"], df["razao_social"]))
    except Exception:
        try:
            df = __import__("pandas").read_sql(
                """
                SELECT t.numero, c.razao_social
                FROM clientes_telefones t
                JOIN clientes_crm c ON t.id_cliente = c.id_cliente
                WHERE t.numero IS NOT NULL AND t.numero != ''
                """,
                engine,
            )
            # Build hash from numero for matching
            return {gerar_hash_lgpd(str(n)): r for n, r in zip(df["numero"], df["razao_social"])}
        except Exception:
            return {}


def vincular_telefone_cliente(
    razao_social: str,
    numero_raw: str,
    cnpj: Optional[str] = None,
) -> tuple[bool, str]:
    """Vincula um telefone a um cliente. Cria cliente se não existir."""
    if not razao_social or not numero_raw:
        return False, "Preencha Razão Social e Número."
    numero = extrair_numeros(numero_raw)
    if not numero:
        return False, "Número inválido."
    engine = get_connection()
    try:
        tel_hash = gerar_hash_lgpd(numero)
        with engine.begin() as conn:
            id_cli = None
            cnpj_limpo = extrair_numeros(cnpj) if cnpj else None
            if cnpj_limpo:
                try:
                    id_cli = conn.execute(text("SELECT id_cliente FROM clientes_crm WHERE cnpj = :c LIMIT 1"), {"c": cnpj_limpo}).scalar()
                except Exception:
                    pass
            if not id_cli:
                try:
                    id_cli = conn.execute(text("SELECT id_cliente FROM clientes_crm WHERE razao_social ILIKE :n LIMIT 1"), {"n": f"%{razao_social.strip()}%"}).scalar()
                except Exception:
                    pass
            if not id_cli:
                try:
                    id_cli = conn.execute(text("INSERT INTO clientes_crm (razao_social, cnpj) VALUES (:n, :c) RETURNING id_cliente"), {"n": razao_social.strip(), "c": cnpj_limpo}).scalar()
                except Exception:
                    id_cli = conn.execute(text("INSERT INTO clientes_crm (razao_social) VALUES (:n) RETURNING id_cliente"), {"n": razao_social.strip()}).scalar()
            for sql, params in [
                (text("INSERT INTO clientes_telefones (id_cliente, numero, telefone_hash, origem_dado) VALUES (:id, :num, :h, 'IMPORT')"), {"id": id_cli, "num": numero, "h": tel_hash}),
                (text("INSERT INTO clientes_telefones (id_cliente, numero, origem_dado) VALUES (:id, :num, 'IMPORT')"), {"id": id_cli, "num": numero}),
            ]:
                try:
                    conn.execute(sql, params)
                    break
                except Exception:
                    continue
        return True, "Cliente vinculado."
    except Exception as e:
        return False, str(e)
