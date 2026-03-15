# Migração Streamlit → NiceGUI — WikiSuporte

## Resumo da estrutura de arquivos NiceGUI

| Arquivo / Pasta | Função |
|-----------------|--------|
| `main_nicegui.py` | Entrada da aplicação: `ui.run()`, rotas `@ui.page`, login e Home implementados; demais páginas com placeholder. |
| `wiki_nicegui/state.py` | Estado de sessão (equivalente a `st.session_state`): autenticado, usuario_id, perfil, notificacoes_lidas. Usa `app.storage.user`. |
| `wiki_nicegui/layout.py` | Layout profissional: `build_header()`, `build_drawer()` (menu lateral com links). Substitui sidebar + navegação por páginas. |
| `wiki_nicegui/auth.py` | `verificar_login()` — mesma lógica e query PostgreSQL (crypt) do `app.py`. |
| `wiki_nicegui/data_home.py` | Dados da Home: `obter_alertas_usuario()`, `obter_kpis_home()` — mesmas queries do `app.py`, sem `@st.cache_data`. |
| `wiki_nicegui/pages/` | (Opcional) Módulos por página para manter o `main_nicegui.py` enxuto; hoje o conteúdo das rotas está em `main_nicegui.py`. |

O banco de dados, configuração e serviços continuam no projeto pai (WikiSuporte1): `config.py`, `modules/database.py`, `modules/auditoria.py`, `services/*`, etc. **Nenhuma query ou regra de negócio foi alterada**; apenas a camada de UI foi trocada de Streamlit para NiceGUI.

---

## Principais diferenças implementadas

### 1. Roteamento e layout
- **Streamlit:** `st.set_page_config` + multipage (arquivos em `pages/`) + `st.sidebar` + `st.switch_page("app.py")`.
- **NiceGUI:** Uma única aplicação com `@ui.page("/")`, `@ui.page("/dashboard-chamados")`, etc. Layout com `ui.header()` e `ui.left_drawer()` (menu lateral). Navegação via `ui.link(label, path)` ou `ui.navigate.to(path)`.

### 2. Sessão / estado
- **Streamlit:** `st.session_state['autenticado']`, `st.session_state['usuario_id']`, etc.
- **NiceGUI:** `app.storage.user` (por sessão do navegador). O módulo `wiki_nicegui/state.py` centraliza get/set (`is_authenticated()`, `get_usuario_id()`, `set_login()`, `logout()`).

### 3. Reatividade
- **Streamlit:** Script reexecuta a cada interação; `st.rerun()` recarrega a página.
- **NiceGUI:** Interface não recarrega inteira; atualizar apenas o que mudou. Onde for necessário:
  - Use **bindings**: ex. `ui.label().bind_text_from(obj, 'nome')`.
  - Use **`@ui.refreshable`** em blocos que devem ser redesenhados (ex. tabela após filtrar).
  - Evite `ui.navigate.reload()` exceto após login/logout.

### 4. Tabelas de dados
- **Streamlit:** `st.dataframe`, `st.table`.
- **NiceGUI:** Use `ui.aggrid()` com `rows=lista_de_dict` ou `ui.table()` com colunas definidas. Para paginação, use as opções nativas do aggrid ou uma lista reativa que você atualiza e passa de novo para o componente.

### 5. Formulários e botões
- **Streamlit:** `st.form`, `st.form_submit_button`, `st.text_input`, etc.
- **NiceGUI:** `ui.input()`, `ui.button()`, `ui.select()`, etc., com `on_click` ou bindings. Não há “submit” único; a lógica é chamada no `on_click` do botão (ex. “Entrar” no login).

### 6. Gráficos
- **Streamlit:** `st.plotly_chart(fig)` com Plotly.
- **NiceGUI:** Pode usar `ui.echart()` com o JSON do ECharts, ou exportar Plotly para HTML e exibir com `ui.html()`, ou usar o componente NiceGUI que encapsula Plotly, se disponível. As queries e a construção dos dados permanecem iguais.

### 7. Conexão com banco e APIs
- **Inalterado:** `modules/database.get_connection()`, `config.Config`, mesmas queries SQL e chamadas a GoTo/ClickUp. Apenas a forma de exibir resultados e disparar ações muda (UI NiceGUI em vez de Streamlit). Chamadas pesadas ou de API devem continuar assíncronas ou em thread para não travar a UI.

### 8. Proteção de rotas
- **Streamlit:** `if not st.session_state.get('autenticado'): st.switch_page("app.py")` no início de cada página.
- **NiceGUI:** Em cada `@ui.page` que exige login, chame algo como `_require_auth(content_fn)`: se `not state.is_authenticated()`, chame `ui.navigate.to("/")` e retorne; caso contrário, renderize o layout + conteúdo.

### 9. Cache
- **Streamlit:** `@st.cache_data(ttl=300)` nas funções de dados.
- **NiceGUI:** Não há decorator global; pode-se usar cache em memória (ex. `functools.lru_cache` ou um dict com TTL) dentro dos módulos de dados, ou simplesmente buscar de novo a cada exibição da página.

---

## Como rodar a aplicação NiceGUI

1. **Ambiente:** Na raiz do projeto WikiSuporte1 (ou com `PYTHONPATH` apontando para ela), com o mesmo `.env` e banco PostgreSQL configurados.
2. **Instalar dependências NiceGUI:**
   ```bash
   pip install -r WikiSuporte2.0/requirements_nicegui.txt
   ```
3. **Executar:**
   ```bash
   cd WikiSuporte2.0
   python main_nicegui.py
   ```
   Ou, a partir da raiz WikiSuporte1:
   ```bash
   python WikiSuporte2.0/main_nicegui.py
   ```
4. Abrir no navegador a URL indicada (ex.: `http://localhost:8080`).

---

## Próximos passos para paridade total

- **Dashboard Atendimentos / Chamados / Tickets EPSY:** Copiar a lógica de filtros e de carregamento de dados das páginas Streamlit correspondentes; exibir tabelas com `ui.aggrid()` e gráficos com `ui.echart()` ou `ui.html(plotly_fig.to_html())`.
- **Importação de Dados:** Manter a mesma lógica de upload e processamento (incl. `processador_csv`, `goto_api`); substituir `st.tabs`, `st.file_uploader` e botões por equivalentes NiceGUI; chamadas à API GoTo em execução assíncrona/em background.
- **Configurações, Registro de Atendimentos, Feedback, Releases, Contribuições:** Aplicar o mesmo padrão: mesma regra de negócio e serviços; apenas trocar widgets Streamlit por componentes NiceGUI e usar `state` + `_require_auth` onde fizer sentido.

Com isso, a migração mantém **100% das funcionalidades, regras de negócio, integrações e consultas ao PostgreSQL**, alterando apenas a camada de interface para NiceGUI.
