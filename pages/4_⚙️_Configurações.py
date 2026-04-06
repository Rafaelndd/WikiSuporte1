"""
WikiSuporte - Página de Configurações.
Permite controle dos bots de varredura e cadastro de clientes com telefones.
Acesso restrito ao perfil **admin**. O status dos bots é lido do arquivo `robo_state.json` e pode ser controlado por este painel, mas o motor precisa estar rodando (via `motor_extracao.py`) para processar as solicitações. O cadastro de clientes/telefones é usado para cruzar dados de suporte. Logs de auditoria registram ações importantes.
"""
import re
import time
import urllib.request
from datetime import date, datetime

import pandas as pd
import streamlit as st

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from modules.utils import ler_estado_robo, salvar_estado_robo
from services.clientes_service import (
    buscar_clientes_autocomplete,
    garantir_indices_clientes_busca,
    listar_clientes_telefones_resumo,
    vincular_telefone_cliente,
)
from services.system_notifications import (
    bloqueios_versao_ativos,
    criar_notificacao,
    desativar_notificacao,
    ensure_schema as ensure_notifications_schema,
    listar_notificacoes_admin,
    normalizar_tipo_notificacao,
    registrar_bloqueio_versao,
    resolver_bloqueio_versao,
)
from services.perfil_usuario import eh_admin
from services.ui_realtime import render_global_notifications_listener
from services.ui_theme_presets import wiki_theme_apply_authenticated
from services.wiki_authenticator import process_forced_logout_from_url
from utils.release_manager import append_release, catalog_path, load_catalog

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

if process_forced_logout_from_url():
    st.rerun()

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

usuario_id = st.session_state.get("usuario_id")
nome_usuario = str(st.session_state.get("usuario_nome", "Sistema"))
perfil_raw = st.session_state.get("perfil", "")
render_global_notifications_listener()
wiki_theme_apply_authenticated()
ensure_notifications_schema()

if not eh_admin(perfil_raw):
    st.error("⛔ Acesso Negado. Apenas usuários com perfil **admin**.")
    st.stop()

perfil_usuario = "admin"

st.title("⚙️ WikiSuporte - Configurações")
st.markdown("Controle dos bots, clientes e comunicados globais do sistema.")

nomes_abas = [
    "🤖 Bots",
    "🏢 Clientes e Telefones",
    "📢 Lançar Nova Versão",
]
tem_painel_notifs = True
if tem_painel_notifs:
    nomes_abas.append("📣 Notificações e Comunicados")
abas = st.tabs(nomes_abas)
aba_robo, aba_clientes, aba_release_launch = abas[:3]
aba_notificacoes = abas[3] if tem_painel_notifs else None

