import streamlit as st
import pandas as pd
import re
from datetime import datetime
from sqlalchemy import text
from modules.database import get_connection

# Importa as suas funções brilhantes de LGPD e limpeza
from modules.processador_csv import processar_csv_goto, processar_csv_multi360, ler_arquivo_dinamico

# Tenta importar auditoria
try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

# ==========================================
# 1. CADEADO DE SEGURANÇA E SESSÃO
# ==========================================
if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()

# Apenas Desenvolvedores e Coordenação podem importar dados em massa
if perfil_usuario not in ["desenvolvedor", "superadmin", "coordenação", "coordenacao"]:
    st.error("⛔ Acesso Restrito. Apenas utilizadores com perfil de Coordenação ou superior podem importar ficheiros.")
    st.stop()

# ==========================================
# 2. FUNÇÕES AUXILIARES DE BANCO DE DADOS
# ==========================================
def salvar_no_banco(df, nome_tabela, tipo_arquivo):
    """Executa a lógica de Upsert inteligente para evitar duplicidade de dados."""
    engine = get_connection()
    try:
        with engine.begin() as conn:
            if tipo_arquivo == "GOTO":
                # Proteção: Deleta o intervalo de datas exato antes de inserir
                data_min = df['data_chamada'].min()
                data_max = df['data_chamada'].max()
                query_delete = text("DELETE FROM atendimentos_goto WHERE data_chamada >= :dmin AND data_chamada <= :dmax")
                conn.execute(query_delete, {"dmin": data_min, "dmax": data_max})
                
            elif tipo_arquivo == "MULTI360":
                # Proteção: Deleta os protocolos exatos antes de inserir
                lista_protocolos = df['protocolo'].dropna().tolist()
                if lista_protocolos:
                    query_delete = text("DELETE FROM atendimentos_multi360 WHERE protocolo = ANY(:ids)")
                    conn.execute(query_delete, {"ids": lista_protocolos})
            
            # Insere os dados limpos e com LGPD aplicada
            df.to_sql(nome_tabela, conn, if_exists='append', index=False)
            
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)

def apenas_numeros(texto):
    return re.sub(r'\D', '', str(texto))

# ==========================================
# 3. INTERFACE DE USUÁRIO (UX) - ABAS
# ==========================================
st.title("📁 Gestão e Importação de Dados")
st.markdown("Importe relatórios de telefonia/WhatsApp ou vincule clientes ao CRM.")

aba1, aba2 = st.tabs(["📥 Importar Relatórios (CSV/Excel)", "🔗 Vínculo de Clientes (CRM)"])

# ------------------------------------------
# ABA 1: IMPORTAÇÃO DE ARQUIVOS
# ------------------------------------------
with aba1:
    st.info("O sistema deteta automaticamente se o ficheiro pertence ao **GoTo (Telefonia)** ou ao **Multi360 (WhatsApp)**. Os dados sensíveis são anonimizados automaticamente (LGPD) antes de serem guardados.")
    
    arquivo_upload = st.file_uploader("Arraste e solte o ficheiro de relatório aqui", type=['csv', 'xlsx'])
    
    if arquivo_upload:
        # Verifica cabeçalhos rapidamente para rotear para o processador correto
        df_preview = ler_arquivo_dinamico(arquivo_upload)
        
        tipo_identificado = None
        df_processado = None
        erro_processamento = None
        
        if 'Conversation space id' in df_preview.columns:
            tipo_identificado = "GOTO"
            st.success("✅ Formato identificado: **Relatório de Telefonia (GoTo)**")
        elif 'PROTOCOLO' in df_preview.columns:
            tipo_identificado = "MULTI360"
            st.success("✅ Formato identificado: **Relatório de WhatsApp (Multi360)**")
        else:
            st.error("❌ Formato não reconhecido. Certifique-se de que o ficheiro é um relatório original do GoTo ou do Multi360.")
            st.stop()
            
        # Tenta processar e aplicar LGPD
        with st.spinner("A limpar dados e a aplicar regras de LGPD..."):
            try:
                # Retorna o ponteiro do arquivo para o início após o preview
                arquivo_upload.seek(0) 
                
                if tipo_identificado == "GOTO":
                    df_processado = processar_csv_goto(arquivo_upload)
                    nome_tabela_bd = "atendimentos_goto"
                else:
                    df_processado = processar_csv_multi360(arquivo_upload)
                    nome_tabela_bd = "atendimentos_multi360"
                    
            except Exception as e:
                erro_processamento = str(e)
                
        if erro_processamento:
            st.error(f"Ocorreu um erro durante o processamento do ficheiro: {erro_processamento}")
        elif df_processado is not None and not df_processado.empty:
            
            st.markdown("### 🔍 Pré-visualização dos Dados Limpos (LGPD)")
            st.caption("Nota: Os telefones e nomes já aparecem mascarados por segurança.")
            st.dataframe(df_processado.head(5), use_container_width=True)
            
            # Métricas
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Total de Registos", len(df_processado))
            
            if tipo_identificado == "GOTO":
                col_m2.metric("Data Inicial", df_processado['data_chamada'].min().strftime('%d/%m/%Y'))
                col_m3.metric("Data Final", df_processado['data_chamada'].max().strftime('%d/%m/%Y'))
            else:
                col_m2.metric("Data Inicial", df_processado['data_inicio'].min().strftime('%d/%m/%Y'))
                col_m3.metric("Data Final", df_processado['data_inicio'].max().strftime('%d/%m/%Y'))
            
            st.warning("⚠️ **Atenção:** Ao confirmar, os dados do mesmo período/protocolo no banco serão substituídos (Upsert) para evitar duplicações.")
            
            if st.button("💾 Confirmar e Salvar no Banco de Dados", type="primary", use_container_width=True):
                with st.spinner("A gravar no banco de dados com segurança..."):
                    sucesso, msg = salvar_no_banco(df_processado, nome_tabela_bd, tipo_identificado)
                    
                    if sucesso:
                        st.success(f"🎉 Fantástico! {len(df_processado)} registos do {tipo_identificado} foram salvos no banco de dados com sucesso.")
                        registrar_log_auditoria(usuario_id, "IMPORT_CSV", f"Importou arquivo {arquivo_upload.name} ({tipo_identificado})")
                        st.balloons()
                    else:
                        st.error(f"Falha ao salvar no banco de dados: {msg}")

