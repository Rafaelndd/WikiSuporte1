# Changelog

Todas as alterações notáveis do **WikiSuporte** serão documentadas neste ficheiro.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e o versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [1.0.0] - 2026-04-03

Primeira release formal com fluxo de qualidade no GitHub e documentação de arranque para quem clona o repositório.

### Adicionado

- **README.md** com visão geral, instalação local e ligações para contribuição e changelog.
- Fluxo de **CI/CD** com GitHub Actions: `pytest`, `ruff check tests`, `pip-audit`, Bandit (severidade **HIGH**).
- Workflow **Release** em tags `v*.*.*` (revalidação antes de considerar deploy).
- **CONTRIBUTING.md** com fluxo Git (branches, PR, tags, produção sem Docker).
- Regras do projeto em **`.cursor/rules/`** para o Cursor (contexto GSD, Python/Streamlit, testes).
- **bandit.yaml**, **ruff.toml** e **requirements-dev.txt** alargado (ferramentas de qualidade).

### Removido

- Integração Docker/GHCR adiada; fluxo assente em **Git + Actions** e deploy manual no servidor.

### Corrigido

- **Bandit B324:** `hashlib.md5(..., usedforsecurity=False)` em identificadores sintéticos em `modules/processador_csv.py`.
- **Ruff I001:** ordenação de imports em `tests/streamlit_page_runner.py`.

<!-- Ao publicar uma release, mova itens de [Unreleased] para uma secção ## [X.Y.Z] com data. -->
