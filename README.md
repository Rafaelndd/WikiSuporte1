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

## Backup e continuidade (DR)

O projeto já possui backup automatizado em:

- `scripts/03_create_backup.ps1`

Use o plano completo de recuperacao em:

- `SECURITY_BACKUP_PLAN.md`

O inventario de pastas e arquivos criticos para troca de servidor esta em:

- `scripts/recovery_portability_manifest.json`

## Script único de estrutura do banco

Para criação/cópia de ambiente (esquema + migrações atuais):

- `database/wikisuporte_schema_full_ddl.sql`

Este arquivo já contém **todo o DDL consolidado** (estrutura base + migrations atuais + extensão
`pgvector`) em um único SQL físico, sem dependência de `\i`.

Fluxo sugerido:

1. Criar banco vazio `wikisuporte` (ou nome próprio).
2. Conectar no banco criado.
3. Executar: `psql -U <usuario> -d wikisuporte -f database/wikisuporte_schema_full_ddl.sql`.

## Aplicação assistida do schema (produção)

Para execução segura com validações prévias, log e rollback controlado:

- `scripts/04_apply_schema_prod.ps1`

Exemplo de uso:

1. Modo padrão (usa `.env` com `DB_*`, cria banco se não existir e aplica o script).
2. Recriar forçadamente em ambiente de homologação:
   `.\scripts\04_apply_schema_prod.ps1 -RecreateIfExists`

## Restore completo de produção (arquivos + banco)

Para recuperar um ambiente de forma operacional (backup zip + dump):

- `scripts/05_restore_wikisuporte.ps1`

Exemplo de uso:

1. Restaurar apenas arquivos:  
   `.\scripts\05_restore_wikisuporte.ps1 -BackupPath .\backups\WikiSuporte_Backup_YYYYMMDD_HHMM.zip -SkipDatabaseRestore`
2. Restore completo com banco novo:
   `.\scripts\05_restore_wikisuporte.ps1 -BackupPath .\backups\WikiSuporte_Backup_YYYYMMDD_HHMM.zip -DropExistingDatabase -ForceFileOverwrite -PromptForPassword`
