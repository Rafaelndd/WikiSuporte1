"""
Serviço de clientes e telefones para cruzar com Goto/Multi360.
"""
import re
from typing import Optional

import pandas as pd
from modules.database import get_connection
from sqlalchemy import text

try:
    from modules.processador_csv import gerar_hash_lgpd
except ImportError:

    def gerar_hash_lgpd(t):
        return ""


def extrair_numeros(texto) -> str:
    return re.sub(r"\D", "", str(texto)) if texto else ""


def _garantir_indices_clientes(conn) -> None:
    """Cria índices para acelerar autocomplete e vínculo de telefone."""
    conn.execute(text("ALTER TABLE clientes_crm ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE"))
    conn.execute(text("ALTER TABLE clientes_telefones ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE"))
    conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_cliente_telefone "
            "ON clientes_telefones(id_cliente, numero) "
            "WHERE numero IS NOT NULL AND numero <> ''"
        )
    )
    conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_crm_cnpj_not_null "
            "ON clientes_crm(cnpj) "
            "WHERE cnpj IS NOT NULL AND cnpj <> ''"
        )
    )
    # Índices para buscas por CNPJ tratado/não tratado, razão social e telefone.
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_clientes_crm_cnpj_digits "
            "ON clientes_crm ((regexp_replace(COALESCE(cnpj, ''), '[^0-9]', '', 'g')))"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_clientes_crm_razao_social_lower "
            "ON clientes_crm ((LOWER(COALESCE(razao_social, ''))))"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_clientes_telefones_numero_digits "
            "ON clientes_telefones ((regexp_replace(COALESCE(numero, ''), '[^0-9]', '', 'g')))"
        )
    )


def garantir_indices_clientes_busca() -> tuple[bool, str]:
    """Garante estrutura e índices usados na busca/autocomplete de clientes."""
    engine = get_connection()
    try:
        with engine.begin() as conn:
            _garantir_indices_clientes(conn)
        return True, "Índices de clientes verificados com sucesso."
    except Exception as e:
        return False, str(e)


def buscar_clientes_autocomplete(termo: str = "", limite: int = 20) -> pd.DataFrame:
    """
    Busca inteligente por cliente para autocomplete:
    - Razão social (nome do cliente)
    - CNPJ com ou sem máscara
    """
    engine = get_connection()
    termo_limpo = str(termo or "").strip()
    termo_digits = extrair_numeros(termo_limpo)
    q = text(
        """
        SELECT
            c.id_cliente,
            COALESCE(c.razao_social, '') AS razao_social,
            COALESCE(c.cnpj, '') AS cnpj
        FROM clientes_crm c
        WHERE COALESCE(c.ativo, TRUE) = TRUE
          AND (
            :termo = ''
            OR COALESCE(c.razao_social, '') ILIKE :like
            OR COALESCE(c.cnpj, '') ILIKE :like
            OR (
                :digits <> ''
                AND regexp_replace(COALESCE(c.cnpj, ''), '[^0-9]', '', 'g') LIKE :digits_like
            )
          )
        ORDER BY
            CASE
                WHEN :digits <> '' AND regexp_replace(COALESCE(c.cnpj, ''), '[^0-9]', '', 'g') = :digits THEN 0
                WHEN COALESCE(c.razao_social, '') ILIKE :prefix THEN 1
                ELSE 2
            END,
            COALESCE(c.razao_social, '') ASC
        LIMIT :lim
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(
            q,
            conn,
            params={
                "termo": termo_limpo,
                "like": f"%{termo_limpo}%",
                "digits": termo_digits,
                "digits_like": f"%{termo_digits}%",
                "prefix": f"{termo_limpo}%",
                "lim": int(limite),
            },
        )


def listar_clientes_telefones_resumo(limite: int = 1000) -> pd.DataFrame:
    """Lista clientes e quantidade de telefones vinculados (sem exibir id interno)."""
    engine = get_connection()
    q = text(
        """
        SELECT
            COALESCE(c.razao_social, '') AS razao_social,
            COALESCE(c.cnpj, '') AS cnpj,
            COUNT(t.numero) FILTER (
                WHERE t.numero IS NOT NULL AND t.numero <> ''
            ) AS qtd_telefones
        FROM clientes_crm c
        LEFT JOIN clientes_telefones t ON t.id_cliente = c.id_cliente
        WHERE COALESCE(c.ativo, TRUE) = TRUE
        GROUP BY c.id_cliente, c.razao_social, c.cnpj
        ORDER BY COALESCE(c.razao_social, '')
        LIMIT :lim
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(q, conn, params={"lim": int(limite)})


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
            try:
                _garantir_indices_clientes(conn)
            except Exception:
                pass
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
            ja_vinculado = conn.execute(
                text("SELECT id_telefone FROM clientes_telefones WHERE id_cliente = :id AND numero = :num LIMIT 1"),
                {"id": id_cli, "num": numero},
            ).fetchone()
            if ja_vinculado:
                return True, "Telefone já vinculado ao cliente (registro reaproveitado)."
            for sql, params in [
                (text("INSERT INTO clientes_telefones (id_cliente, numero, telefone_hash, origem_dado, ativo) VALUES (:id, :num, :h, 'IMPORT', TRUE)"), {"id": id_cli, "num": numero, "h": tel_hash}),
                (text("INSERT INTO clientes_telefones (id_cliente, numero, origem_dado, ativo) VALUES (:id, :num, 'IMPORT', TRUE)"), {"id": id_cli, "num": numero}),
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
