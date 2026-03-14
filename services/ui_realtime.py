"""
Camada de UI para notificações globais, lembretes e estilo moderno.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from services.system_notifications import (
    bloqueios_versao_ativos,
    dias_sem_contribuicao,
    escala_plantao_hoje,
    get_active_notifications,
    pendencias_usuario,
)


PONTOS_VR = [
    ("08:00", "Entrada da manhã"),
    ("12:00", "Saída para intervalo"),
    ("13:30", "Retorno do intervalo"),
    ("18:20", "Saída do expediente"),
]


def inject_modern_css() -> None:
    st.markdown(
        """
        <style>
        div[data-baseweb="notification"][kind="success"]{
            background: linear-gradient(135deg,#133c2f,#1e5f4a) !important;
            border: 1px solid #2f8f6f !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="notification"][kind="warning"]{
            background: linear-gradient(135deg,#463211,#6a4b16) !important;
            border: 1px solid #b67b14 !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="notification"][kind="error"]{
            background: linear-gradient(135deg,#4b1717,#7f2020) !important;
            border: 1px solid #d94a4a !important;
            border-radius: 12px !important;
        }
        .ws-card {
            border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.12);
            box-shadow: 0 8px 24px rgba(0,0,0,0.18);
            padding: 12px 14px;
            margin: 6px 0;
            background: rgba(255,255,255,0.03);
        }
        .ws-pulse {
            animation: wsPulse 1.25s infinite;
            border-left: 5px solid #ff5f5f;
        }
        @keyframes wsPulse {
            0% { box-shadow: 0 0 0 0 rgba(255,95,95,0.65);}
            70% { box-shadow: 0 0 0 10px rgba(255,95,95,0);}
            100% { box-shadow: 0 0 0 0 rgba(255,95,95,0);}
        }
        .ws-gold {
            border: 1px solid #c9a227 !important;
            box-shadow: 0 0 20px rgba(201,162,39,0.35) !important;
            background: linear-gradient(135deg,#2f2813,#3b3114);
        }
        .ws-sticky {
            position: sticky;
            top: 0.5rem;
            z-index: 20;
            backdrop-filter: blur(3px);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60)
def _cached_notifs(role: str) -> pd.DataFrame:
    return get_active_notifications(role=role)


@st.cache_data(ttl=60)
def _cached_version_blocks() -> pd.DataFrame:
    return bloqueios_versao_ativos()


def _emit_ponto_eletronico_toasts() -> None:
    now = datetime.now()
    if now.weekday() > 4:  # 0=segunda ... 4=sexta
        return

    hhmm = now.strftime("%H:%M")

    # Pré-calculo dos avisos T-5 e T-1
    agenda: dict[str, str] = {}
    for horario, evento in PONTOS_VR:
        base = datetime.strptime(horario, "%H:%M")
        menos5 = (base - pd.Timedelta(minutes=5)).strftime("%H:%M")
        menos1 = (base - pd.Timedelta(minutes=1)).strftime("%H:%M")
        agenda[menos5] = f"⏰ Faltam 5 minutos para bater o ponto no VR ({evento.lower()} às {horario})."
        agenda[menos1] = f"🚨 Último aviso: falta 1 minuto para bater o ponto no VR ({evento.lower()} às {horario})."

    if hhmm in agenda:
        key = f"toast_ponto_{now.strftime('%Y%m%d_%H%M')}"
        if not st.session_state.get(key):
            st.toast(agenda[hhmm], icon="⏱️")
            st.session_state[key] = True


def _formatar_contagem(segundos: int) -> str:
    if segundos < 0:
        segundos = 0
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    seg = segundos % 60
    return f"{horas:02d}:{minutos:02d}:{seg:02d}"


def _proximo_evento_ponto(now: datetime) -> tuple[datetime, str, str]:
    """
    Retorna (dt_evento, label_evento, horario_str) do próximo ponto no VR.
    Considera segunda a sexta; se fim de semana, joga para segunda 08:00.
    """
    # Se sábado/domingo -> próxima segunda 08:00
    if now.weekday() > 4:
        dias_ate_segunda = 7 - now.weekday()
        base = (now + pd.Timedelta(days=dias_ate_segunda)).replace(hour=8, minute=0, second=0, microsecond=0)
        return base, "Entrada da manhã", "08:00"

    for horario, label in PONTOS_VR:
        h, m = [int(x) for x in horario.split(":")]
        dt_evt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if dt_evt > now:
            return dt_evt, label, horario

    # Já passou da última batida do dia -> próximo dia útil às 08:00
    prox = now + pd.Timedelta(days=1)
    while prox.weekday() > 4:
        prox += pd.Timedelta(days=1)
    prox = prox.replace(hour=8, minute=0, second=0, microsecond=0)
    return prox, "Entrada da manhã", "08:00"


def _render_proximo_ponto_sidebar() -> None:
    now = datetime.now()
    dt_evt, label, horario = _proximo_evento_ponto(now)
    faltam = int((dt_evt - now).total_seconds())
    contagem = _formatar_contagem(faltam)
    classe_extra = " ws-pulse" if faltam <= 300 else ""
    st.sidebar.markdown(
        f"""
        <div class="ws-card{classe_extra}">
            <b>🕒 Próximo ponto no VR</b><br/>
            Evento: <b>{label}</b><br/>
            Horário: <b>{horario}</b><br/>
            Contagem: <b>{contagem}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pendencias_sidebar(usuario_id: Optional[int]) -> None:
    if not usuario_id:
        return
    pend = pendencias_usuario(int(usuario_id))
    total = int(pend.get("homologacao", 0)) + int(pend.get("conhecimento_revisar", 0))
    if total > 0:
        st.sidebar.markdown(
            f"""
            <div class="ws-card ws-pulse">
                <b>⚠️ Pendências detectadas</b><br/>
                Homologação: <b>{pend.get("homologacao",0)}</b><br/>
                Contribuições para revisar: <b>{pend.get("conhecimento_revisar",0)}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_plantao_sidebar(usuario_id: Optional[int]) -> None:
    if not usuario_id:
        return
    esc = escala_plantao_hoje(int(usuario_id))
    if esc:
        ent = esc["entrada"].strftime("%H:%M") if getattr(esc.get("entrada"), "strftime", None) else str(esc.get("entrada"))
        sai = esc["saida"].strftime("%H:%M") if getattr(esc.get("saida"), "strftime", None) else str(esc.get("saida"))
        st.sidebar.markdown(
            f"""
            <div class="ws-card">
                <b>📅 Escala de plantão hoje</b><br/>
                {ent} às {sai}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_inatividade_sidebar(usuario_id: Optional[int]) -> None:
    if not usuario_id:
        return
    dias = dias_sem_contribuicao(int(usuario_id))
    if dias is None or dias > 5:
        st.sidebar.warning("📌 Você está há mais de 5 dias sem contribuição na base. Registre uma nova contribuição.")


def render_global_notifications_listener() -> None:
    """
    Executa no início das páginas para escutar notificações ativas e lembretes.
    """
    inject_modern_css()
    role = str(st.session_state.get("perfil", "analista")).strip().lower()
    usuario_id = st.session_state.get("usuario_id")

    _emit_ponto_eletronico_toasts()
    _render_proximo_ponto_sidebar()
    _render_inatividade_sidebar(usuario_id)
    _render_pendencias_sidebar(usuario_id)
    _render_plantao_sidebar(usuario_id)

    # Alertas críticos de bloqueio de versão no topo
    blocks = _cached_version_blocks()
    if "ws_dismissed_version_blocks" not in st.session_state:
        st.session_state["ws_dismissed_version_blocks"] = []
    if not blocks.empty:
        for _, b in blocks.head(3).iterrows():
            bid = int(b["id"])
            if bid in st.session_state["ws_dismissed_version_blocks"]:
                continue
            st.markdown(
                f"""
                <div class="ws-card ws-pulse ws-sticky" style="margin-top:4px;">
                    <b>🚫 NÃO ATUALIZE O MÓDULO {b['modulo_nome']}</b><br/>
                    Versão bloqueada: <b>{b['versao_problematica']}</b><br/>
                    Motivo: {b.get('motivo') or 'Não informado'}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.error(f"Bloqueio ativo: módulo {b['modulo_nome']} versão {b['versao_problematica']}.")
            if st.button("Entendi este alerta", key=f"ack_ver_block_{bid}"):
                st.session_state["ws_dismissed_version_blocks"].append(bid)
                st.rerun()

    df = _cached_notifs(role=role)
    if df.empty:
        return

    if "ws_seen_notifications" not in st.session_state:
        st.session_state["ws_seen_notifications"] = []

    for _, n in df.iterrows():
        nid = int(n["id"])
        if nid not in st.session_state["ws_seen_notifications"]:
            st.toast(f"📣 {n['titulo'] or n['tipo']}: nova notificação", icon="🔔")
            st.session_state["ws_seen_notifications"].append(nid)

        tipo = str(n["tipo"]).strip().lower()
        titulo = n["titulo"] or tipo.replace("_", " ").title()
        msg = str(n["mensagem"])
        if tipo == "erro_critico":
            st.error(f"{titulo}: {msg}")
        elif tipo == "aviso":
            st.warning(f"{titulo}: {msg}")
        else:
            st.info(f"{titulo}: {msg}")


def show_gamification_upgrade_card(titulo: str, detalhe: str) -> None:
    inject_modern_css()
    st.snow()
    st.markdown(
        f"""
        <div class="ws-card ws-gold">
            <b>🏆 {titulo}</b><br/>{detalhe}
        </div>
        """,
        unsafe_allow_html=True,
    )
