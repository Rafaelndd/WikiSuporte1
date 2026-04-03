"""
Serviço de notificações globais do sistema e lembretes operacionais.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy import text

from modules.database import get_connection

from services.notificacao_tipos import TIPOS_VALIDOS, normalizar_tipo_notificacao


def ensure_schema() -> None:
    engine = get_connection()
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS notificacoes_sistema (
            id SERIAL PRIMARY KEY,
            tipo VARCHAR(20) NOT NULL,
            titulo VARCHAR(100),
            mensagem TEXT NOT NULL,
            autor VARCHAR(50),
            data_criacao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            data_expiracao TIMESTAMPTZ,
            ativo BOOLEAN DEFAULT TRUE,
            target_role VARCHAR(20) DEFAULT 'todos'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bloqueio_versoes (
            id SERIAL PRIMARY KEY,
            modulo_nome VARCHAR(100) NOT NULL,
            versao_problematica VARCHAR(50) NOT NULL,
            motivo TEXT,
            data_bloqueio TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            resolvido BOOLEAN DEFAULT FALSE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_notificacoes_ativas ON notificacoes_sistema (ativo, data_expiracao, data_criacao)",
        "CREATE INDEX IF NOT EXISTS idx_notificacoes_tipo ON notificacoes_sistema (tipo, ativo)",
        "CREATE INDEX IF NOT EXISTS idx_bloqueio_versoes_resolvido ON bloqueio_versoes (resolvido, data_bloqueio)",
    ]
    with engine.begin() as conn:
        for s in stmts:
            try:
                conn.execute(text(s))
            except Exception:
                continue


def criar_notificacao(
    tipo: str,
    mensagem: str,
    autor: str,
    titulo: str = "",
    target_role: str = "todos",
    data_expiracao: Optional[datetime] = None,
    dedupe_seconds: int = 120,
) -> tuple[bool, str]:
    ensure_schema()
    t = normalizar_tipo_notificacao(tipo or "")
    if not t:
        return False, "Tipo inválido de notificação."
    if not (mensagem or "").strip():
        return False, "Mensagem é obrigatória."
    titulo_norm = (titulo or "").strip()[:100]
    mensagem_norm = (mensagem or "").strip()
    autor_norm = (autor or "").strip()[:50]
    role_norm = (target_role or "todos").strip()[:20]
    engine = get_connection()
    try:
        with engine.begin() as conn:
            # Evita publicação duplicada em janelas curtas (duplo clique/reload).
            lock_key = f"{t}|{titulo_norm.lower()}|{mensagem_norm.lower()}|{autor_norm.lower()}|{role_norm.lower()}"
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})

            janela = max(5, int(dedupe_seconds or 120))
            dup = conn.execute(
                text(
                    """
                    SELECT id
                    FROM notificacoes_sistema
                    WHERE tipo = :tipo
                      AND COALESCE(TRIM(titulo), '') = :titulo
                      AND TRIM(mensagem) = :mensagem
                      AND COALESCE(TRIM(autor), '') = :autor
                      AND COALESCE(TRIM(target_role), 'todos') = :role
                      AND ativo = TRUE
                      AND data_criacao >= (CURRENT_TIMESTAMP - (:janela * INTERVAL '1 second'))
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {
                    "tipo": t,
                    "titulo": titulo_norm,
                    "mensagem": mensagem_norm,
                    "autor": autor_norm,
                    "role": role_norm,
                    "janela": janela,
                },
            ).fetchone()
            if dup:
                return True, f"Notificação já publicada recentemente (ID {int(dup[0])})."

            conn.execute(
                text(
                    """
                    INSERT INTO notificacoes_sistema
                    (tipo, titulo, mensagem, autor, data_expiracao, ativo, target_role)
                    VALUES (:tipo, :titulo, :mensagem, :autor, :exp, TRUE, :role)
                    """
                ),
                {
                    "tipo": t,
                    "titulo": titulo_norm or None,
                    "mensagem": mensagem_norm,
                    "autor": autor_norm or None,
                    "exp": data_expiracao,
                    "role": role_norm,
                },
            )
        return True, "Notificação publicada."
    except Exception as e:
        return False, str(e)


def desativar_notificacao(id_notificacao: int) -> tuple[bool, str]:
    engine = get_connection()
    try:
        with engine.begin() as conn:
            r = conn.execute(
                text("UPDATE notificacoes_sistema SET ativo = FALSE WHERE id = :id"),
                {"id": int(id_notificacao)},
            )
        if r.rowcount:
            return True, "Notificação desativada."
        return False, "Notificação não encontrada."
    except Exception as e:
        return False, str(e)


