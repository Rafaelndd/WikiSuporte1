---
phase: release-notes-ui-home
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/release_notes_banner.py
  - pages/10_📋_Notas_de_versao.py
  - app.py
  - tests/test_release_notes_ui.py
  - tests/test_release_manager.py
autonomous: true
requirements:
  - RN-UI-01
  - RN-UI-02
  - RN-UI-03
user_setup: []
must_haves:
  truths:
    - "Utilizador autenticado vê o nudge na Home apenas enquanto a janela `notificacao_ate` da última release for válida."
    - "O nudge e a página de notas partilham tokens visuais (Wiki/Suporte, claro/escuro) sem regressão de leitura."
    - "A página de notas continua a listar o catálogo JSON e o Markdown opcional sem alterar o fluxo de login."
  artifacts:
    - path: services/release_notes_banner.py
      provides: "Nudge na Home + eventual CSS compartilhável"
    - path: pages/10_📋_Notas_de_versao.py
      provides: "Hero + histórico + expanders"
  key_links:
    - from: app.py
      to: services/release_notes_banner.render_home_release_nudge
      via: "chamada após sidebar, antes do hero principal"
    - from: services/release_notes_banner
      to: utils.release_manager.release_for_home_banner
      via: "catálogo e janela de notificação"
---

# Plano executável — UI/UX de notas de versão na Home (WikiSuporte)

## Objetivo

Melhorar a **experiência visual e a consistência** do aviso de nova versão na **Home** e o alinhamento com a **página de notas de versão**, reutilizando `releases/releases_catalog.json` como fonte de verdade já integrada a `utils.release_manager` e `services/release_notes_banner`.

**Propósito:** comunicar releases de forma clara, acessível e coerente com os temas Streamlit (claro/escuro), sem aumentar acoplamento nem risco no núcleo de autenticação.

**Saída esperada:** ajustes localizados em módulos de UI de release notes, testes pytest cobrindo lógica exposta e regressão mínima; **nenhuma** alteração em `wiki_authenticator`, cookies ou `stauth` salvo bug de segurança documentado (fora de escopo).

---

## Onde gravar este plano (clone sem `.planning/`)

Sugestão de árvore GSD para este repositório:

- `.planning/PROJECT.md` — visão curta do produto (opcional neste ciclo).
- `.planning/ROADMAP.md` — fases; mapear requisitos `RN-UI-*` abaixo quando formalizar o roadmap.
- `.planning/phases/release-notes-ui-home/release-notes-ui-home-01-PLAN.md` — cópia deste ficheiro.

---

## Escopo

### In scope

- **Home:** `render_home_release_nudge()` — copy, hierarquia, contraste, espaçamento, alinhamento com o hero (cores `#1e5fbf` / `#0d9488` e variantes dark já usadas na página de notas e no `app.py`).
- **Consistência temática:** reutilizar ou centralizar **apenas CSS/markup** partilhado entre nudge e hero de notas (ex.: variáveis ou classe com prefixo `ws-`), sem mudar semântica de `html[data-theme="dark"]`.
- **Catálogo:** garantir que o nudge continua a refletir `release_for_home_banner()` (já testado indiretamente em `test_release_manager.py`); se extrair helpers puramente para teste, manter o mesmo comportamento.
- **Acessibilidade leve:** `role="status"` ou equivalente mantido/melhorado; textos legíveis em ambos os temas.
- **Testes:** pytest alinhado ao padrão do repo (`tests/test_release_manager.py`, `tests/test_streamlit_pages_subprocess.py`).

### Out of scope (explícito)

- **`wiki_authenticator`**, **`stauth`**, gestão de **sessão/cookies**, prazo de sessão, logout — **não alterar**. O nudge já usa apenas `st.session_state.get("autenticado")` como guarda de exibição; isso **permanece**; não introduzir novas chaves de sessão nem mexer no fluxo de login.
- **Refatorações destrutivas** em `app.py` além do necessário para chamar estilos/helpers compartilhados (preferir mudanças em `services/release_notes_banner.py`).
- **Backend/PostgreSQL** para releases (catálogo continua JSON local).
- **E2E Selenium completo** como obrigatório neste plano — ver secção de testes (mínimo viável primeiro).

