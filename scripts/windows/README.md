# WikiSuporte — serviços Windows (NSSM) e deploy

Objetivo: **Streamlit** e **motor de extração** (`motor_extracao.py`) passam a ser **Serviços Windows** (arranque automático, parar/iniciar sem depender de janela `.bat` aberta), e **atualizações Git** ficam num único script.

## 1. Pré-requisitos

- Repositório já clonado (ex.: `D:\WikiSuporte`), com `venv` e `.streamlit\secrets.toml` no servidor.
- [NSSM](https://nssm.cc/download) (Non-Sucking Service Manager): build **win64**; em produção o executável está em `D:\Tools\nssm-2.24-103-gdee49fc\win64\nssm.exe` (ajuste se o caminho for outro).
- PowerShell **como Administrador** para instalar serviços.

Ajuste **`REPO`** para o caminho real do clone no servidor.

```powershell
$REPO = "D:\WikiSuporte"
$NSSM = "D:\Tools\nssm-2.24-103-gdee49fc\win64\nssm.exe"
```

## 2. Instalar dois serviços (uma vez)

**Importante:** o NSSM costuma **falhar** se a aplicação for só o ficheiro `.cmd`. Use **`cmd.exe`** com **`/c "...\run-....cmd"`** (recomendado pela documentação do NSSM).

### Streamlit (interface)

```powershell
& $NSSM install WikiSuporteStreamlit "C:\Windows\System32\cmd.exe"
& $NSSM set WikiSuporteStreamlit AppParameters "/c `"$REPO\scripts\windows\run-streamlit.cmd`""
& $NSSM set WikiSuporteStreamlit AppDirectory $REPO
& $NSSM set WikiSuporteStreamlit DisplayName "WikiSuporte — Streamlit"
& $NSSM set WikiSuporteStreamlit Description "Streamlit WikiSuporte headless :8502"
& $NSSM set WikiSuporteStreamlit Start SERVICE_AUTO_START
& $NSSM set WikiSuporteStreamlit AppStdout "$REPO\logs\streamlit-service.out.log"
& $NSSM set WikiSuporteStreamlit AppStderr "$REPO\logs\streamlit-service.err.log"
& $NSSM set WikiSuporteStreamlit AppRotateFiles 1
& $NSSM set WikiSuporteStreamlit AppRotateBytes 1048576
```

### Motor / bot (`motor_extracao.py`)

```powershell
& $NSSM install WikiSuporteMotor "C:\Windows\System32\cmd.exe"
& $NSSM set WikiSuporteMotor AppParameters "/c `"$REPO\scripts\windows\run-motor.cmd`""
& $NSSM set WikiSuporteMotor AppDirectory $REPO
& $NSSM set WikiSuporteMotor DisplayName "WikiSuporte — Motor extração"
& $NSSM set WikiSuporteMotor Description "motor_extracao.py"
& $NSSM set WikiSuporteMotor Start SERVICE_AUTO_START
& $NSSM set WikiSuporteMotor AppStdout "$REPO\logs\motor-service.out.log"
& $NSSM set WikiSuporteMotor AppStderr "$REPO\logs\motor-service.err.log"
& $NSSM set WikiSuporteMotor AppRotateFiles 1
& $NSSM set WikiSuporteMotor AppRotateBytes 1048576
```

### Já instalou apontando só para o `.cmd` e o serviço não sobe?

Não precisa reinstalar: ajuste **Application** e **AppParameters** (PowerShell como administrador):

```powershell
$REPO = "D:\WikiSuporte"
$NSSM = "D:\Tools\nssm-2.24-103-gdee49fc\win64\nssm.exe"

& $NSSM set WikiSuporteStreamlit Application "C:\Windows\System32\cmd.exe"
& $NSSM set WikiSuporteStreamlit AppParameters "/c `"$REPO\scripts\windows\run-streamlit.cmd`""

& $NSSM set WikiSuporteMotor Application "C:\Windows\System32\cmd.exe"
& $NSSM set WikiSuporteMotor AppParameters "/c `"$REPO\scripts\windows\run-motor.cmd`""
```

### Testar o Streamlit na consola (sem NSSM)

Tem de estar na pasta do script **ou** usar caminho completo:

```powershell
cd $REPO\scripts\windows
.\run-streamlit.cmd
```

Ou: `cmd /c "$REPO\scripts\windows\run-streamlit.cmd"`

### Arranque e recuperação

```powershell
& $NSSM set WikiSuporteStreamlit AppExit Default Restart
& $NSSM set WikiSuporteStreamlit AppRestartDelay 5000
& $NSSM set WikiSuporteMotor AppExit Default Restart
& $NSSM set WikiSuporteMotor AppRestartDelay 5000

Start-Service WikiSuporteMotor
Start-Service WikiSuporteStreamlit
```

**Ordem:** em muitos cenários faz sentido **Motor** antes de **Streamlit** (se o motor alimenta dados). Ajuste `Start-Service` conforme a vossa dependência.

### Gestão corrente

```powershell
Get-Service WikiSuporteStreamlit, WikiSuporteMotor
Stop-Service WikiSuporteStreamlit, WikiSuporteMotor -Force
Start-Service WikiSuporteMotor, WikiSuporteStreamlit
```

Para remover serviços: `& $NSSM remove WikiSuporteStreamlit confirm` (idem Motor).

## 3. Atualizar a partir do Git (deploy)

Com os serviços NSSM já instalados:

1. **Fechar** processos antigos se ainda usares `init_ws.bat` manualmente (para não haver portas duplicadas).
2. PowerShell **Administrador**, na pasta `scripts\windows`:

```powershell
cd D:\WikiSuporte\scripts\windows
.\deploy.ps1
```

Com **tag** específica:

```powershell
.\deploy.ps1 -GitRef v1.0.1
```

Sem `pip` (só código):

```powershell
.\deploy.ps1 -SkipPip
```

Depois, se usarem Alembic, corram `alembic upgrade head` no `venv` antes ou editem o `deploy.ps1` para incluir esse passo.

## 4. Relação com `init_ws.bat`

- `init_ws.bat` continua válido para **teste manual** ou ambientes sem NSSM.
- Em **produção**, o recomendável é **só serviços NSSM** (ou só `init_ws`, sem misturar os dois em simultâneo na mesma porta).

## 5. Firewall

Confirmar regra de entrada **TCP 8502** se o acesso for de outras máquinas.

## 6. NSSM ajuda, mas estes pontos quebram o login / o browser

O NSSM **não corrige** `.env`, PostgreSQL nem código: só **arranca** o processo. Se o serviço cair ao iniciar ou usar o Python errado, o browser mostra **connection refused** na porta **8502** (igual a “erro de login” na prática).

1. **AppDirectory** no NSSM tem de ser a **raiz do repositório** (a pasta que contém `app.py` e o `.env`), igual ao `$REPO` dos comandos acima.
2. **Logs:** ver `logs\streamlit-service.err.log` e `logs\streamlit-service.out.log` — o traceback real aparece aí (venv em falta, import, DB, etc.).
3. **venv:** o `run-streamlit.cmd` usa `venv\Scripts\python.exe` ou `.venv\Scripts\python.exe`. Se o ambiente virtual tiver outro nome, ajuste o script ou crie `venv` com esse nome.
4. **Não correr dois Streamlit na mesma porta:** pare o serviço antes de `streamlit run` manual (ou use outra porta).
5. **Conta do serviço:** “Local System” lê disco local; se o Postgres só aceita rede por utilizador específico, pode ser preciso definir **Log on** no serviço ou `DB_HOST` acessível a essa conta.

### Erro `ImportError: cannot import name '__version__' from 'urllib3'`

O Streamlit em modo **headless** chama `requests` ao mostrar a URL externa; um `urllib3` errado (ex.: *urllib3-future*) quebra o arranque.

Na raiz do repo, com venv ativo, ou execute:

`scripts\windows\reparar-urllib3-requests.cmd`

Ou manualmente: `pip uninstall -y urllib3-future` e `pip install --force-reinstall "urllib3>=2.2.2,<2.6" "requests>=2.31.0,<3"`.
