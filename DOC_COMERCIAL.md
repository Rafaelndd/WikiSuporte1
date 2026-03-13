# WikiSuporte — Documentação Comercial

## O problema que o mercado sente

Equipes de suporte e implantação lidam diariamente com:

- **Dados espalhados** — chamados no helpdesk, ligações no GoTo, chats no Multi360, tickets internos, sem visão única.
- **Perda de contexto** — histórico de releases e retrabalho de homologação mal registrado, dificultando medir qualidade real.
- **Tempo perdido** — busca manual em PDFs, wikis e planilhas; pouca reutilização de conhecimento.
- **Gestão às cegas** — poucos indicadores confiáveis por analista, por cliente e por tipo de demanda.

## A solução WikiSuporte

O **WikiSuporte** centraliza operação e conhecimento em uma **plataforma web única**:

- **Dashboards** de atendimentos (GoTo/Multi360), chamados Tecnuv, tickets EPSY e gestão.
- **Importação** de relatórios com vínculo progressivo de clientes (CNPJ / telefone).
- **Homologação de releases** com ciclos auditáveis (aprovado / reprovado) e métricas de retrabalho.
- **Classificação inteligente** de chamados (Erro, Melhoria, Adequação Fiscal) para priorização e relatórios.
- **Base de conhecimento + busca semântica** (RAG) sobre manuais e wikis, reduzindo tempo de resposta.
- **Automação opcional** (bots) para sincronizar helpdesk sem sobrecarregar o servidor da Tecnuv.

## Proposta de valor

| Benefício | Impacto |
|-----------|---------|
| Menos tempo em busca de informação | Menos minutos por atendimento |
| Visão por cliente e por analista | Melhor alocação e SLA |
| Métricas de homologação | Decisões baseadas em dados, não em achismo |
| Conhecimento reutilizável | Menos retrabalho e treino mais rápido |
| Um só lugar para operar | Menos ferramentas, menos erro humano |

## ROI esperado (ordem de grandeza)

- **Produtividade:** economia de **5–15 minutos por atendimento** quando o analista encontra resposta na base ou no dashboard em vez de caçar em vários sistemas.
- **Gestão:** redução de reuniões de “achismo” ao substituir por **indicadores** (filas, aging, categorias IA, retrabalho de release).
- **Qualidade:** visibilidade de **reprovações por release/módulo** direciona melhoria contínua no relacionamento com desenvolvimento.

*(Valores exatos dependem do volume de chamados e da maturidade do cadastro de clientes.)*

## Público-alvo ideal

- **Coordenação e supervisão** de suporte / implantação.
- **Analistas** que abrem chamados, atendem telefone/chat e registram conhecimento.
- **Gestão** que precisa de indicadores consolidados e rastreabilidade de releases.

## Diferenciais competitivos

1. **Feito para o ecossistema Tecnuv + EPSY** (helpdesk, plantões, tickets).
2. **LGPD-aware** no tratamento de telefones e cadastro de clientes.
3. **Extensível** — PostgreSQL + pgvector + IA configurável (Gemini).
4. **Operação híbrida** — uso manual intensivo + bots quando desejado.

---

**Contato / evolução:** evoluir módulos sem perder o histórico no banco; roadmap alinhado a novos relatórios e integrações.
