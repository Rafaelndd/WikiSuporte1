# Plano de seguranca e continuidade (DR) do WikiSuporte

Objetivo:
Garantir recuperacao rapida do sistema em tres cenarios:
- perda do servidor fisico/VM
- perda da base de dados
- incidente de seguranca com suspeita de adulteracao

## Estrutura de camadas recomendada

1. Camada de backup automatizado
- backup do banco com `pg_dump` via `scripts/03_create_backup.ps1`
- backup dos arquivos de aplicacao e anexos com rotacao diaria
- copia dos backups para local externo (bucket S3, SFTP ou armazenamento em rede)
- checksum/validacao (hash) de cada backup antes de enviar
- prova de restore programada (ex.: 1 vez por mes)

2. Camada de seguranca da base e do servidor
- limitar acesso de rede no PostgreSQL (`pg_hba.conf`, firewall e VPN/ACL)
- senhas fortes + rotacao com periodicidade definida
- acesso de admin com MFA e contas sem compartilhamento
- logs de acesso e alteracao de dados persistidos em local seguro
- atualizacao mensal de sistema operacional, Python e dependencias

3. Camada de restauracao (RTO/RPO)
- RTO alvo inicial: recuperar aplicacao em ate 4 horas
- RPO alvo inicial: perda maxima aceitavel de 24 horas (conforme politica interna)
- testagem de restauracao trimestral obrigatoria em ambiente de homologacao

## Arquivo de portabilidade obrigatorio

Arquivo:
- `scripts/recovery_portability_manifest.json`

Ele descreve o que precisa ser levado para outro servidor:
- pastas criticas
- arquivos essenciais de execucao
- lista de extensoes de arquivos na raiz para backup
- arquivos obrigatorios de configuracao
- itens que podem ser recriados no bootstrap
- passos basicos de retorno

## Itens padrao para migrar o sistema

- Diretorios:
  - `app`
  - `assets`
  - `database`
  - `logs`
  - `mascote`
  - `modules`
  - `pages`
  - `scripts`
  - `services`
  - `utils`
  - `uploads`
  - `uploads_wiki`
  - `.streamlit`
- Arquivos:
  - `.env.example`
  - `requirements.txt`
  - `requirements-dev.txt`
  - `app.py`
  - `config.py`
  - `config_ramais.py`
  - `motor_extracao.py`
  - `menus.py`
  - `cadastro_usuarios.py`
  - `bandit.yaml`
  - `ruff.toml`
  - arquivos de inicializacao e scripts em `scripts/*.ps1`

Observacao importante:
- `.env` e `.streamlit/secrets.toml` NAO devem ficar em repositorio, mas devem existir no novo servidor.
- Nunca versionar credenciais reais, chaves privadas ou backups no Git.

## Procedimento basico de migracao para outro servidor

1. Preparar novo servidor com Ubuntu/Windows Server atualizado e PostgreSQL acessivel.
2. Copiar:
   - conteudo do repositorio
   - pasta `backups` com dump de base mais recente (idealmente fora da VM)
3. Restaurar segredos:
   - criar `.env` a partir de `.env.example`
   - configurar `.streamlit/secrets.toml`
4. Recriar ambiente Python e dependencias:
   - `python -m venv .venv`
   - `pip install -r requirements.txt`
5. Restaurar base:
   - `createdb -U postgres wikisuporte` (se necessario)
   - `psql -U postgres -d wikisuporte < wikisuporte_dump.sql`
6. Rodar `./.venv/Scripts/python.exe -m streamlit run app.py` e validar fluxo principal.
7. Executar script de saúde da aplicacao e checar logs de erro.

## Ajustes sugeridos no projeto (fase inicial)

- Agendar backup automatico diario (fora de pico de uso).
- Habilitar backup com criptografia (ex.: OpenSSL AES-256 ou GPG).
- Guardar senha/sessao de administracao em um gerenciador seguro.
- Habilitar alertas para falhas de backup (email/slack/teams).
- Bloquear escrita direta em diretorios sensiveis por usuario sem necessidade.
- Documentar chave de restauracao e dono do processo (RACI).

## O que fica agora:

- `scripts/recovery_portability_manifest.json` (inventario padrao)
- `scripts/03_create_backup.ps1` (script principal atual de backup)
- `SECURITY_BACKUP_PLAN.md` (guia operacional)
