"""
WikiSuporte - Página de Configurações.
Controle de bots, gestão de usuários/ramais, clientes e telefones.
"""
import json
import os
import re
import time
import urllib.request
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import text

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from modules.database import get_connection
from modules.utils import ler_estado_robo, salvar_estado_robo

try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(*args): pass

try:
    from services.bot_control import (
        RASPAGENS,
        MIN_INTERVALO_MINUTOS,
        MAX_RASPAGENS_POR_HORA,
        ler_estado,
        salvar_estado,
        solicitar_raspagem,
        solicitar_parada_bots,
        forcar_estado_parado,
        sincronizar_estado_se_motor_morto,
        pode_executar_raspagem,
    )
    BOT_CONTROL_DISPONIVEL = True
except ImportError:
    BOT_CONTROL_DISPONIVEL = False

st.set_page_config(page_title="WikiSuporte - Configurações", page_icon="⚙️", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

usuario_id = st.session_state.get("usuario_id")
perfil_raw = str(st.session_state.get("perfil", "")).strip().lower()
perfil_usuario = "dev" if perfil_raw in ("dev", "desenvolvedor") else "coordenador" if perfil_raw in ("coordenador", "coordenação") else perfil_raw

if perfil_usuario not in ["dev", "coordenador"]:
    st.error("⛔ Acesso Negado: Esta página é restrita a Coordenação e Desenvolvimento.")
    st.stop()

st.title("⚙️ WikiSuporte - Configurações")
st.markdown("Controle dos bots de varredura, gestão de usuários/ramais e cadastro de clientes com telefones.")

aba_robo, aba_ramais, aba_usuarios, aba_clientes, aba_diagnostico = st.tabs([
    "🤖 Bots de Varredura",
    "📞 Ramais e Analistas",
    "👥 Usuários",
    "🏢 Clientes e Telefones",
    "🛠️ Diagnóstico",
])

# ==========================================
# ABA 1: BOTS DE VARREDURA
# ==========================================
with aba_robo:
    st.subheader("Controle dos Bots de Varredura")
    with st.expander("🤔 Como usar esta área?"):
        st.markdown(
            "**Métricas** mostram se o motor está rodando. **Salvar** grava intervalo e limites de segurança. "
            "**Raspagens individuais** só funcionam com `python motor_extracao.py` (ou `start_motor.bat`) aberto em outro terminal. "
            "Evite disparar muitas raspagens seguidas — respeite o limite por hora."
        )
    estado = ler_estado_robo() if not BOT_CONTROL_DISPONIVEL else ler_estado()
    if BOT_CONTROL_DISPONIVEL:
        if sincronizar_estado_se_motor_morto():
            estado = ler_estado()
            st.toast("Estado corrigido: motor não está rodando — status voltou para Parado.", icon="✅")

    em_andamento = estado.get("em_andamento", False)
    etapa = estado.get("etapa_atual") or "—"
    ultima = estado.get("ultima_execucao", "Nunca")
    if ultima != "Nunca":
        try:
            ultima = datetime.fromisoformat(ultima).strftime("%d/%m/%Y às %H:%M:%S")
        except Exception:
            pass

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", "🟢 Executando" if em_andamento else "⏸️ Parado", delta="Etapa atual" if em_andamento else "Livre")
    c2.metric("Etapa Atual", etapa if em_andamento else "—")
    c3.metric("Última Varredura", ultima)
    c4.metric("Intervalo", f"{estado.get('intervalo', 60)} min")

    st.divider()

    # Configurações e segurança
    with st.expander("⚙️ Configurações e Segurança", expanded=True):
        with st.form("form_bot_config"):
            auto_ativo = st.toggle("Ativar varreduras automáticas", value=estado.get("auto_ativo", False))
            intervalo = st.slider("Intervalo entre varreduras (min)", min_value=MIN_INTERVALO_MINUTOS if BOT_CONTROL_DISPONIVEL else 15, max_value=240, value=estado.get("intervalo", 60), step=15)
            min_intervalo = st.number_input("Mín. intervalo entre raspagens (min) - segurança", min_value=15, max_value=120, value=estado.get("min_intervalo", MIN_INTERVALO_MINUTOS), step=5) if BOT_CONTROL_DISPONIVEL else None
            max_por_hora = st.number_input("Máx. raspagens por hora - proteção servidor", min_value=1, max_value=6, value=estado.get("max_raspagens_hora", MAX_RASPAGENS_POR_HORA)) if BOT_CONTROL_DISPONIVEL else None

            if st.form_submit_button("Salvar"):
                estado["auto_ativo"] = auto_ativo
                estado["intervalo"] = intervalo
                if BOT_CONTROL_DISPONIVEL and min_intervalo is not None:
                    estado["min_intervalo"] = min_intervalo
                if BOT_CONTROL_DISPONIVEL and max_por_hora is not None:
                    estado["max_raspagens_hora"] = max_por_hora
                salvar_estado_robo(estado)
                st.success("Configurações salvas.")
                st.rerun()

    # Aviso crítico: motor precisa estar rodando
    st.warning(
        "**⚠️ Para os botões funcionarem:** o motor precisa estar rodando. "
        "Execute `scripts\\start_motor.bat` ou em um terminal: `python motor_extracao.py`"
    )
    if BOT_CONTROL_DISPONIVEL:
        st.markdown("#### Parar / resetar status na tela")
        st.caption(
            "O status **Executando** vem do arquivo `robo_state.json`. Se você **fechou o terminal** do motor, "
            "esse flag pode ficar preso — use **Forçar Parado** para liberar os botões de raspagem de novo."
        )
        cpar1, cpar2 = st.columns(2)
        with cpar1:
            if st.button("🛑 Forçar Parado (corrigir status preso)", type="primary", key="forcar_parado"):
                solicitar_parada_bots()
                forcar_estado_parado()
                st.success("Estado gravado como **Parado**. Pode voltar a solicitar raspagens.")
                st.rerun()
        with cpar2:
            if st.button("⏸️ Só avisar motor (parada cooperativa)", key="parar_coop"):
                solicitar_parada_bots()
                st.info("Se o motor estiver rodando, ele encerra no próximo passo. O status só muda quando o motor chama finalizar.")
                st.rerun()

    # Botões individuais de raspagem
    st.markdown("#### Raspagens Individuais")
    st.caption("Clique para solicitar. O motor (motor_extracao.py) precisa estar rodando em outro terminal.")
    st.info(
        "**Dashboard Chamados** usa cache (~45s) ao ler `chamados_tecnuv`. O bot **grava no Postgres** ao sincronizar; "
        "se a tela não mudou na hora, abra o Dashboard e clique **🔄 Atualizar** (limpa cache). "
        "Nos logs: `[DB] … gravados (commit)` confirma escrita antes do deep scrape."
    )

    raspagens_ui = RASPAGENS if BOT_CONTROL_DISPONIVEL else {
        "chamados": {"label": "Chamados Tecnuv", "icon": "📋"},
        "tickets": {"label": "Tickets EPSY", "icon": "🎫"},
        "releases": {"label": "Releases", "icon": "🧩"},
        "plantoes": {"label": "Plantões", "icon": "📅"},
        "manuais": {"label": "Manuais", "icon": "📚"},
        "wikis": {"label": "Wikis", "icon": "📖"},
        "email": {"label": "Email", "icon": "📧"},
    }
    cols = st.columns(4)
    for i, (tipo, info) in enumerate(raspagens_ui.items()):
        with cols[i % 4]:
            if st.button(f"{info['icon']} {info['label']}", key=f"btn_{tipo}", use_container_width='strech', disabled=em_andamento):
                if BOT_CONTROL_DISPONIVEL:
                    ok, msg = solicitar_raspagem(tipo)
                    st.toast(msg, icon="✅" if ok else "⚠️")
                    if ok:
                        st.success("Tarefa enviada ao motor. Aguarde a execução (veja Etapa atual acima).")
                    else:
                        st.warning(msg)
                else:
                    st.info("Serviço de controle de bot não disponível.")

# ==========================================
# ABA 2: RAMAIS E ANALISTAS
# ==========================================
ARQUIVO_RAMAIS = "ramais_config.json"

def _ler_ramais():
    if os.path.exists(ARQUIVO_RAMAIS):
        try:
            with open(ARQUIVO_RAMAIS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _salvar_ramais(dados):
    with open(ARQUIVO_RAMAIS, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

@st.cache_data(ttl=120)
def _obter_analistas_ativos():
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT DISTINCT usuario_epsy FROM chamados_tecnuv WHERE usuario_epsy IS NOT NULL AND usuario_epsy != ''", engine)
        return [a for a in df["usuario_epsy"].tolist() if a and a != "Não Informado"]
    except Exception:
        return []

with aba_ramais:
    st.subheader("Ramais e Analistas EPSY")
    st.caption("Os analistas cadastrados aqui são os mesmos que abrem chamados, estão nos plantões, contribuições e dashboards. Cadastre/altere ramais.")

    ramais = _ler_ramais()
    analistas = _obter_analistas_ativos()

    col_r1, col_r2 = st.columns([1, 1.5])
    with col_r1:
        with st.form("form_ramal"):
            sel = st.selectbox("Analista", ["-- Novo --"] + analistas)
            nome = st.text_input("Nome") if sel == "-- Novo --" else sel
            ramal = st.text_input("Número do Ramal")
            if st.form_submit_button("Vincular"):
                if nome and ramal:
                    ramais[nome.strip()] = ramal.strip()
                    _salvar_ramais(ramais)
                    st.success(f"Ramal vinculado a {nome}.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("Preencha nome e ramal.")

    with col_r2:
        if ramais:
            df_r = pd.DataFrame(list(ramais.items()), columns=["Analista", "Ramal"]).sort_values("Analista")
            st.dataframe(df_r, hide_index=True, use_container_width='strech')
            remover = st.selectbox("Remover", [""] + list(ramais.keys()))
            if st.button("Remover") and remover:
                del ramais[remover]
                _salvar_ramais(ramais)
                st.rerun()

# ==========================================
# ABA 3: USUÁRIOS
# ==========================================
@st.cache_data(ttl=120)
def _obter_usuarios():
    engine = get_connection()
    try:
        return pd.read_sql("SELECT id, nome, email, perfil, ramal, ativo FROM usuarios ORDER BY nome", engine)
    except Exception:
        return pd.DataFrame()

with aba_usuarios:
    st.subheader("Gestão de Usuários")
    df_u = _obter_usuarios()

    if df_u.empty:
        st.warning("Nenhum usuário encontrado.")
    else:
        u1, u2 = st.columns(2)

        with u1:
            st.markdown("#### Alterar usuário (exceto dev)")
            user_sel = st.selectbox("Usuário", df_u["nome"].tolist())
            row = df_u[df_u["nome"] == user_sel].iloc[0]
            is_dev = str(row.get("perfil", "")).lower() in ("dev", "desenvolvedor")

            if is_dev:
                st.warning("⛔ Alteração de perfil e senha do usuário **dev** não é permitida aqui.")
            else:
                perfis = [p for p in ["Analista", "Coordenação"]]
                idx = perfis.index(row["perfil"]) if row["perfil"] in perfis else 0
                novo_perfil = st.selectbox("Perfil", perfis, index=idx)
                nova_senha = st.text_input("Nova senha (vazio = manter)", type="password")

                if st.button("Salvar alterações"):
                    engine = get_connection()
                    try:
                        with engine.begin() as conn:
                            if nova_senha.strip():
                                conn.execute(text("UPDATE usuarios SET perfil = :p, password_hash = :s WHERE nome = :n"), {"p": novo_perfil, "s": nova_senha.strip(), "n": user_sel})
                            else:
                                conn.execute(text("UPDATE usuarios SET perfil = :p WHERE nome = :n"), {"p": novo_perfil, "n": user_sel})
                        st.success("Alterado.")
                        registrar_log_auditoria(usuario_id, "UPDATE_USER", f"Alterou {user_sel}")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        with u2:
            st.markdown("#### Senha do desenvolvedor")
            st.caption("Apenas o próprio dev pode alterar sua senha. Não é permitido alterar o perfil dev.")
            if perfil_usuario != "dev":
                st.error("Acesso restrito ao perfil desenvolvedor.")
            else:
                nova_admin = st.text_input("Nova senha admin", type="password", key="pass_admin")
                if st.button("Atualizar senha admin"):
                    if nova_admin.strip():
                        with get_connection().begin() as conn:
                            res = conn.execute(text("UPDATE usuarios SET password_hash = :s WHERE id = :id AND LOWER(perfil) IN ('dev', 'desenvolvedor')"), {"s": nova_admin.strip(), "id": usuario_id})
                            rows = res.rowcount
                        if rows and rows > 0:
                            st.success("Senha alterada.")
                            st.rerun()
                        else:
                            st.error("Nenhuma linha atualizada.")
                    else:
                        st.warning("Senha não pode ser vazia.")

# ==========================================
# ABA 4: CLIENTES E TELEFONES
# ==========================================
def _apenas_numeros(txt):
    return re.sub(r"\D", "", str(txt)) if txt else ""

with aba_clientes:
    st.subheader("Clientes e Telefones")
    st.caption("Um CNPJ = uma Razão Social. Cadastre vários telefones por cliente. Usado para cruzar Goto/Multi360 e identificar quem mais consome suporte.")

    with st.form("form_cliente"):
        razao = st.text_input("Razão Social *", placeholder="Ex: Posto Avenida LTDA")
        cnpj = _apenas_numeros(st.text_input("CNPJ", placeholder="00.000.000/0000-00"))
        tel = _apenas_numeros(st.text_input("Telefone/Celular *", placeholder="48999999999"))
        if st.form_submit_button("Salvar e vincular"):
            if razao and tel:
                engine = get_connection()
                try:
                    from modules.processador_csv import gerar_hash_lgpd
                    tel_hash = gerar_hash_lgpd(tel)
                    with engine.begin() as conn:
                        id_cli = None
                        if cnpj:
                            try:
                                id_cli = conn.execute(text("SELECT id_cliente FROM clientes_crm WHERE cnpj = :c LIMIT 1"), {"c": cnpj}).scalar()
                            except Exception:
                                pass
                        if not id_cli:
                            try:
                                id_cli = conn.execute(text("SELECT id_cliente FROM clientes_crm WHERE razao_social ILIKE :n LIMIT 1"), {"n": f"%{razao.strip()}%"}).scalar()
                            except Exception:
                                pass
                        if not id_cli:
                            try:
                                id_cli = conn.execute(text("INSERT INTO clientes_crm (razao_social, cnpj) VALUES (:n, :c) RETURNING id_cliente"), {"n": razao.strip(), "c": cnpj or None}).scalar()
                            except Exception:
                                id_cli = conn.execute(text("INSERT INTO clientes_crm (razao_social) VALUES (:n) RETURNING id_cliente"), {"n": razao.strip()}).scalar()
                        for sql, params in [
                            (text("INSERT INTO clientes_telefones (id_cliente, numero, telefone_hash, origem_dado) VALUES (:id, :tel, :h, 'MANUAL')"), {"id": id_cli, "tel": tel, "h": tel_hash}),
                            (text("INSERT INTO clientes_telefones (id_cliente, numero, origem_dado) VALUES (:id, :tel, 'MANUAL')"), {"id": id_cli, "tel": tel}),
                        ]:
                            try:
                                conn.execute(sql, params)
                                break
                            except Exception:
                                continue
                    st.success(f"Cliente {razao} vinculado ao telefone.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            else:
                st.warning("Preencha Razão Social e Telefone.")

    try:
        df_cli = pd.read_sql("""
            SELECT c.id_cliente, c.razao_social, c.cnpj, COUNT(t.id_cliente) as qtd_telefones
            FROM clientes_crm c
            LEFT JOIN clientes_telefones t ON t.id_cliente = c.id_cliente
            GROUP BY c.id_cliente, c.razao_social, c.cnpj
            ORDER BY c.razao_social
        """, get_connection())
        if not df_cli.empty:
            st.dataframe(df_cli, hide_index=True, use_container_width='strech')
    except Exception as e:
        st.caption(f"Listagem indisponível: {e}")

# # ==========================================
# # ABA 5: DIAGNÓSTICO
# # ==========================================
# with aba_diagnostico:
#     if perfil_usuario != "dev":
#         st.error("Acesso restrito ao desenvolvedor.")
#     else:
#         st.subheader("Diagnóstico do Servidor")
#         d1, d2, d3 = st.columns(3)
#         with d1:
#             if st.button("Testar DB"):
#                 t0 = time.time()
#                 try:
#                     with get_connection().connect() as c:
#                         c.execute(text("SELECT 1"))
#                     st.success(f"Conexão OK — {((time.time()-t0)*1000):.0f} ms")
#                 except Exception as e:
#                     st.error(str(e))
#         with d2:
#             if st.button("Testar Internet"):
#                 try:
#                     urllib.request.urlopen("http://8.8.8.8", timeout=3)
#                     st.success("Ping OK")
#                 except Exception:
#                     st.error("Falha de rede")
#         with d3:
#             if st.button("Recursos") and HAS_PSUTIL:
#                 st.metric("CPU", f"{psutil.cpu_percent()}%")
#                 st.metric("RAM", f"{psutil.virtual_memory().percent}%")

# registrar_log_auditoria(usuario_id, "VIEW_CONFIG", "Acessou configurações.")
