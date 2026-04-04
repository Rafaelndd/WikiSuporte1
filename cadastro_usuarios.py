"""
Criação de usuários do WikiSuporte no PostgreSQL (hash bcrypt, coluna `nome`).

Modo interativo (sem argumentos):
  python cadastro_usuarios.py

Modo terminal (não interativo):
  python cadastro_usuarios.py meu.login --senha 'MinhaSenh@1'
  echo minhasenha | python cadastro_usuarios.py meu.login --senha-stdin

Atualizar usuário existente (perfil e/ou senha — não duplica `nome`):
  python cadastro_usuarios.py admin --atualizar --perfil admin
  python cadastro_usuarios.py admin --atualizar --senha 'NovaSenh@1'
  python cadastro_usuarios.py admin --atualizar --senha '...' --perfil analista

Atenção: --senha fica no histórico do shell; em produção prefira --senha-stdin ou variável
WS_CADASTRO_SENHA (lida se --senha e --senha-stdin forem omitidos em modo CLI).
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import bcrypt
import pandas as pd
from sqlalchemy import text

from modules.database import get_connection
from services.usuario_modelo import defaults_novo_usuario, normalizar_username


def validar_senha_forte(senha: str) -> tuple[bool, str]:
    """Valida: Mínimo 8 caracteres, 1 Maiúscula, 1 Número, 1 Caractere Especial."""
    if len(senha) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."
    if not re.search(r"[A-Z]", senha):
        return False, "A senha deve ter pelo menos 1 letra maiúscula."
    if not re.search(r"[0-9]", senha):
        return False, "A senha deve ter pelo menos 1 número."
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', senha):
        return False, "A senha deve ter pelo menos 1 caractere especial."
    return True, "Senha válida."


def mapear_perfil_cli(valor: str) -> str:
    """Converte atalhos CLI para o texto gravado em `usuarios.perfil` (somente admin ou analista)."""
    v = (valor or "analista").strip().lower()
    mapa = {
        "analista": "analista",
        "admin": "admin",
        "master": "admin",
        "coordenador": "admin",
        "coordenação": "admin",
        "coordenacao": "admin",
        "dev": "admin",
        "desenvolvedor": "admin",
        "supervisor": "admin",
    }
    return mapa.get(v, "analista")


def criar_usuario(
    username: str,
    senha: str,
    perfil: str,
    *,
    nome_exibicao: str | None = None,
    ramal: str = "",
    ativo: bool = True,
    em_ferias: bool = False,
    em_atendimento_externo: bool = False,
    caminho_foto_perfil: str = "",
) -> tuple[bool, str]:
    """
    Insere usuário no modelo alinhado à gestão (nome, username, hash, perfil, ramal, flags).

    Parâmetro `username` (primeiro argumento posicional): login curto quando `nome_exibicao`
    é informado; caso contrário mantém o comportamento legado (valor gravado em `nome` e
    espelhado em `username` em minúsculas).
    """
    valida, msg = validar_senha_forte(senha)
    if not valida:
        return False, msg

    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), salt).decode("utf-8")
    perfil_db = mapear_perfil_cli(perfil)
    canon = perfil_db.lower()

    nome_db, user_db = defaults_novo_usuario(
        nome_exibicao if (nome_exibicao or "").strip() else username,
        username if (nome_exibicao or "").strip() else None,
    )
    if not nome_db:
        return False, "Nome de usuário vazio."

    try:
        engine = get_connection()
        with engine.begin() as conn:
            query = text(
                "INSERT INTO usuarios (nome, username, password_hash, perfil, ramal, ativo, "
                "em_ferias, em_atendimento_externo, caminho_foto_perfil) "
                "VALUES (:nome, :u, :h, :p, :ramal, :ativo, :ferias, :ext, :foto)"
            )
            conn.execute(
                query,
                {
                    "nome": nome_db[:150],
                    "u": (user_db[:150] if user_db else None),
                    "h": senha_hash,
                    "p": canon,
                    "ramal": (ramal or "")[:20],
                    "ativo": ativo,
                    "ferias": em_ferias,
                    "ext": em_atendimento_externo,
                    "foto": (caminho_foto_perfil or "")[:500],
                },
            )
        return True, (
            f"Usuário '{nome_db}' criado (login: {user_db or nome_db}) com perfil '{canon}'."
        )
    except Exception as e:
        err = str(e)
        if "UniqueViolation" in type(e).__name__ or "unique" in err.lower():
            err += (
                " Dica: para alterar perfil/senha do mesmo login, use --atualizar "
                "(ex.: python cadastro_usuarios.py admin --atualizar --perfil analista)."
            )
        return False, f"Erro ao criar usuário (duplicado ou schema): {err}"


def atualizar_usuario(
    username: str,
    senha: str | None,
    perfil: str | None,
) -> tuple[bool, str]:
    """
    Atualiza `password_hash` e/ou `perfil` do usuário com `nome` = username.
    `senha` ou `perfil` deve estar definido (pelo menos um).
    """
    nome = username.strip()
    if not nome:
        return False, "Nome de usuário vazio."

    sets: list[str] = []
    params: dict[str, str] = {"nome": nome}

    if senha is not None and senha != "":
        valida, msg = validar_senha_forte(senha)
        if not valida:
            return False, msg
        salt = bcrypt.gensalt()
        params["h"] = bcrypt.hashpw(senha.encode("utf-8"), salt).decode("utf-8")
        sets.append("password_hash = :h")

    if perfil is not None:
        perfil_db = mapear_perfil_cli(perfil)
        params["p"] = perfil_db.lower()
        sets.append("perfil = :p")

    if not sets:
        return False, "Nada a atualizar: passe --senha e/ou --perfil."

    try:
        engine = get_connection()
        sql = text(f"UPDATE usuarios SET {', '.join(sets)} WHERE nome = :nome")
        with engine.begin() as conn:
            res = conn.execute(sql, params)
            n = res.rowcount if res is not None else 0
        if not n:
            return False, f"Usuário '{nome}' não encontrado em `usuarios`."
        partes = []
        if "h" in params:
            partes.append("senha")
        if "p" in params:
            partes.append(f"perfil='{params['p']}'")
        return True, f"Usuário '{nome}' atualizado ({', '.join(partes)})."
    except Exception as e:
        return False, f"Erro ao atualizar: {e}"


def listar_usuarios_admin() -> tuple[bool, str, pd.DataFrame | None]:
    """
    Lista usuários para o painel admin (sem `password_hash`).
    Retorna (sucesso, mensagem_erro_ou_vazia, DataFrame|None).
    """
    sql = text(
        """
        SELECT
            id,
            nome,
            COALESCE(username, '') AS username,
            perfil,
            COALESCE(ramal, '') AS ramal,
            COALESCE(ativo, TRUE) AS ativo,
            COALESCE(em_ferias, FALSE) AS em_ferias,
            COALESCE(em_atendimento_externo, FALSE) AS em_atendimento_externo
        FROM usuarios
        ORDER BY nome
        """
    )
    try:
        engine = get_connection()
        df = pd.read_sql(sql, engine)
        return True, "", df
    except Exception as e:
        return False, f"Falha ao consultar usuários: {e}", None


def atualizar_usuario_painel(
    usuario_id: int,
    nome: str,
    username: str,
    ramal: str,
    perfil: str,
    ativo: bool,
    em_ferias: bool,
    em_atendimento_externo: bool,
    nova_senha: str | None = None,
) -> tuple[bool, str]:
    """
    Atualiza campos operacionais e opcionalmente a senha (hash bcrypt). Chave: `id`.
    """
    if usuario_id <= 0:
        return False, "ID de usuário inválido."

    nome_db = (nome or "").strip()
    if not nome_db:
        return False, "Nome é obrigatório."

    user_norm = normalizar_username(username)
    perfil_db = mapear_perfil_cli(perfil)
    canon = perfil_db.lower()
    if canon not in ("admin", "analista"):
        return False, "Perfil inválido: use apenas admin ou analista."

    sets = [
        "nome = :nome",
        "username = :username",
        "ramal = :ramal",
        "perfil = :perfil",
        "ativo = :ativo",
        "em_ferias = :ferias",
        "em_atendimento_externo = :ext",
    ]
    params: dict = {
        "id": usuario_id,
        "nome": nome_db[:150],
        "username": user_norm[:150] if user_norm else None,
        "ramal": (ramal or "")[:20],
        "perfil": canon,
        "ativo": bool(ativo),
        "ferias": bool(em_ferias),
        "ext": bool(em_atendimento_externo),
    }

    if nova_senha is not None and str(nova_senha).strip() != "":
        valida, msg = validar_senha_forte(str(nova_senha).strip())
        if not valida:
            return False, msg
        salt = bcrypt.gensalt()
        params["h"] = bcrypt.hashpw(str(nova_senha).strip().encode("utf-8"), salt).decode(
            "utf-8"
        )
        sets.append("password_hash = :h")

    try:
        engine = get_connection()
        sql = text(f"UPDATE usuarios SET {', '.join(sets)} WHERE id = :id")
        with engine.begin() as conn:
            res = conn.execute(sql, params)
            n = res.rowcount if res is not None else 0
        if not n:
            return False, "Usuário não encontrado ou ID inválido."
        return True, "Usuário atualizado com sucesso."
    except Exception as e:
        err = str(e)
        if "UniqueViolation" in type(e).__name__ or "unique" in err.lower():
            err += " Verifique se nome ou username já estão em uso."
        return False, f"Erro ao atualizar usuário: {err}"


def inativar_usuario_por_id(usuario_id: int) -> tuple[bool, str]:
    """Soft delete: apenas `ativo = FALSE` (preserva histórico)."""
    if usuario_id <= 0:
        return False, "ID de usuário inválido."
    try:
        engine = get_connection()
        with engine.begin() as conn:
            res = conn.execute(
                text("UPDATE usuarios SET ativo = FALSE WHERE id = :id"),
                {"id": usuario_id},
            )
            n = res.rowcount if res is not None else 0
        if not n:
            return False, "Usuário não encontrado."
        return True, "Usuário inativado (mantido no histórico)."
    except Exception as e:
        return False, f"Erro ao inativar usuário: {e}"


# --- Meu Perfil (usuário autenticado): leitura segura, foto e troca de senha ---

_MAX_BYTES_FOTO_PERFIL = 2_500_000  # ~2,5 MB


def slug_para_nome_arquivo_perfil(username: str, usuario_id: int) -> str:
    """Segmento seguro para o nome do arquivo (sem path traversal)."""
    raw = (username or "").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "_", raw, flags=re.IGNORECASE)
    raw = raw.strip("._")
    if not raw:
        raw = f"id{int(usuario_id)}"
    return raw[:80]


def validar_bytes_imagem_perfil(data: bytes) -> tuple[bool, str]:
    """
    Aceita apenas assinatura PNG ou JPEG (defesa contra uploads maliciosos).
    Em caso de sucesso devolve (True, '.png'|'.jpg'); em falha (False, mensagem).
    """
    if not data:
        return False, "Arquivo vazio."
    if len(data) > _MAX_BYTES_FOTO_PERFIL:
        return False, "Arquivo muito grande (máx. 2,5 MB)."
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True, ".png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return True, ".jpg"
    return False, "Formato inválido. Use apenas PNG ou JPEG."


def obter_dados_perfil_meu_perfil(usuario_id: int) -> tuple[bool, str, dict | None]:
    """
    Dados do próprio usuário para a página «Meu Perfil» (sem expor `password_hash`).
    """
    if usuario_id <= 0:
        return False, "Sessão inválida.", None
    sql = text(
        """
        SELECT
            id,
            nome,
            COALESCE(NULLIF(trim(username), ''), '') AS username,
            COALESCE(NULLIF(trim(ramal), ''), '') AS ramal,
            COALESCE(NULLIF(trim(caminho_foto_perfil), ''), '') AS caminho_foto_perfil
        FROM usuarios
        WHERE id = :id
        """
    )
    try:
        engine = get_connection()
        with engine.connect() as conn:
            row = conn.execute(sql, {"id": usuario_id}).mappings().fetchone()
        if not row:
            return False, "Perfil não encontrado na base de dados.", None
        return True, "", dict(row)
    except Exception as e:
        return False, f"Erro ao carregar perfil: {e}", None


def atualizar_caminho_foto_perfil_usuario(
    usuario_id: int, caminho_relativo_posix: str
) -> tuple[bool, str]:
    """Grava o caminho relativo (ex.: uploads/fotos_perfil/...)."""
    if usuario_id <= 0:
        return False, "Sessão inválida."
    rel = (caminho_relativo_posix or "").strip().replace("\\", "/")
    if ".." in rel or rel.startswith("/"):
        return False, "Caminho de foto inválido."
    try:
        engine = get_connection()
        with engine.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE usuarios SET caminho_foto_perfil = :p WHERE id = :id"
                ),
                {"p": rel[:500], "id": usuario_id},
            )
            n = res.rowcount if res is not None else 0
        if not n:
            return False, "Não foi possível atualizar a foto (usuário inexistente)."
        return True, "Caminho da foto atualizado."
    except Exception as e:
        return False, f"Erro ao gravar foto na base: {e}"


def _password_hash_bytes(stored: object) -> bytes:
    if stored is None:
        return b""
    if isinstance(stored, memoryview):
        stored = stored.tobytes()
    if isinstance(stored, bytes):
        h = stored
    else:
        h = str(stored).strip().encode("utf-8")
    return h


def trocar_senha_meu_perfil(
    usuario_id: int,
    senha_atual: str,
    nova_senha: str,
    nova_senha_confirmacao: str,
) -> tuple[bool, str]:
    """
    Valida a senha atual (bcrypt), confirma política da nova senha e atualiza o hash.
    """
    if usuario_id <= 0:
        return False, "Sessão inválida."

    nova = (nova_senha or "").strip()
    conf = (nova_senha_confirmacao or "").strip()
    if nova != conf:
        return False, "A nova senha e a confirmação não coincidem."

    valida, msg = validar_senha_forte(nova)
    if not valida:
        return False, msg

    atual = senha_atual or ""
    try:
        engine = get_connection()
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT password_hash FROM usuarios WHERE id = :id"),
                {"id": usuario_id},
            ).fetchone()
            if not row:
                return False, "Usuário não encontrado."
            stored = _password_hash_bytes(row[0])
            if not stored:
                return False, "Conta sem senha configurada; contacte um administrador."

            try:
                ok = bcrypt.checkpw(atual.encode("utf-8"), stored)
            except (ValueError, TypeError):
                return False, "Não foi possível validar a senha atual."

            if not ok:
                return False, "Senha atual incorreta."

            salt = bcrypt.gensalt()
            new_h = bcrypt.hashpw(nova.encode("utf-8"), salt).decode("utf-8")
            res = conn.execute(
                text("UPDATE usuarios SET password_hash = :h WHERE id = :id"),
                {"h": new_h, "id": usuario_id},
            )
            n = res.rowcount if res is not None else 0
        if not n:
            return False, "Falha ao atualizar a senha."
        return True, "Senha atualizada com sucesso."
    except Exception as e:
        return False, f"Erro ao alterar a senha: {e}"


def _ler_senha_cli(args: argparse.Namespace) -> str | None:
    if args.senha is not None:
        return args.senha
    if args.senha_stdin:
        line = sys.stdin.readline()
        return (line or "").rstrip("\r\n")
    env = (os.environ.get("WS_CADASTRO_SENHA") or "").strip()
    if env:
        return env
    return None


def _main_cli() -> int:
    parser = argparse.ArgumentParser(
        description="Cria usuário WikiSuporte no PostgreSQL (login na coluna `nome`).",
    )
    parser.add_argument(
        "nome",
        help="Nome de login (ex.: maria.silva — será usado na tela de login)",
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--senha",
        "-s",
        metavar="TEXTO",
        help="Senha forte (evite em shells compartilhados — fica no histórico)",
    )
    g.add_argument(
        "--senha-stdin",
        action="store_true",
        help="Ler senha da primeira linha do stdin (sem eco)",
    )
    parser.add_argument(
        "--perfil",
        default=None,
        metavar="PERFIL",
        help="analista | admin (criar: padrão analista se omitido)",
    )
    parser.add_argument(
        "--atualizar",
        "-u",
        action="store_true",
        help="Atualiza usuário existente (use com --perfil e/ou --senha; não insere linha nova)",
    )
    args = parser.parse_args()

    senha = _ler_senha_cli(args)

    if args.atualizar:
        if not senha and args.perfil is None:
            parser.error(
                "--atualizar exige --perfil e/ou senha (--senha, --senha-stdin ou WS_CADASTRO_SENHA)."
            )
        ok, msg = atualizar_usuario(args.nome, senha, args.perfil)
        print(msg)
        return 0 if ok else 1

    if not senha:
        parser.error(
            "Para criar, defina a senha com --senha, --senha-stdin ou WS_CADASTRO_SENHA."
        )

    perfil_criar = args.perfil if args.perfil is not None else "analista"
    ok, msg = criar_usuario(args.nome, senha, perfil_criar)
    print(msg)
    return 0 if ok else 1


def _main_interativo() -> int:
    print("=== CRIAÇÃO DE USUÁRIO DO DASHBOARD ===")
    user = input("Digite o nome de usuário: ")
    senha = input("Digite a senha forte: ")

    print("\n=== SELECIONE O PERFIL DE ACESSO ===")
    print("1 - Analista")
    print("2 - Admin (gestão total)")

    opcao = input("\nDigite o número correspondente ao perfil: ").strip()

    if opcao == "1":
        perfil = "analista"
    elif opcao == "2":
        perfil = "admin"
    else:
        print("⚠️ Opção inválida. Atribuindo perfil padrão: analista.")
        perfil = "analista"

    ok, msg = criar_usuario(user, senha, perfil)
    print(msg if ok else f"Erro: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        raise SystemExit(_main_interativo())
    raise SystemExit(_main_cli())
