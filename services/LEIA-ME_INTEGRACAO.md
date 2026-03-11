# Onde inserir as chamadas aos novos serviços (arquivos originais)

**Regra:** Nenhum arquivo original foi alterado. Abaixo estão os pontos exatos onde você pode inserir as **chamadas mínimas** para integrar as funções.

---

## 1. `services/ticket_classifier.py` (Classificação e SLA)

### 1.1 Classificar chamados ao raspar (Oráculo / Motor)

- **Arquivo:** `modules/OraculoLogistica.py` (ou onde os chamados são inseridos/atualizados após o parse).
- **Local sugerido:** Logo após o `INSERT` ou `UPDATE` de um registro em `chamados_tecnuv` (por exemplo, após o bloco que grava um chamado vindo da raspagem).
- **Chamada mínima:**
```python
# No topo do arquivo (com as demais importações):
# from services.ticket_classifier import classificar_chamado

# Após persistir o chamado (ex.: depois de conn.execute(..., nr_chamado=..., assunto_html=..., motivo_abertura_html=...)):
# try:
#     from services.ticket_classifier import classificar_chamado
#     classificar_chamado(nr_chamado, assunto_html, motivo_abertura_html)
# except Exception:
#     pass
```

- **Alternativa em lote (execução periódica):** Em um cron ou script agendado, chamar:
```python
from services.ticket_classifier import classificar_chamados_pendentes, obter_alertas_sla
classificar_chamados_pendentes(500)
alertas = obter_alertas_sla()
# Exibir alertas no Dashboard Gestão ou enviar por e-mail
```

### 1.2 Exibir alertas de SLA no painel

- **Arquivo:** `pages/9_📊_DashboardGestao.py` (ou `pages/3_📊_Dashboard_Chamados.py`).
- **Local sugerido:** No início do corpo da página, após os filtros, em uma seção "Alertas SLA".
- **Chamada mínima:**
```python
# from services.ticket_classifier import obter_alertas_sla, resumo_alertas_sla
# alertas = obter_alertas_sla()
# resumo = resumo_alertas_sla()
# Exibir st.metric / st.dataframe com alertas e resumo
```

---

## 2. `services/collaboration_guard.py` (Alertas e anti-duplicidade)

### 2.1 Alerta diário de analistas sem contribuição

- **Arquivo:** `app.py` (home do usuário) ou `pages/9_📊_DashboardGestao.py`.
- **Local sugerido:** Na função que monta os alertas do usuário (ex.: perto de `obter_alertas_usuario`) ou em um bloco que só coordenação/dev vê.
- **Chamada mínima:**
```python
# from services.collaboration_guard import obter_alertas_colaboracao_diarios
# msgs = obter_alertas_colaboracao_diarios(30)
# for m in msgs:
#     st.warning(m)  # ou enviar por e-mail
```

### 2.2 Anti-duplicidade ao aprovar contribuição

- **Arquivo:** `pages/6_🤝_Contribuicoes_Suporte.py`.
- **Local sugerido:** Na aba "Fila de Avaliação", **antes** de executar o `UPDATE base_conhecimento SET status = 'APROVADO'` (ou ao exibir o formulário de aprovação).
- **Chamada mínima:**
```python
# from services.collaboration_guard import deve_alertar_duplicidade_ao_aprovar, verificar_duplicidade_tema, excluir_ou_substituir_antigo
# alerta, duplicados = deve_alertar_duplicidade_ao_aprovar(titulo, categoria, id_atual)
# if alerta:
#     st.warning("Já existe tema similar aprovado: " + str(duplicados))
#     if st.button("Excluir antigo e aprovar este"):
#         excluir_ou_substituir_antigo(duplicados[0]["id"], "excluir")
#         # em seguida executar o UPDATE de aprovação do registro atual
```

---

## 3. `services/email_monitor.py` (Cobranças Rodrigo/Jairo)

- **Arquivo:** Nenhum arquivo da aplicação Streamlit precisa ser alterado.
- **Uso:** Executar como **job agendado** (cron, Task Scheduler ou Celery), por exemplo 1x ao dia:
```bash
# Exemplo (na raiz do projeto):
# python -c "from services.email_monitor import executar_monitor_cobrancas; print(executar_monitor_cobrancas())"
```
- **Variáveis de ambiente:** No `.env`, configurar:
  - `EMAIL_SUPORTE_HOST`, `EMAIL_SUPORTE_USER`, `EMAIL_SUPORTE_PASS`, `EMAIL_SUPORTE_FOLDER` (opcional, default INBOX).

---

## 4. `services/vector_db.py` (Banco vetorial para Gemini)

### 4.1 Criar extensão e tabela (uma vez)

- Executar no PostgreSQL ou via script:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
- Ou em Python (uma vez):
```python
from services.vector_db import criar_extensao_e_tabela
criar_extensao_e_tabela()
```

### 4.2 Indexar base de conhecimento (periódico ou após importação)

- **Arquivo:** Pode ser chamado após a raspagem de Manuais/Wikis (ex.: no final de `motor_extracao.py` ou em job agendado).
- **Chamada mínima:**
```python
# from services.vector_db import indexar_base_conhecimento
# indexar_base_conhecimento(origens=['WIKI_HELPDESK', 'MANUAL_HELPDESK'])
```

### 4.3 Usar busca vetorial no Assistente (RAG)

- **Arquivo:** `pages/6_🤝_Contribuicoes_Suporte.py`, na aba do Assistente Virtual, onde hoje é montado o contexto com `query_rag` (SELECT ... FROM base_conhecimento WHERE ... LIKE).
- **Local sugerido:** Substituir ou complementar a query de contexto com:
```python
# from services.vector_db import montar_contexto_rag, buscar_similares
# texto_contexto = montar_contexto_rag(pergunta, top_k=5, origens=['WIKI_HELPDESK', 'MANUAL_HELPDESK'])
# Se texto_contexto vazio, manter fallback atual (LIKE).
# Enviar texto_contexto ao Gemini no prompt.
```

---

## 5. Painel Atendimentos Diários

- **Arquivo:** Nenhuma alteração necessária nos originais.
- **Página criada:** `pages/10_📅_Atendimentos_Diarios.py`. O Streamlit descobre automaticamente as páginas em `pages/`. O link "Atendimentos Diários" aparecerá no menu lateral.
- Se preferir o nome de arquivo exato `daily_attendance.py`, renomeie para `pages/10_📅_daily_attendance.py` (ou crie um alias) para manter a ordenação no menu.

---

## Resumo dos arquivos originais a tocar (opcional)

| Arquivo original | O que inserir |
|------------------|----------------|
| `modules/OraculoLogistica.py` | Após gravar chamado: `classificar_chamado(nr, assunto_html, motivo_abertura_html)` |
| `pages/9_📊_DashboardGestao.py` | Bloco de alertas SLA (`obter_alertas_sla`) e/ou alertas de colaboração (`obter_alertas_colaboracao_diarios`) |
| `pages/6_🤝_Contribuicoes_Suporte.py` | Na Fila de Avaliação: `deve_alertar_duplicidade_ao_aprovar` antes de aprovar; no Assistente: `montar_contexto_rag` para contexto RAG |
| `app.py` | Opcional: alertas de colaboração na home |
| `motor_extracao.py` | Opcional: ao final da extração, `indexar_base_conhecimento()` |
| Nenhum (job externo) | `email_monitor.executar_monitor_cobrancas()` e, se desejar, `ticket_classifier.classificar_chamados_pendentes()` |
