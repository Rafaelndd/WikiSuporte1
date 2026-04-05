# Release da versão — WikiSuporte

---

## Versão 1.0.23 · 5 de abril de 2026

*Nessa versão foram efetuadas diversas alterações no sistema, tanto nos arquivos fonte (Backend) quanto no visual do sistema (Frontend), esse release tem objetivo de resumir e mostrar as alterações que irão impactar a usabilidade dos usuários finais.*

### Visual, tema e navegação


| Antes                                                                                                                                                    | Agora                                                                                                                                                                                       |
| -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| O aspecto visual de alguns componentes não estavam de acordo com a identidade visual do sistema e as opções de temas claro e escuro apresentavam falhas. | O WikiSuporte usa as **cores e o estilo EPSY** (Wiki em laranja, Suporte em azul), com tema **claro** ou **escuro** — escolha sua na barra lateral, alinhada ao modo do navegador.          |
| Em algumas telas, a **barra lateral** não mostrava bem o botão para **expandir** ou **recolher**, o que atrapalhava em monitores pequenos.               | O botão de **expandir/recolher** a barra lateral voltou a funcionar de forma correta.                                                                                                       |
| Ao clicar em **Sair** e mudar de página, por vezes o sistema **voltava a mostrar sessão iniciada** sem pedir login de novo.                              | O **encerramento de sessão** foi corrigido em **todas as páginas**: ao sair, fica mesmo na área de login. **Sair pela barra lateral** já **não reabre** a sessão sozinha no mesmo instante. |
|                                                                                                                                                          |                                                                                                                                                                                             |


### Quem gerencia usuários e o “Meu perfil”


| Antes                                                                                                                                 | Agora                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A gestão de contas de usuário estava misturada com as **Configurações**, o que tornava mais difícil gerenciar os usuários do sistema. | Quem é **administrador** passa a usar a página **Usuários**: Onde podem **listar**, **criar**, **editar**, marcar **férias** ou **atendimento externo**, e **desativar** contas com confirmação — tudo num lugar dedicado. |
| O Menu Meu Perfil foi criado.                                                                                                         | **Meu perfil** foi **criado**: Nele os usuários podem inserir sua **foto de perfil** , e **troca de senha**. Algo simples mas que irá ser melhorado nas próximas versões.                                                  |


### Home, pontos e ranking


| Antes                                                                                                                                                                            | Agora                                                                                                                                                                                                                                                                                                                               |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Na **área inicial** após login, havia **muitos blocos ao mesmo tempo** (incluindo indicadores como impacto total e ranking de qualidade) e **missões semanais** ocupavam espaço. | A **Home** foi **simplificada**: destaque para **foto de perfil** (maior e centrada), **patente**, barra de experiência, **pontuação atual**, **posição na equipe** e texto de **curtidas** nas estatísticas; **missões semanais** deixaram de aparecer na Home; alguns indicadores antigos foram **retirados** para reduzir ruído. |
| O **tempo até ao próximo registro de ponto** (VR) mostrava segundos o que custava muito para o streamlit reinderizar os segundos constantemente.                                 | A contagem mostra só **horas e minutos** (por exemplo `08:00`).                                                                                                                                                                                                                                                                     |
| O **ranking** de quem mais contribui era somente uma **tabela**, sem destaque visual para os primeiros lugares nem fotos.                                                        | Os **três primeiros** aparecem num **pódio** com **troféus**, **nome**, **patente** e **resumo**; na lista geral, **ícones** indicam quem está de **férias** ou em **atendimento externo**; **foto** ou imagem de substituição quando não há retrato.                                                                               |
| A **saudação**, o **nome** e o **tipo de perfil** repetiam-se na barra lateral na Home, juntamente com o cabeçalho principal.                                                    | Na Home, a **barra lateral** ficou mais **enxuta** (menos repetição de nome e perfil), mantendo o que você precisa para navegar e sair.                                                                                                                                                                                             |


### Contribuições, XP e aprovações


| Antes                                                                                                                   | Agora                                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Aprovar uma contribuição **não ligava** de forma clara à **experiência de pontos** que o usuário vê no dia a dia.       | Ao **aprovar** contribuições, o sistema **registra pontos** de forma alinhada às regras de contribuição (incluindo **bônus** quando aplicável).                                           |
| Não havia um quadro visível para a equipe técnica fechar o ciclo semanal de **ajustes de XP** no painel administrativo. | Existe **interface no painel admin** para o **fechamento semanal** relacionado com XP, quando a sua função o exige.                                                                       |
| Regras de **acompanhamento semanal** para analistas existiam nos bastidores sem ficar tão explícito na experiência.     | **Analistas** podem ser alvo de **ajustes semanais** quando as metas não são cumpridas; quem está em **férias** ou **atendimento externo** fica **isenção** desses ajustes nesse período. |


### Feedback, releases manuais e onde ler as notas


| Antes                                                                                                                        | Agora                                                                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A página de **Feedback** podia mostrar **mensagens técnicas** (arquivos, e-mail interno, configurações) quando algo falhava. | Mensagens de **sucesso** ou **erro** são em **linguagem para usuário final**; detalhes técnicos ficam nos registros internos, não na tela.                                                                                             |
| O **cadastro manual de releases** misturava termos de banco de dados e listagens que assustam quem não é de TI.              | A mesma função foi reescrita em **linguagem do dia a dia**, com **pesquisa** por **versão**, **chamado**, **descrição** e **relevância**; o item mudou de posição no menu lateral (**Releases Tecnuv (manual)** mais abaixo na lista). |
| (Na versão 1.0.1) combinava **aviso no topo** da Home com o menu.                                                            | O histórico **Release da versão** continua acessível pelo **menu lateral** (**Notas de versão**), com comparativos **Como era** / **Como ficou** por versão; a Home foi **descomprimida** no topo para focar no conteúdo principal.    |


---

## Versão 1.0.1 · 4 de abril de 2026

### Sessão e login


| Antes                                                                                                                                       | Agora                                                                                                                                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Ao atualizar a página (F5) ou voltar ao sistema em outro momento, era comum precisar **entrar de novo** com usuário e senha com frequência. | O sistema **reconhece o seu login de forma mais estável** no navegador (sessão guardada de forma segura). Continua a haver **logout automático após inatividade após 50 minutos** por segurança. |


### Onde acompanhar novidades


| Antes                                                                                          | Agora                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Não havia um local único, para saber **o que mudou para os usuários do sistema no dia a dia**. | Existe esta página de **Notas de versão**: resumo direto do que afeta a **sua usabilidade**. Quando houver alterações no sistema, você será notificado. E o documento com as alterações estará acessível pelo **aviso no topo** ou pelo menu lateral. |


---

