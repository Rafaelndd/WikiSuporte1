"""
Serviço de registro de atendimentos manuais de suporte.

Objetivos:
- Garantir persistência transacional para múltiplos analistas simultâneos.
- Normalizar relacionamento cliente/contato/telefone.
- Salvar anexos em disco e metadados no banco.
- Disponibilizar consultas com filtros e busca semântica.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from modules.database import get_connection
from services.embedding_service import generate_embedding
from services.vector_db import gerar_embedding_gemini

try:
    from modules.processador_csv import gerar_hash_lgpd
except Exception:
    def gerar_hash_lgpd(texto: str) -> str:  # type: ignore[override]
        return ""


UPLOAD_DIR = "uploads/atendimentos"
CANAIS_PADRAO = ["Chat Multi360", "Via Ligação GoTo", "E-mail", "WhatsApp", "Outros"]
CRITICIDADES = ["Baixa", "Média", "Alta", "Crítica"]
CATEGORIAS_INICIAIS = [
    "Erro PostoGestor",
    "Erro Automação/Bombas",
    "Erro na Conciliação de Cartões(Man/Aut)",
    "Erro no Banco de Dados",
    "Erros em Geral",
    "Atualização / Retorno de versão do sistema",
    "SPED Fiscal",
    "SPED Contribuições",
    "Ajustes/Alterações no Mapa de Pista",
    "Conciliação Geral",
    "TEF",
    "Integrações PostoGestor",
    "Documentos em Contingência",
    "Cartões não Configurados",
    "Criação/Manutenção de Relatórios Personalizados",
    "Gerencial Geral",
    "Atendimento para Caixa em Geral",
    "PDV Móvel",
    "PG Coletor",
    "PG Mobile",
    "Financeiro Geral",
    "Configurações do PostoGestor em Geral",
]


def _num(txt: Optional[str]) -> str:
    return re.sub(r"\D", "", str(txt or ""))


def _emb_to_sql(emb: List[float]) -> str:
    return "[" + ",".join(str(round(x, 8)) for x in emb) + "]"


def _coluna_pk_telefone(conn: Any) -> str:
    """
    Detecta a coluna PK da tabela clientes_telefones.
    Compatível com bases que usam 'id_telefone' ou apenas 'id'.
    """
    try:
        row = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'clientes_telefones'
                  AND column_name IN ('id_telefone', 'id')
                ORDER BY CASE WHEN column_name = 'id_telefone' THEN 0 ELSE 1 END
                LIMIT 1
                """
            )
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass
    return "id"


