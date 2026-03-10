import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# 1. CONFIGURAÇÃO E AUTENTICAÇÃO
# ==========================================
st.set_page_config(page_title="Registro de Atendimentos", page_icon="📝", layout="wide")

if not st.session_state.get('autenticado'): 
    st.switch_page("app.py")

# Perfil do usuário logado
perfil = st.session_state.get('perfil', 'analista').lower()
id_analista = st.session_state.get('usuario_id')

st.title("📝 Registro de Atendimentos")
st.markdown("Registre, consulte e gerencie os atendimentos diários do Helpdesk.")

# ==========================================
# 2. DICIONÁRIO DE DADOS DINÂMICO (Da Especificação)
# ==========================================
# Mapeamento de Setores para Categorias
dict_categorias = {
    "Suporte": ["API POSTOGESTOR", "APLICATIVOS", "ATENDIMENTOS TERCEIROS", "BANCO DE DADOS", "DEMANDA INTERNA", "GERENCIAL", "PDV - CAIXA", "PDV MOVEL", "Pós ATENDIMENTO", "Pré Implantação", "REAJUSTE DE PREÇOS", "SISTEMAS WEB E APP'S"],
    "TEF": ["Geral", "Instalação", "Suporte TEF"],
    "Comercial": ["Dúvidas", "Renovação", "Cancelamento"],
    "Financeiro": ["Boleto", "Faturamento", "Negociação"]
}

# Mapeamento de Categorias para Classificações (Apenas do Setor Suporte conforme especificado)
dict_classificacoes = {
    "APLICATIVOS": ["Comportamento Inesperado Erro", "PG Coletor+", "PG comanda Mob"],
    "BANCO DE DADOS": ["Criação de Relatório Personalizado", "Migração de Postgres", "Recuperação de banco de dados", "Replicação", "Servidor com problema", "Troca de servidor"],
    "GERENCIAL": ["AJUSTE DE ENCERRANTE", "ATUALIZAÇÃO DO SISTEMA", "BANCO DE DADOS", "CADASTROS EM GERAL", "CHAT SEM RESPOSTA", "COMUNICAÇÃO COM A IMPRESSORA Não FISCAL", "CONCILIAÇÃO DE CARTÕES", "CONFERÊNCIA DE CAIXA", "CONFIGURAÇÃO DE SISTEMA", "DúVIDA OU ERRO ARQUIVOS FISCAIS", "DUVIDA USUARIO", "EMISSAO DE NF-E", "ENTRADAS (ESTOQUE/NOTA)", "ENVIO DE EMAIL", "ERRO DE CADASTROS EM GERAL", "ERRO EMISSÃO DE MDF-E OU CT-E", "ERRO OPERACIONAL USUARIO", "ERRO SISTEMA POSTOGESTOR", "ERROS NO REPLICADOR (SINCRONIA)", "FATURAMENTO", "INVENTÁRIO", "LENTIDÃO NO SISTEMA", "LIBERAÇÃO DE VERSÃO", "LMC", "PEDIDO DE MELHORIA", "PROBLEMA INTERNO NO CLIENTE", "REAJUSTE DE PREÇOS", "REGRA DE PRECO CLIENTES", "SAIDA (ESTOQUE/NOTA)", "SERVIÇO POSTO GESTOR PARADO", "SERVIÇOS PG PARADO", "SOLICITAÇÃO DE NOVO RELATÓRIO", "SPED EM GERAL", "TREINAMENTO ONLINE", "VENDA TRAVADA", "Outros (Especificar)"],
    "PDV - CAIXA": ["ARQUIVOS FISCAIS", "AUTOMAÇÃO", "BANCO DE DADOS", "BICO AMARELO", "BICO AZUL NA TELA", "CHAT SEM RESPOSTA", "CONFIGURAÇÃO DO SISTEMA", "DUVIDA USUARIO", "ERRO AO BAIXAR VENDA", "ERRO DO USUARIO AO LANCAR NOTA", "ERRO OPERACIONAL DE USUÁRIO", "ERRO SISTEMA POSTOGESTOR", "ESTOQUE", "IMPRESSORA TRAVADA", "LENTIDÃO NO SISTEMA", "PRE-VENDAS", "PROBLEMA DE HARDWARE", "REAJUSTE DE PREÇOS", "TEF EM GERAL", "TROCA DE EQUIPAMENTO"],
    "PDV MOVEL": ["Configuração de PDV Móvel", "Dúvidas usuário PDV Móvel", "Erro no PDV Móvel"],
    "Pós ATENDIMENTO": ["Retorno sobre chamado", "Retorno sobre ticket", "Retorno ao cliente"],
    "SISTEMAS WEB E APP'S": ["Helpdesk", "PG Mobile", "PG Monitor", "PG WEB"] # Assumi que POSTOGESTOR WEB/API entrava aqui
}

# ==========================================
# 3. TABS (ABAS) DE NAVEGAÇÃO
# ==========================================
# Analistas veem 2 abas. Coordenadores veem 3 (com os Dashboards).
if perfil in ['coordenação', 'desenvolvedor']:
    tab_lancamento, tab_historico, tab_gestao = st.tabs(["📝 Lançar Atendimento", "🔍 Meu Histórico", "📊 Visão do Coordenador"])
else:
    tab_lancamento, tab_historico = st.tabs(["📝 Lançar Atendimento", "🔍 Meu Histórico"])

