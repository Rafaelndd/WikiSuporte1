def legenda_indicadores():
    indicadores = {
        "TMA": "Tempo médio entre abertura e finalização do chamado.",
        "TMA por Atendente": "Tempo médio individual de resolução.",
        "Tempo Ocioso": "Tempo entre última interação e encerramento.",
        "Volume Total": "Quantidade total de atendimentos no período.",
        "Volume por Atendente": "Total de chamados por colaborador.",
        "Volume por Hora": "Distribuição de atendimentos ao longo do dia.",
        "Taxa de Finalização": "Percentual de chamados finalizados.",
        "Avaliação Média": "Nota média atribuída pelos clientes.",
        "Avaliações Positivas": "Percentual de notas altas recebidas.",
        "Correlação TMA x Avaliação": "Relação entre tempo de atendimento e satisfação.",
        "Distribuição por Origem": "Volume de atendimentos por canal.",
        "TMA por Origem": "Tempo médio de atendimento por canal.",
        "Volume por Departamento": "Quantidade de chamados por área.",
        "Motivos Top 10": "Principais causas de abertura de chamados.",
        "Score de Performance": "Índice composto de desempenho individual.",
        "SLA": "Percentual de chamados dentro do tempo máximo definido.",
        "Encerramentos Fora do Horário": "Chamados finalizados após horário comercial.",
        "Atendimentos Fim de Semana": "Chamados iniciados sábado ou domingo.",
        "Tempo por Dia da Semana": "Tempo médio de atendimento por dia."
    }

    return indicadores


# Exemplo para Streamlit
# import streamlit as st
# st.write(legenda_indicadores())