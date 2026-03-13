"""
Notificações: chamados «Pendente representante» — avisar responsável (id_analista_epsy)
e coordenadores; ao entrar em release, avisar de novo; a cada 7 dias se continuar pendente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text

from modules.database import get_connection


def _fechado(status: Optional[str]) -> bool:
    if not status:
        return False
    s = str(status).strip().lower()
    return "encerrado" in s or "cancelado" in s


def _pendente_representante(situacao: Optional[str]) -> bool:
    if not situacao:
        return False
    s = str(situacao).lower()
    return "pendente" in s and "representante" in s


def ids_coordenadores() -> List[int]:
    engine = get_connection()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id FROM usuarios
                WHERE LOWER(COALESCE(perfil, '')) IN ('coordenador', 'coordenação')
                """
            )
        ).fetchall()
    return [int(r[0]) for r in rows if r[0]]


def inserir_notificacao(
    id_usuario: int,
    titulo: str,
    mensagem: str,
    nr_chamado: Optional[int],
    tipo: str,
) -> None:
    engine = get_connection()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO notificacoes_wikisuporte (id_usuario, titulo, mensagem, nr_chamado, tipo)
                VALUES (:u, :t, :m, :n, :tipo)
                """
            ),
            {
                "u": id_usuario,
                "t": titulo[:280],
                "m": (mensagem or "")[:8000],
                "n": nr_chamado,
                "tipo": tipo[:64],
            },
        )


def notificar_release_chamado(nr_chamado: int, versao_release: str) -> None:
    """
    Chamado citado em release e ainda pendente representante → responsável + coordenadores.
    Evita spam: no máximo 1 por (nr, dia) para tipo release_repr.
    """
    engine = get_connection()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id_analista_epsy, usuario_epsy, situacao, status_atual
                FROM chamados_tecnuv WHERE nr_chamado = :n
                """
            ),
            {"n": nr_chamado},
        ).fetchone()
    if not row:
        return
    id_ana, nome_eps, situacao, status = row[0], row[1] or "", row[2] or "", row[3] or ""
    if _fechado(status):
        return
    if not _pendente_representante(situacao):
        return

    hoje = datetime.now(timezone.utc).date()
    coords = ids_coordenadores()
    alvos = set(coords)
    if id_ana:
        alvos.add(int(id_ana))

    titulo = f"Release {versao_release} — Chamado {nr_chamado} (pendente representante)"
    msg = (
        f"O chamado **{nr_chamado}** foi citado na release **{versao_release}** e continua "
        f"com situação **pendente representante**. Valide com o cliente e providencie encerramento quando resolvido."
    )

    with engine.begin() as conn:
        for uid in alvos:
            dup = conn.execute(
                text(
                    """
                    SELECT 1 FROM notificacoes_wikisuporte
                    WHERE id_usuario = :u AND nr_chamado = :n AND tipo = 'release_repr'
                      AND criado_em::date = CURRENT_DATE
                    LIMIT 1
                    """
                ),
                {"u": uid, "n": nr_chamado},
            ).fetchone()
            if dup:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO notificacoes_wikisuporte (id_usuario, titulo, mensagem, nr_chamado, tipo)
                    VALUES (:u, :t, :m, :n, 'release_repr')
                    """
                ),
                {"u": uid, "t": titulo[:280], "m": msg, "n": nr_chamado},
            )
        try:
            conn.execute(
                text(
                    "UPDATE chamados_tecnuv SET ultima_notif_repr_release = CURRENT_TIMESTAMP WHERE nr_chamado = :n"
                ),
                {"n": nr_chamado},
            )
        except Exception:
            pass


def sincronizar_cobranca_7_dias() -> int:
    """
    Para cada chamado pendente representante aberto há 7+ dias desde última cobrança (ou nunca cobrado),
    notifica responsável + coordenadores. Atualiza ultima_notif_repr_7d.
    """
    engine = get_connection()
    limite = datetime.now(timezone.utc) - timedelta(days=7)
    inseridas = 0
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT nr_chamado, id_analista_epsy, data_abertura, ultima_notif_repr_7d, situacao, status_atual
                    FROM chamados_tecnuv
                    WHERE situacao IS NOT NULL
                      AND LOWER(situacao) LIKE '%pendente%'
                      AND LOWER(situacao) LIKE '%representante%'
                      AND LOWER(COALESCE(status_atual, '')) NOT LIKE '%encerrado%'
                      AND LOWER(COALESCE(status_atual, '')) NOT LIKE '%cancelado%'
                    """
                )
            ).fetchall()
    except Exception:
        return 0

    coords = ids_coordenadores()
    for r in rows:
        nr, id_ana, dt_abertura, ult_7d, sit, st = r[0], r[1], r[2], r[3], r[4], r[5]
        if _fechado(st):
            continue
        if ult_7d and ult_7d.replace(tzinfo=timezone.utc) > limite:
            continue
        if dt_abertura:
            da = dt_abertura.replace(tzinfo=timezone.utc) if dt_abertura.tzinfo else dt_abertura.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - da < timedelta(days=7):
                continue
        dias = 0
        if dt_abertura:
            try:
                da = dt_abertura
                if da.tzinfo is None:
                    da = da.replace(tzinfo=timezone.utc)
                dias = (datetime.now(timezone.utc) - da).days
            except Exception:
                dias = 7
        titulo = f"Cobrança 7d — Chamado {nr} pendente representante"
        msg = (
            f"O chamado **{nr}** está **pendente representante** há **{dias}** dia(s). "
            "Providencie retorno ao cliente e encerramento no Helpdesk."
        )
        alvos = set(coords)
        if id_ana:
            alvos.add(int(id_ana))
        with engine.begin() as conn:
            for uid in alvos:
                conn.execute(
                    text(
                        """
                        INSERT INTO notificacoes_wikisuporte (id_usuario, titulo, mensagem, nr_chamado, tipo)
                        VALUES (:u, :t, :m, :n, 'cobranca_repr_7d')
                        """
                    ),
                    {"u": uid, "t": titulo[:280], "m": msg, "n": nr},
                )
                inseridas += 1
            conn.execute(
                text(
                    "UPDATE chamados_tecnuv SET ultima_notif_repr_7d = CURRENT_TIMESTAMP WHERE nr_chamado = :n"
                ),
                {"n": nr},
            )
    return inseridas


def listar_notificacoes_usuario(id_usuario: int, apenas_nao_lidas: bool = True) -> list:
    engine = get_connection()
    sql = """
        SELECT id, titulo, mensagem, nr_chamado, tipo, criado_em
        FROM notificacoes_wikisuporte
        WHERE id_usuario = :u
    """
    if apenas_nao_lidas:
        sql += " AND lida = false"
    sql += " ORDER BY criado_em DESC LIMIT 80"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"u": id_usuario}).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "titulo": r[1],
                "mensagem": r[2] or "",
                "nr_chamado": r[3],
                "tipo": r[4],
                "criado_em": r[5],
            }
        )
    return out


def marcar_lida(notif_id: int, id_usuario: int) -> None:
    engine = get_connection()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE notificacoes_wikisuporte SET lida = true WHERE id = :i AND id_usuario = :u"
            ),
            {"i": notif_id, "u": id_usuario},
        )


def rodar_sincronizacao_completa() -> None:
    """Chamar na Home (1x por carga) + já disparado ao processar release."""
    try:
        sincronizar_cobranca_7_dias()
    except Exception:
        pass