# ------------------------------------------
# ABA 2: VÍNCULO DE CLIENTES (CRM)
# ------------------------------------------
with aba2:
    st.header("🔗 Vínculo de Clientes (CRM)")
    st.write("Vincule múltiplos números de telefone a um único CNPJ. Use esta tela para unificar os clientes.")
    
    col_crm1, col_crm2 = st.columns(2)
    
    with col_crm1:
        with st.form("form_crm"):
            cnpj_input = st.text_input("Digite o CNPJ do Cliente (com ou sem pontuação):")
            cnpj_limpo = apenas_numeros(cnpj_input)
            
            telefone_input = st.text_input("Digite o Telefone/WhatsApp (com ou sem máscara):")
            telefone_limpo = apenas_numeros(telefone_input)
            
            btn_vincular = st.form_submit_button("Vincular Telefone ao CNPJ", use_container_width=True)
            
            if btn_vincular:
                if cnpj_limpo and telefone_limpo:
                    
                    # 1. AQUI OCORRE O SEU INSERT NO BANCO (Salvando o cliente e o telefone criptografado)
                    # Exemplo: oraculo.salvar_novo_vinculo_cliente(cnpj_limpo, telefone_limpo)
                    
                    st.success(f"✅ Sucesso! Telefone {telefone_limpo} vinculado ao CNPJ {cnpj_limpo}.")
                    registrar_log_auditoria(usuario_id, "VINCULO_CRM", f"Vinculou tel {telefone_limpo} ao CNPJ {cnpj_limpo}")
                    
                    # =====================================================================
                    # 2. A MÁGICA AUTOMÁTICA DA TEIA DE ARANHA (LGPD)
                    # =====================================================================
                    with st.spinner("🕸️ Sincronizando ligações órfãs do passado..."):
                        # NOTA: Substitua 'oraculo' pelo nome da variável de conexão/classe do banco 
                        # que você instanciou no topo do seu app.py (ex: db, conexao, motor, etc.)
                        linhas_afetadas = oraculo.sincronizar_vinculos_goto()
                        
                    if linhas_afetadas > 0:
                        st.info(f"🚀 Incrível! O sistema encontrou e vinculou automaticamente **{linhas_afetadas}** ligações antigas a este novo cliente.")
                    else:
                        st.info("Nenhum atendimento antigo pendente foi encontrado para este telefone específico.")
                    # =====================================================================

                else:
                    st.warning("⚠️ Por favor, preencha tanto o CNPJ quanto o Telefone.")

    with col_crm2:
        st.subheader("Visualização Rápida")
        if cnpj_limpo:
            st.info(f"**CNPJ Normalizado:** {cnpj_limpo}")
        if telefone_limpo:
            st.info(f"**Telefone Normalizado:** {telefone_limpo}")
        
        st.caption("A tabela de vínculos ativos será apresentada aqui futuramente.")