# ==========================================
# ABA 1: BOTS DE VARREDURA
# ==========================================
with aba_robo:
    st.subheader("Controle dos Bots de buscas")
    with st.expander("🤔 Como usar esta área?"):
        st.markdown(
            "**Status dos Bots**: O status de execução dos bots é lido do arquivo `robo_state.json`, que o motor de extração atualiza. Se o motor não estiver rodando, o status pode ficar preso — use o botão **Forçar Parado** para corrigir. "
            "**Configurações**: Ative/desative varreduras automáticas, ajuste o intervalo entre varreduras e defina limites de segurança para evitar sobrecarga do servidor. "
            "**Raspagens Individuais**: Solicite varreduras específicas (chamados, tickets, releases, etc.) a qualquer momento. O motor precisa estar rodando para processar essas solicitações. O status e a etapa atual serão atualizados conforme o motor executa as tarefas. "
            "**Aviso Importante**: Respeite os intervalos mínimos e máximos para evitar bloqueios ou sobrecarga do servidor da TECNUV. O motor de extração é responsável por seguir essas regras, mas o controle manual também está disponível para casos excepcionais."
        )
    estado = ler_estado_robo() if not BOT_CONTROL_DISPONIVEL else ler_estado()
    if BOT_CONTROL_DISPONIVEL:
        if sincronizar_estado_se_motor_morto():
            estado = ler_estado()
            st.toast("As buscas estão sendo sincronizadas...", icon="✅")

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
            auto_ativo = st.toggle("Ativar buscas automáticas", value=estado.get("auto_ativo", False))
            intervalo = st.slider("Intervalo entre buscas (min)", min_value=MIN_INTERVALO_MINUTOS if BOT_CONTROL_DISPONIVEL else 15, max_value=240, value=estado.get("intervalo", 60), step=15)
            min_intervalo = st.number_input("Mín. intervalo entre buscas (min) - segurança", min_value=15, max_value=120, value=estado.get("min_intervalo", MIN_INTERVALO_MINUTOS), step=5) if BOT_CONTROL_DISPONIVEL else None
            max_por_hora = st.number_input("Máx. buscas por hora - proteção servidor", min_value=1, max_value=6, value=estado.get("max_raspagens_hora", MAX_RASPAGENS_POR_HORA)) if BOT_CONTROL_DISPONIVEL else None

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
        "**⚠️ Importante: A Extração de dados ** precisa estar ativa para processar as solicitações de buscas no HelpDesk. O status e as etapas são atualizados conforme a execução dos bots. "
        "Se o status ficar preso ou não atualizar, use o botão **Forçar Parado** para corrigir. Respeite os intervalos mínimos e máximos para evitar bloqueios ou sobrecarga do servidor da TECNUV."
    )
    if BOT_CONTROL_DISPONIVEL:
        st.markdown("#### Forçar parada das buscas")
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
    st.caption("Clique em um dos botões abaixo para solicitar uma varredura específica.")
    st.info(
        "**Dashboard Chamados**: Após solicitar uma busca, o status é atualizado no arquivo de estado. Se o status ficar preso ou não atualizar, use o botão **Forçar Parada** para corrigir. "
      
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
            if st.button(f"{info['icon']} {info['label']}", key=f"btn_{tipo}", use_container_width="stretch", disabled=em_andamento):
                if BOT_CONTROL_DISPONIVEL:
                    ok, msg = solicitar_raspagem(tipo)
                    st.toast(msg, icon="✅" if ok else "⚠️")
                    if ok:
                        st.success("Tarefa enviada ao sistema. Aguarde a execução (veja Etapa atual acima).")
                    else:
                        st.warning(msg)
                else:
                    st.info("Serviço de controle de bot não disponível.")

# ==========================================
# ABA 2: CLIENTES E TELEFONES
# ==========================================
def _apenas_numeros(txt):
    return re.sub(r"\D", "", str(txt)) if txt else ""

with aba_clientes:
    st.subheader("Cadastre e Vincule números de Telefone/Celular ao cadastro dos clientes cadastrados")

    ok_idx, msg_idx = garantir_indices_clientes_busca()
    if not ok_idx:
        st.warning(f"Não foi possível validar os índices de busca agora: {msg_idx}")

    if "cfg_cli_razao_social" not in st.session_state:
        st.session_state["cfg_cli_razao_social"] = ""
    if "cfg_cli_cnpj" not in st.session_state:
        st.session_state["cfg_cli_cnpj"] = ""
    if "cfg_cli_telefone" not in st.session_state:
        st.session_state["cfg_cli_telefone"] = ""
    if "cfg_cli_last_sel_razao" not in st.session_state:
        st.session_state["cfg_cli_last_sel_razao"] = ""
    if "cfg_cli_last_sel_cnpj" not in st.session_state:
        st.session_state["cfg_cli_last_sel_cnpj"] = ""

    def _aplicar_sugestao_cliente(label_escolhido: str, opcoes: dict[str, dict]) -> None:
        escolhido = opcoes.get(label_escolhido)
        if not escolhido:
            return
        st.session_state["cfg_cli_razao_social"] = str(escolhido.get("razao_social") or "")
        st.session_state["cfg_cli_cnpj"] = str(escolhido.get("cnpj") or "")
        st.rerun()

    st.markdown("#### Busca inteligente em tempo real")
    b1, b2 = st.columns(2)
    with b1:
        busca_razao = st.text_input(
            "Buscar por razão social/nome/CNPJ",
            key="cfg_cli_busca_razao",
            placeholder="Digite parte do nome, razão social ou CNPJ",
        )
        if (busca_razao or "").strip():
            df_sug_razao = buscar_clientes_autocomplete(busca_razao, limite=12)
            if not df_sug_razao.empty:
                opcoes_razao = {"": {}}
                for _, row in df_sug_razao.iterrows():
                    label = f"{row['razao_social']} | CNPJ: {row['cnpj'] or 'não informado'}"
                    opcoes_razao[label] = {
                        "razao_social": str(row["razao_social"] or ""),
                        "cnpj": str(row["cnpj"] or ""),
                    }
                escolha_razao = st.selectbox(
                    "Sugestões da busca por razão social",
                    list(opcoes_razao.keys()),
                    key="cfg_cli_sug_razao",
                )
                if escolha_razao and escolha_razao != st.session_state.get("cfg_cli_last_sel_razao", ""):
                    st.session_state["cfg_cli_last_sel_razao"] = escolha_razao
                    _aplicar_sugestao_cliente(escolha_razao, opcoes_razao)
                elif not escolha_razao:
                    st.session_state["cfg_cli_last_sel_razao"] = ""
            else:
                st.caption("Nenhuma correspondência encontrada para essa busca.")
    with b2:
        busca_cnpj = st.text_input(
            "Buscar por CNPJ (com ou sem máscara)",
            key="cfg_cli_busca_cnpj",
            placeholder="Ex.: 12.345.678/0001-90 ou 12345678000190",
        )
        if (busca_cnpj or "").strip():
            df_sug_cnpj = buscar_clientes_autocomplete(busca_cnpj, limite=12)
            if not df_sug_cnpj.empty:
                opcoes_cnpj = {"": {}}
                for _, row in df_sug_cnpj.iterrows():
                    label = f"{row['cnpj'] or 'não informado'} | {row['razao_social']}"
                    opcoes_cnpj[label] = {
                        "razao_social": str(row["razao_social"] or ""),
                        "cnpj": str(row["cnpj"] or ""),
                    }
                escolha_cnpj = st.selectbox(
                    "Sugestões da busca por CNPJ",
                    list(opcoes_cnpj.keys()),
                    key="cfg_cli_sug_cnpj",
                )
                if escolha_cnpj and escolha_cnpj != st.session_state.get("cfg_cli_last_sel_cnpj", ""):
                    st.session_state["cfg_cli_last_sel_cnpj"] = escolha_cnpj
                    _aplicar_sugestao_cliente(escolha_cnpj, opcoes_cnpj)
                elif not escolha_cnpj:
                    st.session_state["cfg_cli_last_sel_cnpj"] = ""
            else:
                st.caption("Nenhuma correspondência encontrada para esse CNPJ.")

    st.markdown("#### Vincular telefone")
    c1, c2, c3 = st.columns(3)
    with c1:
        razao = st.text_input(
            "Razão Social *",
            key="cfg_cli_razao_social",
            placeholder="Ex.: Posto Avenida LTDA",
        )
    with c2:
        cnpj_in = st.text_input(
            "CNPJ",
            key="cfg_cli_cnpj",
            placeholder="00.000.000/0000-00",
        )
    with c3:
        tel_in = st.text_input(
            "Telefone/Celular *",
            key="cfg_cli_telefone",
            placeholder="48999999999",
        )

    if st.button("Salvar e vincular", type="primary", key="cfg_cli_btn_salvar", use_container_width=True):
        razao_limpa = (razao or "").strip()
        cnpj_limpo = _apenas_numeros(cnpj_in)
        tel_limpo = _apenas_numeros(tel_in)
        if not razao_limpa or not tel_limpo:
            st.warning("Preencha Razão Social e Telefone/Celular.")
        else:
            ok, msg = vincular_telefone_cliente(
                razao_social=razao_limpa,
                numero_raw=tel_limpo,
                cnpj=cnpj_limpo or None,
            )
            if ok:
                st.success("Vínculo salvo com sucesso. Os dados já ficam disponíveis na página de Registro de Atendimentos.")
                st.session_state["cfg_cli_telefone"] = ""
                st.rerun()
            else:
                st.error(msg)

    try:
        df_cli = listar_clientes_telefones_resumo(limite=2000)
        if not df_cli.empty:
            df_cli = df_cli.rename(
                columns={
                    "razao_social": "Razão Social",
                    "cnpj": "CNPJ",
                    "qtd_telefones": "Qtd. Telefones",
                }
            )
            st.dataframe(df_cli, hide_index=True, use_container_width="stretch")
    except Exception as e:
        st.caption(f"Listagem indisponível: {e}")

# ==========================================
# ABA: LANÇAR NOVA VERSÃO (RELEASE NOTES)
# ==========================================
with aba_release_launch:
    st.subheader("📢 Lançar Nova Versão")
    st.caption(
        "Publique novidades do sistema de forma simples. "
        "O aviso na Home ficará visível pelo período que você definir."
    )
    st.caption("Use esta área para comunicar melhorias e mudanças importantes para toda a equipe.")

    existentes = load_catalog(create_if_missing=True)
    if existentes:
        ult = existentes[0]
        st.info(
            f"Última publicada: **{ult.versao}** · {ult.data_lancamento} · "
            f"aviso na Home até **{ult.notificacao_ate}**."
        )

    with st.form("form_lancar_release_wikisuporte", clear_on_submit=False):
        in_versao = st.text_input("Número da versão", placeholder="v1.2.0")
        in_data = st.date_input("Data de lançamento", value=date.today())
        in_era = st.text_area("Como era", height=110, placeholder="Descreva o comportamento ou limitação anterior.")
        in_ficou = st.text_area("Como ficou", height=130, placeholder="Descreva a melhoria ou a nova experiência.")
        in_dias = st.number_input(
            "Dias com notificação na Home (inclui o dia de lançamento)",
            min_value=1,
            max_value=365,
            value=7,
            step=1,
            help="Ex.: 7 = mostra na Home durante 7 dias corridos a partir da data de lançamento.",
        )
        submitted = st.form_submit_button("💾 Guardar release", type="primary", use_container_width=True)

        if submitted:
            if not (in_versao or "").strip():
                st.error("Indique o número da versão.")
            elif not (in_era or "").strip() or not (in_ficou or "").strip():
                st.error("Preencha **Como era** e **Como ficou**.")
            else:
                try:
                    rec = append_release(
                        versao=in_versao.strip(),
                        data_lancamento=in_data,
                        como_era=in_era,
                        como_ficou=in_ficou,
                        dias_notificacao=int(in_dias),
                    )
                    registrar_log_auditoria(
                        usuario_id,
                        "RELEASE_PUBLISH",
                        f"Publicou release {rec.versao} (aviso até {rec.notificacao_ate})",
                    )
                    st.cache_data.clear()
                    st.success(
                        f"Release **{rec.versao}** guardada. Aviso na Home até **{rec.notificacao_ate}**."
                    )
                    st.balloons()
                    st.rerun()
                except ValueError as ve:
                    st.error(str(ve))
                except OSError as oe:
                    st.error(f"Falha ao gravar arquivo: {oe}")

if aba_notificacoes:
    with aba_notificacoes:
        st.subheader("📣 Painel do Suporte para Notificações")
        st.caption(
            "Dispare comunicados em tempo real para usuários ativos. "
            "Tipos: comunicado, aviso, erro crítico, bloqueio de versão e release WikiSuporte."
        )

        releases_catalog = load_catalog(create_if_missing=True)
        release_mais_recente = releases_catalog[0] if releases_catalog else None
        release_titulo_auto = ""
        release_msg_auto = ""
        release_meta_auto = ""
        if release_mais_recente:
            data_release_fmt = release_mais_recente.data_lancamento
            try:
                data_release_fmt = datetime.fromisoformat(
                    release_mais_recente.data_lancamento
                ).strftime("%d/%m/%Y")
            except ValueError:
                pass
            resumo_release = " ".join((release_mais_recente.como_ficou or "").split())
            if len(resumo_release) > 220:
                resumo_release = resumo_release[:217].rstrip() + "..."
            release_titulo_auto = f"Novo release WikiSuporte: {release_mais_recente.versao}"
            release_msg_auto = (
                f"Nova versão do WikiSuporte disponível ({release_mais_recente.versao} · {data_release_fmt}). "
                "Acesse a página Notas de versão no menu lateral para ver o comparativo completo de melhorias."
            )
            if resumo_release:
                release_msg_auto += f" Destaque: {resumo_release}"
            release_meta_auto = (
                f"Release ativo para comunicado automático: {release_mais_recente.versao} "
                f"({data_release_fmt})."
            )

        with st.form("form_notificacao_admin"):
            c1, c2, c3 = st.columns(3)
            tipo = c1.selectbox(
                "Tipo *",
                [
                    "Comunicado",
                    "Aviso",
                    "Erro Crítico",
                    "Versão Bloqueada",
                    "Release WikiSuporte",
                ],
                help="Erro crítico e versão bloqueada aparecem com destaque no topo.",
            )
            target_role = c2.selectbox("Público-alvo", ["Todos", "Analistas", "Supervisores", "Coordenadores", "Desenvolvedores"])
            horas_expira = c3.number_input("Expira em (horas)", min_value=0, max_value=720, value=0, step=1)
            minutos_expira = st.number_input(
                "Expira em (minutos)",
                min_value=0,
                max_value=59,
                value=0,
                step=1,
                help="Use horas e minutos. Ex.: 1 hora e 30 minutos.",
            )
            tipo_release = tipo == "Release WikiSuporte"
            tipo_bloqueio = tipo == "Versão Bloqueada"

            if tipo_release:
                if release_mais_recente is None:
                    st.error(
                        "Não foi possível localizar um release no histórico. "
                        "Publique primeiro em 'Lançar Nova Versão'."
                    )
                else:
                    st.info(f"ℹ️ {release_meta_auto}")
                    st.markdown("**Último release (sempre usado neste tipo):**")
                    st.markdown(
                        f"- **Versão:** {release_mais_recente.versao}\n"
                        f"- **Data:** {data_release_fmt}\n"
                        f"- **Como ficou:** {release_mais_recente.como_ficou or '—'}"
                    )
                titulo = st.text_input(
                    "Título",
                    value=release_titulo_auto,
                    disabled=True,
                )
                mensagem = st.text_area(
                    "Mensagem *",
                    value=release_msg_auto,
                    height=120,
                    disabled=True,
                )
            else:
                titulo = st.text_input("Título")
                mensagem = st.text_area("Mensagem *", height=120)

            modulo_nome = ""
            versao_prob = ""
            motivo_bloqueio = ""
            if tipo_bloqueio:
                cmod1, cmod2 = st.columns(2)
                modulo_nome = cmod1.text_input("Módulo com erro de versão (opcional)")
                versao_prob = cmod2.text_input("Versão problemática (opcional)")
                motivo_bloqueio = st.text_area(
                    "Motivo do bloqueio de versão (opcional)",
                    height=80,
                )

            salvar_notif = st.form_submit_button("🚀 Publicar notificação", type="primary", use_container_width=True)

            if salvar_notif:
                if tipo_release and release_mais_recente is None:
                    st.error(
                        "Não há release disponível para este tipo de comunicado. "
                        "Publique primeiro uma nova versão."
                    )
                elif not mensagem.strip():
                    st.error("Mensagem é obrigatória.")
                else:
                    tipo_norm = normalizar_tipo_notificacao(tipo)
                    if not tipo_norm:
                        st.error("Tipo de notificação inválido.")
                    else:
                        titulo_publicar = release_titulo_auto if tipo_release else titulo
                        mensagem_publicar = release_msg_auto if tipo_release else mensagem
                        with st.status("Publicando comunicado...", expanded=False) as status:
                            exp = None
                            total_minutos_exp = (int(horas_expira or 0) * 60) + int(minutos_expira or 0)
                            if total_minutos_exp > 0:
                                exp = datetime.now() + pd.Timedelta(minutes=total_minutos_exp)
                            ok, msg = criar_notificacao(
                                tipo=tipo_norm,
                                mensagem=mensagem_publicar,
                                autor=nome_usuario,
                                titulo=titulo_publicar,
                                target_role=target_role,
                                data_expiracao=exp,
                                dedupe_seconds=120,
                            )
                            if ok and tipo_norm == "versao_bloqueada" and modulo_nome.strip() and versao_prob.strip():
                                okb, _ = registrar_bloqueio_versao(
                                    modulo_nome.strip(), versao_prob.strip(), motivo_bloqueio.strip()
                                )
                                if not okb:
                                    st.warning("Notificação publicada, mas falhou ao gravar em bloqueio_versoes.")
                            if ok:
                                status.update(label="Notificação publicada com sucesso.", state="complete")
                                st.toast("✅ Comunicado publicado em tempo real.", icon="✅")
                                st.success(msg)
                                st.rerun()
                            else:
                                status.update(label="Falha ao publicar.", state="error")
                                st.error(msg)

        st.markdown("### Notificações recentes")
        df_not = listar_notificacoes_admin(120)
        if df_not.empty:
            st.info("Nenhuma notificação cadastrada.")
        else:
            st.dataframe(df_not, hide_index=True, use_container_width=True)
            with st.form("form_desativar_notificacao"):
                ativo_series = df_not["ativo"].astype(str).str.lower().isin(["true", "t", "1"])
                ids = df_not[ativo_series]["id"].tolist()
                id_desativar = st.selectbox("Desativar notificação ativa", [""] + [str(i) for i in ids])
                btn_off = st.form_submit_button("Desativar", use_container_width=True)
                if btn_off and id_desativar:
                    okd, msgd = desativar_notificacao(int(id_desativar))
                    if okd:
                        st.cache_data.clear()
                        st.success(msgd)
                        st.rerun()
                    else:
                        st.error(msgd)

        st.markdown("### Bloqueios de versão ativos")
        df_blocks = bloqueios_versao_ativos()
        if df_blocks.empty:
            st.caption("Sem bloqueios ativos.")
        else:
            st.dataframe(df_blocks, hide_index=True, use_container_width=True)
            with st.form("form_resolver_bloqueio_versao"):
                id_resolver = st.selectbox(
                    "Marcar bloqueio como resolvido",
                    [""] + [str(i) for i in df_blocks["id"].astype(int).tolist()],
                )
                btn_resolver = st.form_submit_button("Resolver bloqueio", use_container_width=True)
                if btn_resolver and id_resolver:
                    okr, msgr = resolver_bloqueio_versao(int(id_resolver))
                    if okr:
                        st.cache_data.clear()
                        st.success(msgr)
                        st.rerun()
                    else:
                        st.error(msgr)
