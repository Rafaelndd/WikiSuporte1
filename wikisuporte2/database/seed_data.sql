-- ============================================================
-- WikiSuporte 2.0 — Dados Iniciais (Seed)
-- Execute APÓS init_schema.sql
-- ============================================================

-- ============================================================
-- ROLES PADRÃO
-- ============================================================
INSERT INTO roles (nome, descricao, nivel) VALUES
    ('ceo',      'CEO — visão global irrestrita do sistema',           100),
    ('admin',    'Administrador do sistema',                            90),
    ('gestor',   'Gestor de setor — visão filtrada pelo setor',         50),
    ('analista', 'Analista de suporte / técnico consultor',             20),
    ('viewer',   'Visualizador — somente leitura',                      10)
ON CONFLICT (nome) DO NOTHING;

-- ============================================================
-- SETOR PADRÃO
-- ============================================================
INSERT INTO setores (nome, descricao) VALUES
    ('TI',        'Tecnologia da Informação'),
    ('Suporte',   'Equipe de Suporte Técnico'),
    ('Comercial', 'Equipe Comercial / Técnico Consultor'),
    ('Gestão',    'Diretoria e Gestão')
ON CONFLICT (nome) DO NOTHING;

-- ============================================================
-- PERMISSÕES PADRÃO
-- ============================================================
INSERT INTO permissoes (modulo, acao, descricao) VALUES
    ('tarefas',    'ler',    'Visualizar tarefas'),
    ('tarefas',    'criar',  'Criar tarefas'),
    ('tarefas',    'editar', 'Editar tarefas'),
    ('tarefas',    'deletar','Excluir tarefas'),
    ('crm',        'ler',    'Visualizar clientes e prospecções'),
    ('crm',        'criar',  'Criar clientes e prospecções'),
    ('crm',        'editar', 'Editar clientes e prospecções'),
    ('crm',        'deletar','Excluir clientes e prospecções'),
    ('suporte',    'ler',    'Visualizar atendimentos e chamados'),
    ('suporte',    'criar',  'Registrar atendimentos e chamados'),
    ('suporte',    'editar', 'Editar atendimentos e chamados'),
    ('suporte',    'deletar','Excluir atendimentos e chamados'),
    ('dashboards', 'ler',    'Visualizar dashboards e métricas'),
    ('usuarios',   'ler',    'Listar usuários'),
    ('usuarios',   'criar',  'Criar usuários'),
    ('usuarios',   'editar', 'Editar usuários'),
    ('usuarios',   'deletar','Desativar usuários')
ON CONFLICT DO NOTHING;

-- ============================================================
-- ASSOCIAÇÃO ROLES x PERMISSÕES
-- ============================================================

-- CEO/Admin: todas as permissões
INSERT INTO role_permissoes (role_id, permissao_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissoes p
WHERE r.nome IN ('ceo', 'admin')
ON CONFLICT DO NOTHING;

-- Gestor: ler/criar/editar em tudo exceto deletar usuários
INSERT INTO role_permissoes (role_id, permissao_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissoes p
WHERE r.nome = 'gestor'
  AND NOT (p.modulo = 'usuarios' AND p.acao = 'deletar')
ON CONFLICT DO NOTHING;

-- Analista: ler/criar/editar em tarefas, crm, suporte; ler dashboards
INSERT INTO role_permissoes (role_id, permissao_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissoes p
WHERE r.nome = 'analista'
  AND p.modulo IN ('tarefas', 'crm', 'suporte', 'dashboards')
  AND p.acao IN ('ler', 'criar', 'editar')
ON CONFLICT DO NOTHING;

-- Viewer: somente leitura
INSERT INTO role_permissoes (role_id, permissao_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissoes p
WHERE r.nome = 'viewer'
  AND p.acao = 'ler'
ON CONFLICT DO NOTHING;

-- ============================================================
-- USUÁRIO ADMIN PADRÃO
-- admin@wikisuporte.com / admin123
-- Hash bcrypt gerado com: passlib.hash.bcrypt.hash("admin123")
-- ⚠️  ATENÇÃO: Altere a senha imediatamente após o primeiro login!
--             Execute: UPDATE usuarios SET senha_hash = crypt('nova_senha', gen_salt('bf'))
--                      WHERE email = 'admin@wikisuporte.com';
-- ============================================================
INSERT INTO usuarios (nome, email, senha_hash, role_id, setor_id, ativo)
SELECT
    'Administrador',
    'admin@wikisuporte.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj0/OqcAnX6u',
    r.id,
    s.id,
    TRUE
FROM roles r, setores s
WHERE r.nome = 'admin'
  AND s.nome = 'TI'
ON CONFLICT (email) DO NOTHING;

-- ============================================================
-- ESPAÇO E STATUS CONFIG PADRÃO
-- ============================================================
INSERT INTO espacos (nome, descricao, cor, icone) VALUES
    ('Suporte Técnico', 'Espaço principal da equipe de suporte', '#4F46E5', 'headset'),
    ('CRM / Comercial', 'Espaço do módulo Técnico Consultor',    '#0EA5E9', 'users'),
    ('Gestão Interna',  'Tarefas e projetos internos da equipe', '#10B981', 'briefcase')
ON CONFLICT DO NOTHING;

-- Status do espaço "Suporte Técnico"
INSERT INTO status_config (espaco_id, nome, cor, ordem, tipo)
SELECT e.id, sc.nome, sc.cor, sc.ordem, sc.tipo
FROM espacos e
CROSS JOIN (VALUES
    ('Para Fazer',    '#6B7280', 0, 'nao_iniciado'),
    ('Em Andamento',  '#3B82F6', 1, 'ativo'),
    ('Em Revisão',    '#F59E0B', 2, 'ativo'),
    ('Concluído',     '#10B981', 3, 'concluido'),
    ('Cancelado',     '#EF4444', 4, 'cancelado')
) AS sc(nome, cor, ordem, tipo)
WHERE e.nome = 'Suporte Técnico'
ON CONFLICT DO NOTHING;

-- Status do espaço "CRM / Comercial"
INSERT INTO status_config (espaco_id, nome, cor, ordem, tipo)
SELECT e.id, sc.nome, sc.cor, sc.ordem, sc.tipo
FROM espacos e
CROSS JOIN (VALUES
    ('Prospectando',   '#6B7280', 0, 'nao_iniciado'),
    ('Em Negociação',  '#3B82F6', 1, 'ativo'),
    ('Convertido',     '#10B981', 2, 'concluido'),
    ('Perdido',        '#EF4444', 3, 'cancelado')
) AS sc(nome, cor, ordem, tipo)
WHERE e.nome = 'CRM / Comercial'
ON CONFLICT DO NOTHING;

-- ============================================================
-- PRODUTOS PADRÃO (para revenda)
-- ============================================================
INSERT INTO produtos (nome, descricao, tipo, preco) VALUES
    ('Módulo Fiscal',          'Módulo fiscal do sistema ERP',     'modulo',     1500.00),
    ('Módulo RH',              'Módulo de Recursos Humanos',       'modulo',     1200.00),
    ('Treinamento Básico',     'Treinamento básico do sistema',    'treinamento',  500.00),
    ('Treinamento Avançado',   'Treinamento avançado do sistema',  'treinamento',  900.00),
    ('Consultoria Técnica',    'Hora de consultoria técnica',      'servico',      350.00),
    ('Implantação',            'Serviço de implantação completa',  'servico',     5000.00)
ON CONFLICT DO NOTHING;
