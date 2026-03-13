# WikiSuporte — Manual do Usuário

Guia simples para começar a usar o sistema no dia a dia.

---

## 1. Como acessar

1. Abra o endereço do WikiSuporte no navegador (ex.: `http://localhost:8501` ou o link que a empresa fornecer).
2. Na tela de **login**, digite seu **usuário** e **senha** (os mesmos cadastrados pelo coordenador ou desenvolvimento).
3. Clique em **Entrar**. Se aparecer mensagem de sucesso, em instantes você verá a **página inicial**.

**Não consegui entrar?** Confira usuário e senha; se persistir, fale com quem administra o cadastro (Configurações → Usuários).

---

## 2. Navegação na tela

### Barra lateral (esquerda)

- Mostra seu **nome** e **perfil** (tipo de acesso).
- **Ajuda rápida** — dicas e perguntas frequentes.
- **Sair** — encerra sua sessão com segurança.

### Menu superior (páginas)

Após o login, no **topo** aparecem as **páginas** do sistema (ícones e nomes). Exemplos:

- Dashboard de atendimentos  
- Importação de dados  
- Dashboard de chamados  
- Configurações (geralmente só coordenação/desenvolvimento)  
- Releases manuais, tickets, contribuições, etc.

Clique no nome da página para abrir. A área **central** é onde você preenche formulários, vê gráficos e tabelas.

---

## 3. O que você pode fazer (passo a passo)

### 3.1 Página inicial (Home)

- Veja **saudação**, **clima** (se disponível) e **alertas** do dia (ex.: plantão, validações pendentes).
- Leia os avisos em destaque; eles ajudam a não esquecer tarefas importantes.

### 3.2 Importar relatórios (GoTo / Multi360)

1. Abra **Importação de dados**.
2. Escolha a aba correta (API GoTo ou **upload** de arquivo).
3. Se for arquivo: selecione o **CSV/XLSX** e aguarde o processamento.
4. Se o sistema pedir **cadastro de cliente** para números sem vínculo, preencha **razão social** (e CNPJ se tiver) — isso melhora os dashboards depois.
5. Clique em **Salvar** para gravar no banco.

*Dica:* use o expander **“Como usar?”** na própria tela, se existir.

### 3.3 Ver chamados e métricas

1. Abra **Dashboard de chamados**.
2. Ajuste **período**, **analista** e **status** (abertos / encerrados) no topo.
3. Navegue pelas **abas**: visão geral, tempos de espera, detalhes por versão, performance, homologação.
4. Na aba de **versões**, você pode **filtrar por categoria** (Erro, Melhoria, Adequação Fiscal) quando o sistema já tiver classificado os chamados.

### 3.4 Releases e homologação

1. Abra **Releases Tecnuv (manual)** (ou nome parecido).
2. Envie o arquivo da release e informe a **versão**; o sistema cria os ciclos de teste.
3. Na **auditoria**, altere status para **Aprovado** ou **Reprovado**; se reprovar, preencha o **motivo**.

### 3.5 Configurações (coordenação)

- **Bots:** ligue o motor em segundo plano (conforme orientação da TI) e use os botões de raspagem com moderação.
- **Clientes e telefones:** cadastre CNPJ, razão social e números para cruzar com GoTo/Multi360.
- **Usuários:** criação e perfis (respeitando as regras do perfil desenvolvedor).

---

## 4. Perguntas frequentes (FAQ)

**P: Preciso instalar algo no meu PC?**  
R: Não. Só o navegador. Quem mantém o servidor cuida do Python e do banco.

**P: Os bots substituem o trabalho manual?**  
R: Eles **ajudam** a atualizar dados do helpdesk; decisões e homologação continuam com a equipe.

**P: Por que alguns clientes aparecem como “sem vínculo”?**  
R: Ainda não cadastramos aquele telefone. Cadastre em Configurações ou na importação quando o sistema pedir.

**P: O que é “Categoria (IA)”?**  
R: É uma sugestão automática (Erro / Melhoria / Adequação Fiscal) baseada no texto do chamado; use como apoio, não como verdade absoluta.

**P: Esqueci a senha.**  
R: Peça ao administrador para redefinir em **Configurações → Usuários**.

**P: O sistema ficou lento.**  
R: Filtros muito amplos (muitos meses) carregam mais dados. Reduza o período ou fale com a TI.

---

Para detalhes técnicos, desenvolvedores usam **DOC_TECNICA.md**. Para argumentação de negócio, **DOC_COMERCIAL.md**.