# --- ABA 1: LANÇAMENTO DE ATENDIMENTO ---
with tab_lancamento:
    with st.container(border=True):
        st.subheader("Ficha de Atendimento")
        
        with st.form("form_atendimento"):
            # Bloco 1: Cliente
            st.markdown("#### 👤 Dados do Cliente")
            c_cli1, c_cli2, c_cli3 = st.columns([2, 1, 1])
            with c_cli1:
                nome_cliente = st.text_input("Nome do Cliente", placeholder="Busque ou digite o nome do cliente EPSY")
            with c_cli2:
                numero_cliente = st.text_input("Número do Contato", placeholder="(XX) XXXXX-XXXX")
            with c_cli3:
                cnpj_cliente = st.text_input("CNPJ", placeholder="Preenchimento automático", disabled=False)
            
            st.divider()
            
            # Bloco 2: Classificação
            st.markdown("#### 🗂️ Tipificação")
            c_tip1, c_tip2, c_tip3 = st.columns(3)
            with c_tip1:
                setor = st.selectbox("Setor", options=["Suporte", "TEF", "Comercial", "Financeiro"])
            with c_tip2:
                # Categoria dinâmica baseada no Setor
                opcoes_cat = dict_categorias.get(setor, ["Geral"])
                categoria = st.selectbox("Categoria", options=opcoes_cat)
            with c_tip3:
                # Classificação dinâmica baseada na Categoria
                opcoes_class = dict_classificacoes.get(categoria, ["Outros"])
                classificacao = st.selectbox("Classificação", options=opcoes_class)
                
            st.divider()
            
            # Bloco 3: Canal e Status
            st.markdown("#### 📞 Canal e Status")
            c_canal1, c_canal2, c_canal3, c_canal4 = st.columns([1.5, 1, 1.5, 1])
            with c_canal1:
                tipo_contato = st.selectbox("Tipo de Contato", ["Chat Multi360", "Via Ligação GoTo", "E-mail", "Outros"])
            with c_canal2:
                protocolo = st.text_input("Protocolo", placeholder="Opcional se GoTo")
            with c_canal3:
                # Mostra o modo APENAS se for GoTo
                if tipo_contato == "Via Ligação GoTo":
                    modo_ligacao = st.selectbox("Modo", ["Receptiva (Recebi)", "Ativa (Liguei)"])
                else:
                    modo_ligacao = None
            with c_canal4:
                status = st.selectbox("Status do Ticket", ["Aberto", "Concluído"])

            st.divider()
            
            # Bloco 4: Relato
            st.markdown("#### 📝 Detalhes do Chamado")
            motivo = st.text_area("Motivo / Assunto do Atendimento*", placeholder="Descreva com detalhes o problema relatado pelo cliente (Mín. 10 caracteres)...", height=100)
            solucao = st.text_area("Solução Aplicada", placeholder="Descreva a solução, número de chamado na Tecnuv, ou próximos passos...", height=100)
            
            # Bloco 5: Anexos
            st.markdown("#### 📎 Anexos")
            anexos = st.file_uploader("Suba prints ou arquivos relacionados (Serão salvos localmente)", accept_multiple_files=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Botão de Salvar
            btn_salvar = st.form_submit_button("✅ Salvar Atendimento", type="primary", use_container_width='stretch')
            
            if btn_salvar:
                if len(motivo) < 10:
                    st.error("❌ O campo 'Motivo / Assunto' é obrigatório e deve conter no mínimo 10 caracteres.")
                elif not nome_cliente or not numero_cliente:
                    st.error("❌ Preencha os dados obrigatórios do cliente (Nome e Número).")
                else:
                    # AQUI ENTRARÁ A LÓGICA DE INSERT NO BANCO DE DADOS (SQLAlchemy)
                    st.success(f"✅ Atendimento de {nome_cliente} registrado com sucesso!")
                    if tipo_contato == "Via Ligação GoTo":
                        st.info("💡 O tempo de atendimento será cruzado e atualizado automaticamente na próxima importação do GoTo Connect.")

# --- ABA 2: HISTÓRICO DO ANALISTA ---
with tab_historico:
    st.subheader("🔍 Meus Atendimentos Recentes")
    st.info("Aqui o analista verá uma tabela com os atendimentos que ele próprio lançou, podendo filtrar por data ou status.")
    # Exemplo de Filtro
    with st.container(border=True):
        st.write("Filtros Rápidos")
        c_filtro1, c_filtro2 = st.columns(2)
        c_filtro1.date_input("Data Inicial")
        c_filtro2.date_input("Data Final")
    # Futuramente: df_meus_atendimentos = pd.read_sql(...)

# --- ABA 3: VISÃO DO COORDENADOR (Apenas Gestão) ---
if perfil in ['coordenação', 'desenvolvedor']:
    with tab_gestao:
        st.subheader("📊 Central de Relatórios do Suporte")
        st.write("Filtre e exporte todos os atendimentos da equipe.")
        
        with st.container(border=True):
            col_g1, col_g2, col_g3 = st.columns(3)
            with col_g1:
                st.selectbox("Filtrar por Analista", ["Todos", "Analista A", "Analista B"])
            with col_g2:
                st.selectbox("Filtrar por Assunto/Categoria", ["Todas"] + list(dict_classificacoes.keys()))
            with col_g3:
                st.selectbox("Status", ["Todos", "Aberto", "Concluído"])
                
        st.warning("Área em construção: Aqui os gráficos de produtividade cruzarão com os dados importados do Multi360 e GoTo.")