# Contribuir ao WikiSuporte

Este repositório está **em produção**. O fluxo abaixo evita alterações diretas em `main`, mantém rastreabilidade e liga mudanças a releases semânticas.

## 1. Sincronizar

```bash
git checkout main
git pull origin main
```

## 2. Isolar o trabalho (branch)

Use prefixos claros:

| Prefixo   | Uso            |
|-----------|----------------|
| `feature/` | nova funcionalidade |
| `fix/`     | correção de bug |
| `chore/`   | tooling, CI, docs |

Exemplo:

```bash
git checkout -b feature/implementar-autorefresh
```

## 3. Desenvolver e testar

- Respeite as regras do projeto em `.cursor/rules/` (quando usar o Cursor).
- Instale dependências de desenvolvimento: `pip install -r requirements-dev.txt`
- Execute os testes: `pytest`
- Lint rápido na pasta de testes: `ruff check tests`

## 4. Commits e push

Mensagens no estilo [Conventional Commits](https://www.conventionalcommits.org/) facilitam o changelog:

- `feat: …`, `fix: …`, `chore: …`, `docs: …`, `test: …`

```bash
git add .
git commit -m "feat: adiciona auto-refresh no dashboard"
git push origin feature/implementar-autorefresh
```

## 5. Pull Request

Abra um PR da sua branch para `main` no GitHub. O workflow **CI** (`.github/workflows/main.yml`) executa:

- `pytest`
- `ruff check tests`
- `pip-audit` sobre `requirements.txt`
- `bandit` (apenas achados de severidade **HIGH**)

Só faça **merge** após revisão humana e CI verde.

## 6. Versionamento semântico e releases

- **MAJOR** (v2.0.0): mudanças incompatíveis com versões anteriores.
- **MINOR** (v1.1.0): novas funcionalidades compatíveis com versões anteriores.
- **PATCH** (v1.0.1): correções compatíveis.

Após o merge em `main`:

1. Atualize o `CHANGELOG.md` (secção `[Unreleased]` → nova versão com data).
2. Crie uma tag anotada, por exemplo:

   ```bash
   git checkout main
   git pull origin main
   git tag -a v1.1.0 -m "Release v1.1.0"
   git push origin v1.1.0
   ```

3. No GitHub, use **Releases** para descrever novidades para os utilizadores (pode colar resumo do changelog).
4. O workflow **Release** (`.github/workflows/release.yml`) volta a correr **as mesmas verificações** nessa versão (testes + auditorias). Isto **não** envia o programa sozinho para o servidor — só confirma que a tag está “saudável”.

## 7. Produção sem Docker (caminho simples para começar)

**Sim, podes usar só Git + GitHub Actions.** O versionamento “de verdade” é: **commits**, **tags** (`v1.1.0`) e **Release** no GitHub com texto para quem usa o sistema.

O que o **GitHub Actions** faz hoje no projeto:

| Workflow | Quando corre | O que faz |
|----------|---------------|-----------|
| **CI** (`main.yml`) | PR e push na `main` | Testes, lint em `tests/`, checagens de dependências e segurança (Bandit HIGH). |
| **Release** (`release.yml`) | Quando envias uma **tag** `v*.*.*` | Repete essas verificações na versão etiquetada (garantia extra antes de deploy). |

O que **não** faz automaticamente (e é normal no início): **ligar ao servidor da empresa** e reiniciar o Streamlit. Isso costuma ser tu (ou o administrador), no próprio servidor, com passos simples depois de a `main` estar actualizada e de existir tag:

1. No servidor, na pasta do projeto: `git fetch` e `git checkout v1.1.0` (ou `git pull` na `main`, conforme a vossa política).
2. Se mudou `requirements.txt`: `pip install -r requirements.txt` (no ambiente virtual que já usam).
3. Correr migrações da base de dados se existirem para essa versão.
4. Reiniciar o processo Streamlit (serviço, `screen`, ou o método que já usam).

**Publicação automática para produção** (um “deploy” que o GitHub dispara sozinho) é um passo opcional mais avançado — por exemplo uma Action com SSH para o servidor ou um *webhook*. Não é obrigatório para ter **versionamento profissional**; muitas equipas pequenas fazem deploy manual durante anos.

**Docker** é também opcional: empacota a aplicação noutro formato. Podes ignorar por completo até te sentires à vontade.

## CI e Python

O GitHub Actions usa atualmente **Python 3.12** nos runners Ubuntu. Se a produção usar outra versão (por exemplo 3.14), mantenha `requirements.txt` e testes locais alinhados à versão do servidor; pode ajustar `python-version` nos workflows quando os runners oficiais suportarem a mesma série.

## Segurança

- Nunca commite credenciais; use `.streamlit/secrets.toml` local e variáveis no servidor.
- Confirme que `.gitignore` cobre segredos e dados sensíveis antes de cada PR.