---

## Dependências

| Dependência | Notas |
|-------------|--------|
| `utils.release_manager` | `release_for_home_banner`, `load_catalog` — já estável e testado. |
| `app.py` | Ordem: sidebar → `render_home_release_nudge()` → hero — manter ordem salvo UX justificar microajuste documentado. |
| `pages/10_📋_Notas_de_versao.py` | Mesmas cores/tipografia que a Home para consistência. |
| Streamlit | `st.page_link` para notas — manter; não substituir por hacks que quebrem multipage. |

---

## Requisitos rastreáveis (para ROADMAP futuro)

| ID | Descrição |
|----|-----------|
| RN-UI-01 | Nudge na Home legível e coerente com identidade Wiki/Suporte em claro e escuro. |
| RN-UI-02 | Comportamento do nudge inalterado quanto a autenticação (só usuário autenticado; sem mudanças em autenticador). |
| RN-UI-03 | Página de notas e nudge visualmente alinhados (tokens ou documentação inline de cores). |

---

## Tarefas (ordem sugerida)

### Tarefa 1 — Consolidar tokens visuais e HTML do nudge

**Ficheiros:** `services/release_notes_banner.py` (principal); opcionalmente constantes compartilhadas no mesmo módulo ou `services/release_notes_styles.py` **somente** se o diff do banner ficar mais legível (pragmatismo: um ficheiro só se `release_notes_banner.py` ultrapassar ~120 linhas com CSS duplicado).

**Ação:**

- Extrair cores e raios de borda do nudge para constantes ou um bloco CSS único documentado (comentário curto: “alinhado a `.ws-notes-hero` / `.ws-home-hero`”).
- Garantir contraste adequado do texto no degradê em **dark** (ajustar `opacity` ou cor de texto se necessário).
- Opcional: incluir um resumo **uma linha** de `rec.como_ficou` truncado (ex.: 120 caracteres) **abaixo** do título do nudge, sem poluir — se considerado excesso, omitir (critério: legibilidade mobile).

**Critérios de aceite:**

- [ ] Nudge visível só com `autenticado` e `release_for_home_banner()` não nulo (comportamento atual preservado).
- [ ] `html[data-theme="dark"]` cobre o nudge como hoje ou melhor (sem texto ilegível).
- [ ] Nenhum import novo de autenticação; nenhuma alteração em `wiki_authenticator` ou equivalente.

**Verificação automatizada:**

```bash
pytest tests/test_release_manager.py -q
```

**Critério “done”:** diff revisado; smoke mental: Home com utilizador autenticado mostra nudge dentro da janela de datas.

---

### Tarefa 2 — Alinhar página de notas ao mesmo sistema de tokens

**Ficheiros:** `pages/10_📋_Notas_de_versao.py`, possivelmente import de constantes/função de CSS de `services/release_notes_banner.py` (se exportar `RELEASE_NOTES_SHARED_STYLE` ou função `inject_release_notes_theme_css()` — **sem** efeitos colaterais Streamlit além de `st.markdown` com CSS).

**Ação:**

- Substituir valores hex duplicados por referência ao mesmo bloco compartilhado **ou** duplicar apenas se a extração acoplar demais (preferir DRY moderado).
- Revisar `st.caption` / subtítulos para tom consistente com o nudge (“Notas de versão”, “último release”).

**Critérios de aceite:**

- [ ] Página continua a redirecionar não autenticados para `app.py` **sem mudança de lógica** (apenas estilo se tocado).
- [ ] Expanders e hero mantêm funcionalidade atual.

**Verificação automatizada:**

```bash
pytest tests/test_streamlit_pages_subprocess.py -q -k "Notas"
```

(ou suíte completa de páginas se o projeto exige)

**Critério “done”:** hero da página de notas e nudge da Home perceptivelmente da mesma “família” visual.

