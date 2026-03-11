# Documentação Comercial — WikiSuporte1 (Business Value)

**Público:** Gestores da EPSY Sistemas  
**Foco:** Produtividade, retenção de talentos, compliance e diferencial competitivo.

---

## 1. Ecossistema de Conhecimento: a “Wikipedia da Empresa”

O WikiSuporte centraliza procedimentos, manuais do PostoGestor e dicas de suporte em uma **base única de conhecimento**. Wikis e manuais do helpdesk são sincronizados automaticamente para o sistema; analistas e coordenadores ainda podem contribuir com novas entradas, que passam por aprovação e entram na base.

**Impacto no tempo médio de atendimento (TMA):**

- **Antes:** Respostas dependiam de memória individual, e-mails internos ou busca manual em pastas e portais.
- **Depois:** Consulta rápida na base (por texto ou, para perfis com acesso, via assistente com IA) reduz o tempo para encontrar o procedimento correto e padroniza a qualidade da informação repassada ao cliente.

A “Wikipedia da Empresa” reduz retrabalho, erros por informação desatualizada e tempo de resolução, contribuindo diretamente para a produtividade da equipe e a satisfação do cliente.

---

## 2. Engajamento via Gamificação

O sistema de **gamificação** incentiva contribuições de qualidade e documentação contínua:

- **XP (experiência):** Pontos obtidos por contribuições aprovadas na base de conhecimento. Há bônus por **agilidade** (registro em até 7, 14 ou 21 dias após o fato) e por **qualidade** (cada upvote recebido soma pontos).
- **Medalhas e patentes:** Hierarquia de títulos (de “Estagiário” a “Expert”) conforme o XP acumulado, tornando o progresso visível e reconhecido.
- **Ranking:** Ordenação por XP e medalha na interface (ex.: aba “Início & Ranking” em Contribuições), criando referência de desempenho e competição saudável.

O impacto psicológico é duplo: **retenção** (o analista vê valor no uso contínuo da ferramenta e no seu crescimento dentro dela) e **qualidade** (upvotes e aprovação incentivam documentação clara e útil, não apenas volume). Premiações por medalhas e ranking reforçam a cultura de compartilhar conhecimento e melhoram a base para toda a equipe.

---

## 3. Mitigação de Riscos (Compliance)

O WikiSuporte incorpora controles que ajudam a proteger dados e cumprir prazos:

- **Logs de auditoria:**  
  - Alterações na tabela de **usuários** (incluindo perfil e dados cadastrais) são registradas em `log_auditoria_usuarios`, **sem gravar senhas**.  
  - Ações na aplicação (login, aceite de termos, acesso a abas sensíveis) são registradas em `logs_auditoria_sistema`.  
  - Dados antigos e novos de tabelas podem ser auditados via `logs_auditoria_dados_tabelas` (JSONB), permitindo rastrear quem alterou o quê e quando.

- **Monitoramento de SLA:** Os dashboards (Atendimentos, Chamados, Tickets) permitem acompanhar volume por analista, tempo de resolução e indicadores de prazo (ex.: percentual “No Prazo Ideal (SLA)” para atendimentos). Isso apoia o cumprimento de compromissos com clientes e a identificação rápida de gargalos.

Em conjunto, auditoria e SLA apoiam a **proteção dos dados** e o **cumprimento de prazos**, alinhados a boas práticas de governança e compliance.

---

## 4. Inteligência Artificial Aplicada

O uso da **API do Gemini** no WikiSuporte traz um diferencial competitivo para a operação:

- **Consultas rápidas em manuais e base de conhecimento:** O assistente virtual (disponível para perfis coordenador e dev) usa a pergunta do usuário para buscar trechos relevantes na base (wikis e manuais sincronizados do helpdesk, além de contribuições aprovadas) e monta um contexto que o Gemini usa para gerar uma resposta direta. Isso acelera a resolução de dúvidas sem que o analista precise ler vários documentos.
- **Histórico de tickets e chamados:** O sistema mantém histórico de chamados e tickets; a evolução para uso de IA (incluindo, no futuro, banco vetorial e chunking) permitirá consultas semânticas sobre casos passados, facilitando “como resolvemos isso antes?” e padronização de soluções.

A IA aplicada reduz tempo de pesquisa, melhora a consistência das respostas e posiciona a EPSY Sistemas com uma ferramenta interna moderna e orientada a resultados.

---

*Documento voltado à gestão da EPSY Sistemas. Para detalhes técnicos (tabelas, pipeline, perfis, RAG), consultar a Documentação Técnica (DOCUMENTACAO_TECNICA_WIKISUPORTE.md).*
