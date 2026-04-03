# Changelog

Todas as alterações notáveis do **WikiSuporte** serão documentadas neste ficheiro.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e o versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado

- Fluxo de CI/CD com GitHub Actions (`pytest`, `ruff` em `tests/`, `pip-audit`, `bandit` HIGH).
- Workflow **Release** em tags `v*.*.*` (revalidação de qualidade; deploy em produção manual ou futuro).
- Documentação de contribuição e versionamento (`CONTRIBUTING.md`).

### Removido

- Integração Docker/GHCR (opcional para uma fase posterior; fluxo simplificado para Git + Actions apenas).

### Corrigido

- Uso de `hashlib.md5(..., usedforsecurity=False)` para identificadores sintéticos não criptográficos (Bandit B324).

<!-- Ao publicar uma release, mova itens de [Unreleased] para uma secção ## [X.Y.Z] com data. -->