def get_active_notifications(role: str = "todos") -> pd.DataFrame:
    ensure_schema()
    engine = get_connection()
    role = (role or "todos").strip().lower()
    if role in ("desenvolvedor", "dev", "coordenador", "coordenação", "coordenacao", "supervisor", "master"):
        role = "admin"
    q = text(
        """
        SELECT id, tipo, titulo, mensagem, autor, data_criacao, data_expiracao, ativo, target_role
        FROM notificacoes_sistema
        WHERE ativo = TRUE
          AND (data_expiracao IS NULL OR data_expiracao >= CURRENT_TIMESTAMP)
          AND (
             :role IN ('admin', 'dev')
             OR target_role = 'todos'
             OR target_role = :role
             OR (:role = 'analista' AND target_role IN ('tecnico', 'Analistas'))
             OR (:role = 'admin' AND target_role IN (
                  'Desenvolvedores', 'Coordenadores', 'Supervisores'
                ))
          )
        ORDER BY
           CASE tipo
             WHEN 'erro_critico' THEN 0
             WHEN 'versao_bloqueada' THEN 1
             WHEN 'aviso' THEN 2
             ELSE 3
           END,
           data_criacao DESC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(q, conn, params={"role": role})


def listar_notificacoes_admin(limite: int = 100) -> pd.DataFrame:
    ensure_schema()
    engine = get_connection()
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                """
                SELECT id, tipo, titulo, mensagem, autor, data_criacao, data_expiracao, ativo, target_role
                FROM notificacoes_sistema
                ORDER BY data_criacao DESC
                LIMIT :lim
                """
            ),
            conn,
            params={"lim": int(limite)},
        )


def registrar_bloqueio_versao(modulo_nome: str, versao: str, motivo: str) -> tuple[bool, str]:
    ensure_schema()
    if not (modulo_nome or "").strip() or not (versao or "").strip():
        return False, "Informe módulo e versão."
    engine = get_connection()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bloqueio_versoes (modulo_nome, versao_problematica, motivo, resolvido)
                    VALUES (:m, :v, :mot, FALSE)
                    """
                ),
                {"m": modulo_nome.strip()[:100], "v": versao.strip()[:50], "mot": (motivo or "").strip() or None},
            )
        return True, "Bloqueio registrado."
    except Exception as e:
        return False, str(e)


def resolver_bloqueio_versao(id_bloqueio: int) -> tuple[bool, str]:
    engine = get_connection()
    try:
        with engine.begin() as conn:
            r = conn.execute(
                text("UPDATE bloqueio_versoes SET resolvido = TRUE WHERE id = :id"),
                {"id": int(id_bloqueio)},
            )
        if r.rowcount:
            return True, "Bloqueio de versão resolvido."
        return False, "Bloqueio não encontrado."
    except Exception as e:
        return False, str(e)


def bloqueios_versao_ativos() -> pd.DataFrame:
    ensure_schema()
    engine = get_connection()
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                """
                SELECT id, modulo_nome, versao_problematica, motivo, data_bloqueio
                FROM bloqueio_versoes
                WHERE resolvido = FALSE
                ORDER BY data_bloqueio DESC
                """
            ),
            conn,
        )


def ultima_contribuicao_usuario(usuario_id: int) -> Optional[datetime]:
    engine = get_connection()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT MAX(criado_em) AS ultima
                FROM base_conhecimento
                WHERE id_analista_autor = :uid
                  AND origem = 'CONHECIMENTO_SUPORTE'
                  AND status IN ('APROVADO', 'PENDENTE', 'REVISAO_PENDENTE')
                """
            ),
            {"uid": int(usuario_id)},
        ).fetchone()
    return row[0] if row and row[0] else None


def dias_sem_contribuicao(usuario_id: int) -> Optional[int]:
    ult = ultima_contribuicao_usuario(usuario_id)
    if not ult:
        return None
    now = datetime.now(tz=ult.tzinfo) if getattr(ult, "tzinfo", None) else datetime.now()
    delta = now - ult
    return int(delta.days)


def pendencias_usuario(usuario_id: int) -> Dict[str, int]:
    engine = get_connection()
    with engine.connect() as conn:
        row_ch = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total
                FROM ciclos_homologacao ch
                JOIN chamados c ON c.id_chamado = ch.id_chamado
                JOIN chamados_tecnuv ct ON ct.nr_chamado::text = c.id_chamado
                WHERE ch.status_teste = 'Aguardando'
                  AND ct.id_analista_epsy = :uid
                """
            ),
            {"uid": int(usuario_id)},
        ).fetchone()
        row_bc = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total
                FROM base_conhecimento
                WHERE id_analista_autor = :uid
                  AND origem = 'CONHECIMENTO_SUPORTE'
                  AND status IN ('REJEITADO', 'OBSOLETO')
                """
            ),
            {"uid": int(usuario_id)},
        ).fetchone()
    return {
        "homologacao": int(row_ch[0] or 0) if row_ch else 0,
        "conhecimento_revisar": int(row_bc[0] or 0) if row_bc else 0,
    }


def escala_plantao_hoje(usuario_id: int) -> Optional[Dict[str, Any]]:
    engine = get_connection()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT data_hora_entrada, data_hora_saida
                FROM plantoes_epsy
                WHERE id_analista_epsy = :uid
                  AND data_hora_entrada::date = CURRENT_DATE
                ORDER BY data_hora_entrada
                LIMIT 1
                """
            ),
            {"uid": int(usuario_id)},
        ).fetchone()
    if not row:
        return None
    return {"entrada": row[0], "saida": row[1]}