def ensure_schema() -> None:
    """
    Cria/ajusta tabelas necessárias para registro de atendimentos e normalização mínima.
    Idempotente e seguro para executar em toda carga da página.
    """
    engine = get_connection()
    stmts = [
        # Extensão vetorial (caso disponível no PostgreSQL)
        "CREATE EXTENSION IF NOT EXISTS vector",
        # Normalização mínima de clientes
        "ALTER TABLE IF EXISTS clientes_crm ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE IF EXISTS clientes_telefones ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE IF EXISTS clientes_telefones ADD COLUMN IF NOT EXISTS data_cadastro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE IF EXISTS clientes_vinculados_chamado ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE IF EXISTS clientes_vinculados_chamado ADD COLUMN IF NOT EXISTS id_cliente INTEGER REFERENCES clientes_crm(id_cliente) ON DELETE SET NULL",
        # Tabelas legadas podem não existir em alguns ambientes
        """
        CREATE TABLE IF NOT EXISTS clientes_alias (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER NOT NULL REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
            nome_variacao VARCHAR(255) NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE IF EXISTS clientes_alias ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE",
        """
        CREATE TABLE IF NOT EXISTS clientes_contatos (
            id SERIAL PRIMARY KEY,
            id_cliente INTEGER NOT NULL REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
            nome_contato VARCHAR(255),
            nome_fantasia VARCHAR(255),
            telefone_chave VARCHAR(50),
            email_chave VARCHAR(255),
            observacoes TEXT,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE IF EXISTS clientes_contatos ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE IF EXISTS clientes_contatos ADD COLUMN IF NOT EXISTS id_cliente INTEGER REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE",
        "ALTER TABLE IF EXISTS clientes_contatos ADD COLUMN IF NOT EXISTS nome_contato VARCHAR(255)",
        "ALTER TABLE IF EXISTS clientes_contatos ADD COLUMN IF NOT EXISTS criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
        # Unicidades principais
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_crm_cnpj_not_null ON clientes_crm(cnpj) WHERE cnpj IS NOT NULL AND cnpj <> ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_cliente_telefone ON clientes_telefones(id_cliente, numero) WHERE numero IS NOT NULL AND numero <> ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_alias_cliente_nome ON clientes_alias(cliente_id, lower(nome_variacao))",
        """
        CREATE TABLE IF NOT EXISTS atendimento_categorias (
            id_categoria SERIAL PRIMARY KEY,
            nome_categoria VARCHAR(255) NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_atendimento_categorias_nome_lower ON atendimento_categorias((lower(nome_categoria)))",
        # Registro de atendimento manual
        """
        CREATE TABLE IF NOT EXISTS atendimentos_registrados (
            id_atendimento BIGSERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
            nome_analista VARCHAR(150),
            cliente_id INTEGER NOT NULL REFERENCES clientes_crm(id_cliente) ON DELETE RESTRICT,
            contato_id INTEGER REFERENCES clientes_contatos(id) ON DELETE SET NULL,
            telefone_id INTEGER,
            setor VARCHAR(40) NOT NULL CHECK (setor IN ('Suporte Geral', 'TEF')),
            categoria VARCHAR(255) NOT NULL,
            criticidade VARCHAR(20) NOT NULL CHECK (criticidade IN ('Baixa', 'Média', 'Alta', 'Crítica')),
            canal VARCHAR(100) NOT NULL,
            protocolo VARCHAR(120),
            data_atendimento TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            duracao_min INTEGER,
            motivo TEXT NOT NULL,
            solucao TEXT,
            resolvido BOOLEAN NOT NULL DEFAULT FALSE,
            abriu_chamado BOOLEAN NOT NULL DEFAULT FALSE,
            nr_chamado VARCHAR(50),
            origem_registro VARCHAR(30) NOT NULL DEFAULT 'MANUAL',
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS atendimento_anexos (
            id_anexo BIGSERIAL PRIMARY KEY,
            atendimento_id BIGINT NOT NULL REFERENCES atendimentos_registrados(id_atendimento) ON DELETE CASCADE,
            nome_arquivo VARCHAR(512) NOT NULL,
            caminho_arquivo VARCHAR(1200) NOT NULL,
            mime_type VARCHAR(255),
            tamanho_bytes BIGINT,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS atendimentos_embeddings (
            id BIGSERIAL PRIMARY KEY,
            atendimento_id BIGINT UNIQUE NOT NULL REFERENCES atendimentos_registrados(id_atendimento) ON DELETE CASCADE,
            resumo_busca TEXT NOT NULL,
            embedding vector(768),
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_atendimentos_data ON atendimentos_registrados(data_atendimento)",
        "CREATE INDEX IF NOT EXISTS idx_atendimentos_cliente ON atendimentos_registrados(cliente_id)",
        "CREATE INDEX IF NOT EXISTS idx_atendimentos_usuario ON atendimentos_registrados(usuario_id)",
        "CREATE INDEX IF NOT EXISTS idx_atendimentos_setor ON atendimentos_registrados(setor)",
        "CREATE INDEX IF NOT EXISTS idx_atendimentos_canal ON atendimentos_registrados(canal)",
        "CREATE INDEX IF NOT EXISTS idx_atend_embeddings_vec ON atendimentos_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                # Algumas alterações podem falhar em bases antigas (tipos/constraints);
                # o fluxo principal de registro deve continuar operacional.
                continue
        for nome in CATEGORIAS_INICIAIS:
            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO atendimento_categorias (nome_categoria, ativo)
                        SELECT :nome, TRUE
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM atendimento_categorias
                            WHERE LOWER(TRIM(nome_categoria)) = LOWER(TRIM(:nome))
                        )
                        """
                    ),
                    {"nome": nome.strip()},
                )
            except Exception:
                continue


def listar_categorias_atendimento() -> List[str]:
    engine = get_connection()
    q = text(
        """
        SELECT nome_categoria
        FROM atendimento_categorias
        WHERE ativo = TRUE
        ORDER BY nome_categoria
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(q).fetchall()
        return [str(r[0]).strip() for r in rows if str(r[0] or "").strip()]
    except Exception:
        # Fallback para manter operação caso tabela ainda não exista.
        return list(CATEGORIAS_INICIAIS)


def adicionar_categoria_atendimento(nome_categoria: str, perfil: str) -> Tuple[bool, str]:
    if perfil != "dev":
        return False, "Somente usuários com perfil DEV podem adicionar categorias."
    nome = str(nome_categoria or "").strip()
    if not nome:
        return False, "Informe o nome da categoria."
    engine = get_connection()
    try:
        with engine.begin() as conn:
            existe = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM atendimento_categorias
                    WHERE LOWER(TRIM(nome_categoria)) = LOWER(TRIM(:nome))
                    LIMIT 1
                    """
                ),
                {"nome": nome},
            ).fetchone()
            if existe:
                return False, "Categoria já cadastrada."
            conn.execute(
                text(
                    """
                    INSERT INTO atendimento_categorias (nome_categoria, ativo)
                    VALUES (:nome, TRUE)
                    """
                ),
                {"nome": nome[:255]},
            )
        return True, "Categoria adicionada com sucesso."
    except Exception as e:
        return False, f"Erro ao adicionar categoria: {e}"


def listar_clientes(termo: str = "", limite: int = 30) -> pd.DataFrame:
    engine = get_connection()
    termo_like = f"%{(termo or '').strip()}%"
    q = text(
        """
        SELECT DISTINCT c.id_cliente, c.razao_social, c.cnpj
        FROM clientes_crm c
        LEFT JOIN clientes_alias a ON a.cliente_id = c.id_cliente AND COALESCE(a.ativo, TRUE) = TRUE
        WHERE COALESCE(c.ativo, TRUE) = TRUE
          AND (
            :termo = '' OR
            c.razao_social ILIKE :like OR
            COALESCE(c.cnpj, '') ILIKE :like OR
            COALESCE(a.nome_variacao, '') ILIKE :like
          )
        ORDER BY c.razao_social
        LIMIT :lim
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(q, conn, params={"termo": (termo or "").strip(), "like": termo_like, "lim": limite})


def buscar_correspondencias_cliente(cnpj: str = "", telefone: str = "", limite: int = 8) -> pd.DataFrame:
    """
    Busca exata por CNPJ e/ou telefone e retorna opções para seleção do usuário.
    """
    engine = get_connection()
    cnpj_limpo = _num(cnpj)
    tel_limpo = _num(telefone)
    with engine.connect() as conn:
        if cnpj_limpo and tel_limpo:
            q = text(
                """
                SELECT DISTINCT c.id_cliente, c.razao_social, c.cnpj, t.numero AS telefone, 'CNPJ/Telefone' AS origem_match
                FROM clientes_crm c
                LEFT JOIN clientes_telefones t ON t.id_cliente = c.id_cliente
                WHERE COALESCE(c.ativo, TRUE) = TRUE
                  AND (
                    c.cnpj = :cnpj
                    OR t.numero = :tel
                  )
                ORDER BY c.razao_social
                LIMIT :lim
                """
            )
            return pd.read_sql(q, conn, params={"cnpj": cnpj_limpo, "tel": tel_limpo, "lim": limite})
        if cnpj_limpo:
            q = text(
                """
                SELECT c.id_cliente, c.razao_social, c.cnpj, NULL::VARCHAR AS telefone, 'CNPJ' AS origem_match
                FROM clientes_crm c
                WHERE COALESCE(c.ativo, TRUE) = TRUE
                  AND c.cnpj = :cnpj
                ORDER BY c.razao_social
                LIMIT :lim
                """
            )
            return pd.read_sql(q, conn, params={"cnpj": cnpj_limpo, "lim": limite})
        if tel_limpo:
            q = text(
                """
                SELECT DISTINCT c.id_cliente, c.razao_social, c.cnpj, t.numero AS telefone, 'Telefone' AS origem_match
                FROM clientes_telefones t
                JOIN clientes_crm c ON c.id_cliente = t.id_cliente
                WHERE COALESCE(c.ativo, TRUE) = TRUE
                  AND t.numero = :tel
                ORDER BY c.razao_social
                LIMIT :lim
                """
            )
            return pd.read_sql(q, conn, params={"tel": tel_limpo, "lim": limite})
    return pd.DataFrame(columns=["id_cliente", "razao_social", "cnpj", "telefone", "origem_match"])


def obter_cliente_por_id(id_cliente: int) -> Optional[Dict[str, Any]]:
    engine = get_connection()
    q = text(
        """
        SELECT id_cliente, razao_social, cnpj
        FROM clientes_crm
        WHERE id_cliente = :id AND COALESCE(ativo, TRUE) = TRUE
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(q, {"id": id_cliente}).fetchone()
    if not row:
        return None
    return {"id_cliente": int(row[0]), "razao_social": row[1], "cnpj": row[2]}


def buscar_cliente_por_cnpj(cnpj: str) -> Optional[Dict[str, Any]]:
    cnpj_limpo = _num(cnpj)
    if not cnpj_limpo:
        return None
    engine = get_connection()
    q = text(
        """
        SELECT id_cliente, razao_social, cnpj
        FROM clientes_crm
        WHERE cnpj = :cnpj
          AND COALESCE(ativo, TRUE) = TRUE
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(q, {"cnpj": cnpj_limpo}).fetchone()
    if not row:
        return None
    return {
        "id_cliente": int(row[0]),
        "razao_social": str(row[1] or ""),
        "cnpj": str(row[2] or ""),
    }


def _upsert_contato(conn: Any, id_cliente: int, contato_nome: str, telefone: str, email: str) -> Optional[int]:
    contato_nome = (contato_nome or "").strip()
    telefone = _num(telefone)
    email = (email or "").strip()
    # Alguns fluxos podem enviar telefone no campo de e-mail; corrige automaticamente.
    if email and ("@" not in email):
        email_num = _num(email)
        if email_num and not telefone:
            telefone = email_num
            email = ""
    if not contato_nome and not telefone and not email:
        return None

    row = conn.execute(
        text(
            """
            SELECT id
            FROM clientes_contatos
            WHERE id_cliente = :idc
              AND COALESCE(ativo, TRUE) = TRUE
              AND (
                (:nome <> '' AND LOWER(COALESCE(nome_contato, '')) = LOWER(:nome))
                OR (:tel <> '' AND COALESCE(telefone_chave, '') = :tel)
                OR (:email <> '' AND LOWER(COALESCE(email_chave, '')) = LOWER(:email))
              )
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"idc": id_cliente, "nome": contato_nome, "tel": telefone, "email": email},
    ).fetchone()
    if row:
        return int(row[0])

    novo = conn.execute(
        text(
            """
            INSERT INTO clientes_contatos
            (id_cliente, nome_contato, nome_fantasia, telefone_chave, email_chave, ativo)
            VALUES (:idc, :nome, :fantasia, :tel, :email, TRUE)
            RETURNING id
            """
        ),
        {
            "idc": id_cliente,
            "nome": contato_nome or None,
            # Algumas bases possuem NOT NULL em nome_fantasia.
            "fantasia": contato_nome or (f"Contato {telefone}" if telefone else "Contato não informado"),
            "tel": telefone or None,
            "email": email or None,
        },
    ).fetchone()
    return int(novo[0]) if novo else None


def _upsert_telefone(conn: Any, id_cliente: int, telefone_raw: str, origem: str = "MANUAL") -> Tuple[Optional[int], str, Optional[str]]:
    numero = _num(telefone_raw)
    if not numero:
        return None, "sem_numero", None
    tel_hash = gerar_hash_lgpd(numero)
    pk_col = _coluna_pk_telefone(conn)

    row = conn.execute(
        text(
            f"""
            SELECT t.{pk_col}, t.id_cliente, c.razao_social
            FROM clientes_telefones t
            JOIN clientes_crm c ON c.id_cliente = t.id_cliente
            WHERE t.numero = :num
              AND COALESCE(t.ativo, TRUE) = TRUE
              AND COALESCE(c.ativo, TRUE) = TRUE
            ORDER BY CASE WHEN t.id_cliente = :idc THEN 0 ELSE 1 END, t.{pk_col}
            LIMIT 1
            """
        ),
        {"idc": id_cliente, "num": numero},
    ).fetchone()
    if row:
        id_telefone = int(row[0])
        id_cliente_existente = int(row[1])
        nome_cliente_existente = str(row[2] or "")
        if id_cliente_existente == int(id_cliente):
            return id_telefone, "mesmo_cliente", nome_cliente_existente
        # Permite o mesmo número existir em clientes diferentes (CNPJs diferentes).
        # A unicidade relevante é (id_cliente, numero), garantida pelo índice ux_cliente_telefone.
        try:
            novo = conn.execute(
                text(
                    f"""
                    INSERT INTO clientes_telefones (id_cliente, origem_dado, numero, telefone_hash, ativo)
                    VALUES (:idc, :origem, :num, :h, TRUE)
                    RETURNING {pk_col}
                    """
                ),
                {"idc": id_cliente, "origem": origem, "num": numero, "h": tel_hash},
            ).fetchone()
            return (int(novo[0]), "duplicado_outro_cliente", nome_cliente_existente) if novo else (None, "erro", None)
        except Exception:
            novo = conn.execute(
                text(
                    f"""
                    INSERT INTO clientes_telefones (id_cliente, origem_dado, numero)
                    VALUES (:idc, :origem, :num)
                    RETURNING {pk_col}
                    """
                ),
                {"idc": id_cliente, "origem": origem, "num": numero},
            ).fetchone()
            return (int(novo[0]), "duplicado_outro_cliente", nome_cliente_existente) if novo else (None, "erro", None)

    try:
        novo = conn.execute(
            text(
                f"""
                INSERT INTO clientes_telefones (id_cliente, origem_dado, numero, telefone_hash, ativo)
                VALUES (:idc, :origem, :num, :h, TRUE)
                RETURNING {pk_col}
                """
            ),
            {"idc": id_cliente, "origem": origem, "num": numero, "h": tel_hash},
        ).fetchone()
        return (int(novo[0]), "inserido", None) if novo else (None, "erro", None)
    except Exception:
        # Fallback para estruturas mais antigas
        novo = conn.execute(
            text(
                f"""
                INSERT INTO clientes_telefones (id_cliente, origem_dado, numero)
                VALUES (:idc, :origem, :num)
                RETURNING {pk_col}
                """
            ),
            {"idc": id_cliente, "origem": origem, "num": numero},
        ).fetchone()
        return (int(novo[0]), "inserido", None) if novo else (None, "erro", None)


def _salvar_anexos(id_atendimento: int, arquivos: List[Any]) -> List[Tuple[str, str, int]]:
    anexos_ok: List[Tuple[str, str, int]] = []
    if not arquivos:
        return anexos_ok

    dt = datetime.now()
    pasta_rel = f"{UPLOAD_DIR}/{dt.year:04d}/{dt.month:02d}/{dt.day:02d}"
    pasta_abs = os.path.join(os.getcwd(), pasta_rel)
    os.makedirs(pasta_abs, exist_ok=True)

    engine = get_connection()
    with engine.begin() as conn:
        for arq in arquivos:
            if not arq:
                continue
            nome_original = arq.name or "anexo.bin"
            safe_name = os.path.basename(nome_original).replace("\\", "_").replace("/", "_")
            nome_disco = f"{uuid.uuid4().hex}_{safe_name}"
            caminho_rel = f"{pasta_rel}/{nome_disco}".replace("\\", "/")
            caminho_abs = os.path.join(os.getcwd(), caminho_rel)
            conteudo = arq.getbuffer()
            with open(caminho_abs, "wb") as f:
                f.write(conteudo)
            tamanho = int(len(conteudo))
            mime = getattr(arq, "type", None)

            conn.execute(
                text(
                    """
                    INSERT INTO atendimento_anexos
                    (atendimento_id, nome_arquivo, caminho_arquivo, mime_type, tamanho_bytes, ativo)
                    VALUES (:id, :nome, :caminho, :mime, :tam, TRUE)
                    """
                ),
                {
                    "id": id_atendimento,
                    "nome": nome_original[:512],
                    "caminho": caminho_rel[:1200],
                    "mime": (mime or "")[:255] or None,
                    "tam": tamanho,
                },
            )
            anexos_ok.append((nome_original, caminho_rel, tamanho))
    return anexos_ok


def _registrar_embedding(conn: Any, id_atendimento: int, motivo: str, solucao: str) -> None:
    """Registra embedding do atendimento (768 dim, Gemini) para busca semântica."""
    resumo = f"{(motivo or '').strip()} {(solucao or '').strip()}".strip()
    if not resumo:
        return
    emb = gerar_embedding_gemini(resumo[:4000])
    if not emb or len(emb) != 768:
        return
    emb_sql = _emb_to_sql(emb)
    conn.execute(
        text(
            """
            INSERT INTO atendimentos_embeddings (atendimento_id, resumo_busca, embedding)
            VALUES (:id, :resumo, CAST(:emb AS vector))
            ON CONFLICT (atendimento_id) DO UPDATE
               SET resumo_busca = EXCLUDED.resumo_busca,
                   embedding = EXCLUDED.embedding
            """
        ),
        {"id": id_atendimento, "resumo": resumo[:60000], "emb": emb_sql},
    )


def registrar_atendimento(payload: Dict[str, Any], anexos: Optional[List[Any]] = None) -> Tuple[bool, str, Optional[int]]:
    """
    Registra atendimento completo com vínculos e anexos.
    Retorna (ok, mensagem, id_atendimento).
    """
    setor = str(payload.get("setor") or "").strip()
    categoria = str(payload.get("categoria") or "").strip()
    criticidade = str(payload.get("criticidade") or "").strip()
    canal = str(payload.get("canal") or "").strip()
    protocolo = str(payload.get("protocolo") or "").strip()
    motivo = str(payload.get("motivo") or "").strip()

    if setor not in ("Suporte Geral", "TEF"):
        return False, "Setor inválido. Use Suporte Geral ou TEF.", None
    if not categoria:
        return False, "Categoria é obrigatória.", None
    if criticidade not in CRITICIDADES:
        return False, "Criticidade inválida.", None
    if not canal:
        return False, "Canal é obrigatório.", None
    if canal == "Chat Multi360" and not protocolo:
        return False, "Protocolo é obrigatório para canal Multi360.", None
    if len(motivo) < 10:
        return False, "Motivo/assunto deve ter no mínimo 10 caracteres.", None

    id_cliente = payload.get("cliente_id")
    razao_social = str(payload.get("razao_social") or "").strip()
    cnpj_limpo = _num(str(payload.get("cnpj") or ""))
    tel_limpo = _num(str(payload.get("telefone") or ""))

    engine = get_connection()
    try:
        msg_telefone = ""
        with engine.begin() as conn:
            if not id_cliente:
                if cnpj_limpo:
                    row_cnpj = conn.execute(
                        text(
                            """
                            SELECT id_cliente
                            FROM clientes_crm
                            WHERE cnpj = :cnpj
                            LIMIT 1
                            """
                        ),
                        {"cnpj": cnpj_limpo},
                    ).fetchone()
                    if row_cnpj:
                        id_cliente = int(row_cnpj[0])
                if cnpj_limpo and not id_cliente:
                    if not razao_social:
                        return False, "CNPJ não encontrado. Informe a Razão Social para criar o cliente.", None
                    try:
                        novo_cli = conn.execute(
                            text(
                                """
                                INSERT INTO clientes_crm (razao_social, cnpj, ativo)
                                VALUES (:nome, :cnpj, TRUE)
                                RETURNING id_cliente
                                """
                            ),
                            {"nome": razao_social, "cnpj": cnpj_limpo},
                        ).fetchone()
                    except Exception:
                        novo_cli = conn.execute(
                            text(
                                """
                                INSERT INTO clientes_crm (razao_social, cnpj)
                                VALUES (:nome, :cnpj)
                                RETURNING id_cliente
                                """
                            ),
                            {"nome": razao_social, "cnpj": cnpj_limpo},
                        ).fetchone()
                    id_cliente = int(novo_cli[0]) if novo_cli else None
                if not cnpj_limpo and not id_cliente and tel_limpo:
                    row_tel = conn.execute(
                        text(
                            """
                            SELECT c.id_cliente
                            FROM clientes_telefones t
                            JOIN clientes_crm c ON c.id_cliente = t.id_cliente
                            WHERE t.numero = :tel
                            LIMIT 1
                            """
                        ),
                        {"tel": tel_limpo},
                    ).fetchone()
                    if row_tel:
                        id_cliente = int(row_tel[0])
                if not cnpj_limpo and not id_cliente and razao_social:
                    row_nome = conn.execute(
                        text(
                            """
                            SELECT id_cliente
                            FROM clientes_crm
                            WHERE LOWER(TRIM(razao_social)) = LOWER(TRIM(:nome))
                            LIMIT 1
                            """
                        ),
                        {"nome": razao_social},
                    ).fetchone()
                    if row_nome:
                        id_cliente = int(row_nome[0])
                if not id_cliente and not razao_social:
                    return False, "Informe a Razão Social quando não houver correspondência automática.", None
                if not id_cliente:
                    try:
                        novo_cli = conn.execute(
                            text(
                                """
                                INSERT INTO clientes_crm (razao_social, cnpj, ativo)
                                VALUES (:nome, :cnpj, TRUE)
                                RETURNING id_cliente
                                """
                            ),
                            {"nome": razao_social, "cnpj": cnpj_limpo or None},
                        ).fetchone()
                    except Exception:
                        novo_cli = conn.execute(
                            text(
                                """
                                INSERT INTO clientes_crm (razao_social, cnpj)
                                VALUES (:nome, :cnpj)
                                RETURNING id_cliente
                                """
                            ),
                            {"nome": razao_social, "cnpj": cnpj_limpo or None},
                        ).fetchone()
                    id_cliente = int(novo_cli[0]) if novo_cli else None
            if not id_cliente:
                return False, "Não foi possível identificar/criar cliente.", None

            if cnpj_limpo:
                try:
                    conn.execute(
                        text(
                            """
                            UPDATE clientes_crm
                            SET cnpj = COALESCE(NULLIF(cnpj, ''), :cnpj)
                            WHERE id_cliente = :id
                            """
                        ),
                        {"id": int(id_cliente), "cnpj": cnpj_limpo},
                    )
                except Exception:
                    pass

            contato_id = _upsert_contato(
                conn,
                int(id_cliente),
                str(payload.get("contato_nome") or ""),
                tel_limpo,
                str(payload.get("email_contato") or ""),
            )
            telefone_id, status_telefone, cliente_dono_telefone = _upsert_telefone(
                conn,
                int(id_cliente),
                tel_limpo,
                origem=str(payload.get("origem_registro") or "MANUAL"),
            )
            if status_telefone == "mesmo_cliente":
                msg_telefone = " Número já estava vinculado a este cliente e foi reutilizado."
            if status_telefone == "duplicado_outro_cliente":
                msg_telefone = (
                    " Número já existia em outro cliente"
                    f" ({cliente_dono_telefone or 'não identificado'}) e foi vinculado também a este CNPJ."
                )

            row = conn.execute(
                text(
                    """
                    INSERT INTO atendimentos_registrados
                    (
                        usuario_id, nome_analista, cliente_id, contato_id, telefone_id,
                        setor, categoria, criticidade, canal, protocolo, data_atendimento, duracao_min,
                        motivo, solucao, resolvido, abriu_chamado, nr_chamado, origem_registro, ativo
                    )
                    VALUES
                    (
                        :usuario_id, :nome_analista, :cliente_id, :contato_id, :telefone_id,
                        :setor, :categoria, :criticidade, :canal, :protocolo, :data_atendimento, :duracao_min,
                        :motivo, :solucao, :resolvido, :abriu_chamado, :nr_chamado, :origem_registro, TRUE
                    )
                    RETURNING id_atendimento
                    """
                ),
                {
                    "usuario_id": payload.get("usuario_id"),
                    "nome_analista": (payload.get("nome_analista") or "")[:150] or None,
                    "cliente_id": int(id_cliente),
                    "contato_id": contato_id,
                    "telefone_id": telefone_id,
                    "setor": setor,
                    "categoria": categoria[:255],
                    "criticidade": criticidade,
                    "canal": canal[:100],
                    "protocolo": protocolo[:120] or None,
                    "data_atendimento": payload.get("data_atendimento") or datetime.now(),
                    "duracao_min": payload.get("duracao_min"),
                    "motivo": motivo,
                    "solucao": (payload.get("solucao") or ""),
                    "resolvido": bool(payload.get("resolvido", False)),
                    "abriu_chamado": bool(payload.get("abriu_chamado", False)),
                    "nr_chamado": (payload.get("nr_chamado") or "")[:50] or None,
                    "origem_registro": (payload.get("origem_registro") or "MANUAL")[:30],
                },
            ).fetchone()
            if not row:
                return False, "Falha ao gerar ID do atendimento.", None
            id_atendimento = int(row[0])
            _registrar_embedding(conn, id_atendimento, motivo, str(payload.get("solucao") or ""))

        _salvar_anexos(id_atendimento, anexos or [])
        return True, f"Atendimento registrado com sucesso.{msg_telefone}", id_atendimento
    except Exception as e:
        return False, f"Erro ao salvar atendimento: {e}", None


def atualizar_atendimento(id_atendimento: int, usuario_id: int, payload: Dict[str, Any], perfil: str) -> Tuple[bool, str]:
    """
    Atualiza atendimento. Analista só pode editar o próprio registro.
    """
    engine = get_connection()
    setor = str(payload.get("setor") or "").strip()
    categoria = str(payload.get("categoria") or "").strip()
    criticidade = str(payload.get("criticidade") or "").strip()
    canal = str(payload.get("canal") or "").strip()
    protocolo = str(payload.get("protocolo") or "").strip()
    motivo = str(payload.get("motivo") or "").strip()
    if setor not in ("Suporte Geral", "TEF"):
        return False, "Setor inválido."
    if not categoria or criticidade not in CRITICIDADES or not canal:
        return False, "Campos obrigatórios inválidos."
    if canal == "Chat Multi360" and not protocolo:
        return False, "Protocolo obrigatório para Multi360."
    if len(motivo) < 10:
        return False, "Motivo deve ter no mínimo 10 caracteres."

    params: Dict[str, Any] = {
        "id": id_atendimento,
        "uid": usuario_id,
        "setor": setor,
        "categoria": categoria[:255],
        "criticidade": criticidade,
        "canal": canal[:100],
        "protocolo": protocolo[:120] or None,
        "duracao_min": payload.get("duracao_min"),
        "motivo": motivo,
        "solucao": str(payload.get("solucao") or ""),
        "resolvido": bool(payload.get("resolvido", False)),
        "abriu_chamado": bool(payload.get("abriu_chamado", False)),
        "nr_chamado": (payload.get("nr_chamado") or "")[:50] or None,
    }
    try:
        with engine.begin() as conn:
            up = conn.execute(
                text(
                    f"""
                    UPDATE atendimentos_registrados
                    SET
                      setor = :setor,
                      categoria = :categoria,
                      criticidade = :criticidade,
                      canal = :canal,
                      protocolo = :protocolo,
                      duracao_min = :duracao_min,
                      motivo = :motivo,
                      solucao = :solucao,
                      resolvido = :resolvido,
                      abriu_chamado = :abriu_chamado,
                      nr_chamado = :nr_chamado,
                      atualizado_em = CURRENT_TIMESTAMP
                    WHERE id_atendimento = :id
                      AND usuario_id = :uid
                    """
                ),
                params,
            )
            if not up.rowcount:
                return False, "Atendimento não encontrado ou você não é o autor."
            _registrar_embedding(conn, id_atendimento, motivo, str(payload.get("solucao") or ""))
        return True, "Atendimento atualizado com sucesso."
    except Exception as e:
        return False, f"Erro ao atualizar atendimento: {e}"


def excluir_atendimento(id_atendimento: int, usuario_id: int) -> Tuple[bool, str]:
    engine = get_connection()
    try:
        with engine.begin() as conn:
            up = conn.execute(
                text(
                    """
                    UPDATE atendimentos_registrados
                    SET ativo = FALSE,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id_atendimento = :id
                      AND usuario_id = :uid
                      AND ativo = TRUE
                    """
                ),
                {"id": int(id_atendimento), "uid": int(usuario_id)},
            )
            if not up.rowcount:
                return False, "Atendimento não encontrado ou você não é o autor."
        return True, "Atendimento excluído com sucesso."
    except Exception as e:
        return False, f"Erro ao excluir atendimento: {e}"


def _montar_where_filtros(
    usuario_id: Optional[int],
    perfil: str,
    data_ini: Optional[date],
    data_fim: Optional[date],
    cliente_id: Optional[int],
    setor: str,
    canal: str,
    protocolo: str,
    analista_id: Optional[int],
) -> Tuple[str, Dict[str, Any]]:
    where = ["a.ativo = TRUE"]
    params: Dict[str, Any] = {}
    if analista_id:
        where.append("a.usuario_id = :aid")
        params["aid"] = analista_id

    if data_ini:
        params["dini"] = datetime.combine(data_ini, time.min)
        where.append("a.data_atendimento >= :dini")
    if data_fim:
        params["dfim"] = datetime.combine(data_fim, time.max)
        where.append("a.data_atendimento <= :dfim")
    if cliente_id:
        where.append("a.cliente_id = :cid")
        params["cid"] = int(cliente_id)
    if setor and setor != "Todos":
        where.append("a.setor = :setor")
        params["setor"] = setor
    if canal and canal != "Todos":
        where.append("a.canal = :canal")
        params["canal"] = canal
    protocolo_like = str(protocolo or "").strip()
    if protocolo_like:
        where.append("COALESCE(a.protocolo, '') ILIKE :protocolo")
        params["protocolo"] = f"%{protocolo_like}%"
    return " WHERE " + " AND ".join(where), params


def _clausula_busca_texto(busca_semantica: str) -> Tuple[str, str, Dict[str, Any]]:
    """Retorna (clausula_completa, condicoes_internas, params) para busca por texto em vários campos."""
    termo = (busca_semantica or "").strip()
    if not termo:
        return "", "", {}
    qtxt = f"%{termo}%"
    inner = (
        "a.motivo ILIKE :qtxt "
        "OR COALESCE(a.solucao, '') ILIKE :qtxt "
        "OR COALESCE(a.categoria, '') ILIKE :qtxt "
        "OR COALESCE(a.setor, '') ILIKE :qtxt "
        "OR COALESCE(a.canal, '') ILIKE :qtxt "
        "OR c.razao_social ILIKE :qtxt"
    )
    full = " AND (" + inner + ")"
    return full, inner, {"qtxt": qtxt}


def consultar_atendimentos(
    usuario_id: Optional[int],
    perfil: str,
    data_ini: Optional[date],
    data_fim: Optional[date],
    cliente_id: Optional[int],
    setor: str = "Todos",
    canal: str = "Todos",
    protocolo: str = "",
    analista_id: Optional[int] = None,
    busca_semantica: str = "",
    limite: int = 300,
) -> pd.DataFrame:
    engine = get_connection()
    with engine.connect() as conn_meta:
        telefone_pk_col = _coluna_pk_telefone(conn_meta)
    where_sql, params = _montar_where_filtros(
        usuario_id, perfil, data_ini, data_fim, cliente_id, setor, canal, protocolo, analista_id
    )

    # Busca por texto: motivo, solucao, categoria, setor, canal, cliente
    busca_semantica = (busca_semantica or "").strip()
    text_full, text_inner, text_params = _clausula_busca_texto(busca_semantica)
    if text_params:
        params.update(text_params)

    # Busca vetorial (Gemini 768) quando há termo e API disponível
    emb = None
    if busca_semantica:
        try:
            emb = gerar_embedding_gemini(busca_semantica[:3000])
        except Exception:
            emb = None
        if emb is not None and len(emb) != 768:
            emb = None

    if emb:
        params["emb"] = _emb_to_sql(emb)
        params["lim"] = limite
        # Retorna todos que têm embedding OU que batem no texto
        where_com_busca = where_sql + " AND (e.embedding IS NOT NULL OR " + text_inner + ")"
        sql = text(
            f"""
            SELECT
                a.id_atendimento,
                a.usuario_id,
                a.data_atendimento,
                COALESCE(u.nome, a.nome_analista, 'Sem nome') AS analista,
                c.razao_social AS cliente,
                c.cnpj,
                COALESCE(ct.nome_contato, '') AS contato,
                COALESCE(t.numero, '') AS telefone,
                a.setor,
                a.categoria,
                a.criticidade,
                a.canal,
                a.protocolo,
                a.duracao_min,
                a.motivo,
                a.solucao,
                a.resolvido,
                a.abriu_chamado,
                a.nr_chamado,
                (1 - (e.embedding <=> CAST(:emb AS vector))) AS score_semantico
            FROM atendimentos_registrados a
            JOIN clientes_crm c ON c.id_cliente = a.cliente_id
            LEFT JOIN clientes_contatos ct ON ct.id = a.contato_id
            LEFT JOIN clientes_telefones t ON t.{telefone_pk_col} = a.telefone_id
            LEFT JOIN usuarios u ON u.id = a.usuario_id
            LEFT JOIN atendimentos_embeddings e ON e.atendimento_id = a.id_atendimento
            {where_com_busca}
            ORDER BY
              CASE WHEN e.embedding IS NULL THEN 1 ELSE 0 END,
              e.embedding <=> CAST(:emb AS vector),
              a.data_atendimento DESC
            LIMIT :lim
            """
        )
    else:
        if text_full:
            where_sql += text_full
        params["lim"] = limite
        sql = text(
            f"""
            SELECT
                a.id_atendimento,
                a.usuario_id,
                a.data_atendimento,
                COALESCE(u.nome, a.nome_analista, 'Sem nome') AS analista,
                c.razao_social AS cliente,
                c.cnpj,
                COALESCE(ct.nome_contato, '') AS contato,
                COALESCE(t.numero, '') AS telefone,
                a.setor,
                a.categoria,
                a.criticidade,
                a.canal,
                a.protocolo,
                a.duracao_min,
                a.motivo,
                a.solucao,
                a.resolvido,
                a.abriu_chamado,
                a.nr_chamado,
                NULL::float AS score_semantico
            FROM atendimentos_registrados a
            JOIN clientes_crm c ON c.id_cliente = a.cliente_id
            LEFT JOIN clientes_contatos ct ON ct.id = a.contato_id
            LEFT JOIN clientes_telefones t ON t.{telefone_pk_col} = a.telefone_id
            LEFT JOIN usuarios u ON u.id = a.usuario_id
            {where_sql}
            ORDER BY a.data_atendimento DESC
            LIMIT :lim
            """
        )
    try:
        with engine.connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except Exception:
        if emb and text_full:
            params.pop("emb", None)
            where_sql_fb = where_sql + text_full
            params["lim"] = limite
            sql_fb = text(
                f"""
                SELECT
                    a.id_atendimento,
                    a.usuario_id,
                    a.data_atendimento,
                    COALESCE(u.nome, a.nome_analista, 'Sem nome') AS analista,
                    c.razao_social AS cliente,
                    c.cnpj,
                    COALESCE(ct.nome_contato, '') AS contato,
                    COALESCE(t.numero, '') AS telefone,
                    a.setor,
                    a.categoria,
                    a.criticidade,
                    a.canal,
                    a.protocolo,
                    a.duracao_min,
                    a.motivo,
                    a.solucao,
                    a.resolvido,
                    a.abriu_chamado,
                    a.nr_chamado,
                    NULL::float AS score_semantico
                FROM atendimentos_registrados a
                JOIN clientes_crm c ON c.id_cliente = a.cliente_id
                LEFT JOIN clientes_contatos ct ON ct.id = a.contato_id
                LEFT JOIN clientes_telefones t ON t.{telefone_pk_col} = a.telefone_id
                LEFT JOIN usuarios u ON u.id = a.usuario_id
                {where_sql_fb}
                ORDER BY a.data_atendimento DESC
                LIMIT :lim
                """
            )
            with engine.connect() as conn:
                return pd.read_sql(sql_fb, conn, params=params)
        raise


def listar_anexos_atendimento(id_atendimento: int) -> pd.DataFrame:
    engine = get_connection()
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                """
                SELECT id_anexo, nome_arquivo, caminho_arquivo, mime_type, tamanho_bytes, criado_em
                FROM atendimento_anexos
                WHERE atendimento_id = :id AND ativo = TRUE
                ORDER BY id_anexo
                """
            ),
            conn,
            params={"id": int(id_atendimento)},
        )


def metricas_resumo(df: pd.DataFrame) -> Dict[str, int]:
    if df.empty:
        return {"total": 0, "dia": 0, "semana": 0, "mes": 0, "ano": 0}
    base = df.copy()
    base["data_atendimento"] = pd.to_datetime(base["data_atendimento"], errors="coerce")
    agora = pd.Timestamp.now(tz=base["data_atendimento"].dt.tz if base["data_atendimento"].dt.tz is not None else None)
    hoje = agora.normalize()
    ini_semana = hoje - pd.Timedelta(days=int(hoje.weekday()))
    ini_mes = hoje.replace(day=1)
    ini_ano = hoje.replace(month=1, day=1)
    return {
        "total": int(len(base)),
        "dia": int((base["data_atendimento"] >= hoje).sum()),
        "semana": int((base["data_atendimento"] >= ini_semana).sum()),
        "mes": int((base["data_atendimento"] >= ini_mes).sum()),
        "ano": int((base["data_atendimento"] >= ini_ano).sum()),
    }


def ranking_clientes_motivos(df: pd.DataFrame, top_n: int = 10) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    top_clientes = (
        df.groupby("cliente", dropna=False)
        .size()
        .reset_index(name="total_atendimentos")
        .sort_values("total_atendimentos", ascending=False)
        .head(top_n)
    )
    top_motivos = (
        df.groupby("categoria", dropna=False)
        .size()
        .reset_index(name="total_atendimentos")
        .sort_values("total_atendimentos", ascending=False)
        .head(top_n)
    )
    return top_clientes, top_motivos

