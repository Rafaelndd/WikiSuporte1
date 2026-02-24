import streamlit as st
import re
import pandas as pd

# Função para normalizar dados digitados pelo usuário
def apenas_numeros(texto):
    return re.sub(r'\D', '', str(texto))

def tela_vinculacao_crm():
    st.header("🔗 Vínculo de Clientes (CRM)")
    st.write("Vincule múltiplos números de telefone a um único CNPJ. Use esta tela para unificar os clientes.")
    
    # Layout em colunas
    col1, col2 = st.columns(2)
    
    with col1:
        # 1. Campo para o CNPJ
        cnpj_input = st.text_input("Digite o CNPJ do Cliente (com ou sem pontuação):")
        cnpj_limpo = apenas_numeros(cnpj_input)
        
        # 2. Campo para o Telefone
        telefone_input = st.text_input("Digite o Telefone/WhatsApp (com ou sem máscara):")
        telefone_limpo = apenas_numeros(telefone_input)
        
        # 3. Botão de Salvar
        if st.button("Vincular Telefone ao CNPJ", type="primary", use_container_width=True):
            if cnpj_limpo and telefone_limpo:
                # Aqui você fará o INSERT no SQLAlchemy (tabela clientes_telefones)
                # Exemplo: 
                # novo_vinculo = ClienteTelefone(cnpj=cnpj_limpo, telefone=telefone_limpo)
                # session.add(novo_vinculo); session.commit()
                st.success(f"✅ Sucesso! Telefone {telefone_limpo} vinculado ao CNPJ {cnpj_limpo}.")
            else:
                st.warning("⚠️ Por favor, preencha tanto o CNPJ quanto o Telefone.")

    with col2:
        st.subheader("Visualização Rápida")
        if cnpj_limpo:
            st.info(f"**CNPJ Normalizado (Banco de Dados):** {cnpj_limpo}")
        if telefone_limpo:
            st.info(f"**Telefone Normalizado (Banco de Dados):** {telefone_limpo}")
            
        # Abaixo você pode carregar um DataFrame do banco para mostrar os números já vinculados
        # df_vinculos = pd.read_sql(f"SELECT telefone FROM clientes_telefones WHERE cnpj = '{cnpj_limpo}'", con)
        # st.dataframe(df_vinculos, width='stretch')