*Documento vivo: em cada release, acrescente uma secção nova no topo com versão, data e resumo Antes/Agora.*

---

# Notas de versão — utilizadores

---

## Versão 2.1.0 · 2 de abril de 2026

### Sessão e login

| Antes | Agora |
|--------|--------|
| Ao atualizar a página (F5) ou voltar ao sistema em outro momento, era comum precisar **entrar de novo** com utilizador e senha com frequência. | O sistema **reconhece o seu login de forma mais estável** no navegador (sessão guardada de forma segura, com prazo alargado). Continua a haver **logout automático após inatividade** por segurança. |

### Onde acompanhar novidades

| Antes | Agora |
|--------|--------|
| Não havia um sítio único, em linguagem clara, para saber **o que mudou para quem usa o sistema no dia a dia**. | Existe esta página de **Notas de versão**: resumo direto do que afeta a **sua utilização**. Quando houver alterações, pode abrir o mesmo documento pelo **aviso no topo** ou pelo menu lateral. |

### Segurança e estabilidade (bastidores)

| Antes | Agora |
|--------|--------|
| Ficheiros de ambiente e de registo podiam, por engano, ser tratados como ficheiros normais do projeto. | Reforçámos as regras para que **dados sensíveis e registos** não entrem no controlo de versões — **menos risco** de exposição acidental. |

---

## Versões anteriores

*Ainda não há entradas anteriores neste formato. As próximas versões serão listadas acima.*

---

## Para a equipa técnica (manutenção deste ficheiro)

1. **Editar** este ficheiro: `releases/WIKISUPORTE_NOTAS_DE_VERSAO.md` — adicionar uma nova secção **no topo** com versão, data e tabela Antes/Agora.
2. **Atualizar** `services/release_notes_banner.py`: constantes `RELEASE_NOTES_VERSION`, `RELEASE_NOTES_DATE` e, se necessário, `RELEASE_NOTES_SUMMARY` (texto curto do banner).
3. **Opcional — notificação na base de dados** para todos os perfis (mensagem com link interno ao menu):

```sql
-- Exemplo (ajustar título/mensagem à versão)
INSERT INTO notificacoes_sistema (tipo, titulo, mensagem, autor, target_role)
VALUES (
  'comunicado',
  'WikiSuporte — novidades na versão',
  'Há atualizações que podem afetar a sua rotina. Abra **Notas de versão** no menu lateral (ícone de prancheta) para ver o resumo.',
  'Sistema',
  'todos'
);
```

4. Limpar caches de notificação na sessão se testar localmente (`ws_seen_notifications` / toast duplicado).