---

### Tarefa 3 — Testes pytest: lógica testável e regressão do banner

**Ficheiros:** `tests/test_release_notes_ui.py` (novo).

**Ação:**

- **Preferência A (mínimo viável, alinhado ao repo atual):** funções puras extraídas em `services/release_notes_banner.py`, por exemplo `format_release_date_br(iso: str) -> str` e/ou `build_home_nudge_html(rec: ReleaseRecord) -> str` **sem** chamar `st.*` — pytest com `ReleaseRecord` fake.
- **Preferência B (se política do projeto exigir AppTest):** um teste `streamlit.testing.AppTest.from_file` num script mínimo que define `st.session_state["autenticado"]=True` e monkeypatch `release_for_home_banner` — **só** se a versão Streamlit do `pyproject.toml`/`requirements` suportar AppTest de forma estável no CI.

**Casos mínimos:**

- Data ISO válida → `dd/mm/aaaa`.
- Data inválida → fallback (string original), espelhando o `try/except` atual.
- HTML gerado contém `versao` e classe `ws-home-release-nudge` (ou sucessor nomeado).

**Critérios de aceite:**

- [ ] `pytest tests/test_release_notes_ui.py -q` passa.
- [ ] Cobertura toca apenas UI helpers; **não** simula login real.

**Verificação automatizada:**

```bash
pytest tests/test_release_notes_ui.py tests/test_release_manager.py -q
```

---

## Riscos e mitigação

| Risco | Mitigação |
|-------|-----------|
| Regressão visual no dark mode | Comparar screenshot manual uma vez (UAT); manter seletores `html[data-theme="dark"]`. |
| Acoplamento excessivo entre página e serviço | Compartilhar só CSS/constants; não mover lógica de catálogo para Streamlit. |
| Tocar sem querer em auth ao editar `app.py` | Restringir edits à área do hero/CSS ou imports de release notes; code review focado. |
| AppTest instável no CI | Preferir funções puras + pytest (Tarefa 3, Preferência A). |

---

## Verificação e UAT

### Automatizada (gate de PR)

```bash
pytest tests/test_release_manager.py tests/test_release_notes_ui.py tests/test_streamlit_pages_subprocess.py -q
```

(Ajustar marcadores `-m` conforme `pytest.ini` do repo, se existir.)

### Manual (UAT — 10 min)

1. Login normal (fluxo existente — **não** alterado pelo plano).
2. Home: com catálogo ativo e data atual ≤ `notificacao_ate`, confirmar nudge + link para notas.
3. Alternar tema claro/escuro nas configurações Streamlit: nudge e página de notas legíveis.
4. Simular expiração (opcional): alterar temporariamente `notificacao_ate` no JSON de **dev** e confirmar desaparecimento do nudge (valida integração com `release_for_home_banner`).

---

## Critérios de sucesso globais

- [ ] RN-UI-01, RN-UI-02, RN-UI-03 atendidos.
- [ ] Nenhum ficheiro de autenticação modificado (`wiki_authenticator`, etc.).
- [ ] Testes novos ou estendidos passam; smoke de páginas continua verde.
- [ ] Documento `releases/WIKISUPORTE_NOTAS_DE_VERSAO.md` pode ser atualizado **opcionalmente** na mesma PR para mencionar “estilo alinhado na Home” (fora do núcleo deste plano técnico).

---

## Pós-entrega (opcional, outra fase)

- E2E Selenium: abrir Home logado e assert de texto “Novo Release” ou classe CSS — apenas se o projeto já tiver harness Selenium reutilizável.
- “Dispensar até próxima versão” com `st.session_state` — **ideia adicional**; só com plano à parte e sem confundir com cookies de login.

---

## Resumo para SUMMARY pós-execução

Após implementar, criar `.planning/phases/release-notes-ui-home/release-notes-ui-home-01-SUMMARY.md` com: ficheiros alterados, screenshots notas (opcional), comandos pytest executados, e confirmação explícita de que auth não foi modificado.
