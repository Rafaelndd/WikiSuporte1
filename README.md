# WikiSuporte

Sistema **em produção** de suporte e documentação interna, com interface **Streamlit**, backend **Python** e base de dados **PostgreSQL**.

**Repositório:** [github.com/Rafaelndd/WikiSuporte1](https://github.com/Rafaelndd/WikiSuporte1)

[![CI](https://github.com/Rafaelndd/WikiSuporte1/actions/workflows/main.yml/badge.svg)](https://github.com/Rafaelndd/WikiSuporte1/actions/workflows/main.yml)

## Requisitos

- Python 3.12+ (recomendado alinhar com a versão em produção)
- PostgreSQL (instância acessível à aplicação)
- Ficheiro de segredos Streamlit (ver abaixo)

## Instalação rápida (desenvolvimento local)

```bash
git clone https://github.com/Rafaelndd/WikiSuporte1.git
cd WikiSuporte1
python -m venv .venv
```

**Windows (PowerShell):** `.\.venv\Scripts\Activate.ps1`  
**Linux/macOS:** `source .venv/bin/activate`

```bash
pip install -r requirements.txt
```

Configure **`.streamlit/secrets.toml`** (não existe no repositório — copie a partir do modelo interno da equipa). Nunca commite credenciais.

```bash
streamlit run app.py
```

A aplicação abre por omissão em `http://localhost:8501`.

## Qualidade e testes

```bash
pip install -r requirements-dev.txt
python -m pytest --durations=10 -q --junitxml=test-reports/pytest-report.xml
python -m pytest --durations=10 -q --junitxml=test-reports/pytest-report.xml > test-reports/pytest-console.log 2>&1
python scripts/test_health_report.py
ruff check tests
```

## Contribuir e versionamento

Ver **[CONTRIBUTING.md](CONTRIBUTING.md)** (branches, PRs, tags `v*.*.*`, GitHub Actions, deploy manual em produção).

## Changelog e releases

Alterações por versão: **[CHANGELOG.md](CHANGELOG.md)**. Releases assinaladas no GitHub seguem [Semantic Versioning](https://semver.org/lang/pt-BR/).

## Licença e uso

Uso interno da organização. Ajuste esta secção se o projeto tiver licença pública explícita.
