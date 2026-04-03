"""
Criação de usuários do WikiSuporte no PostgreSQL (hash bcrypt, coluna `nome`).

Modo interativo (sem argumentos):
  python cadastro_usuarios.py

Modo terminal (não interativo):
  python cadastro_usuarios.py meu.login --senha 'MinhaSenh@1'
  echo minhasenha | python cadastro_usuarios.py meu.login --senha-stdin

Atualizar utilizador existente (perfil e/ou senha — não duplica `nome`):
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
from sqlalchemy import text

from modules.database import get_connection


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


def criar_usuario(username: str, senha: str, perfil: str) -> tuple[bool, str]:
    """
    Insere usuário. Retorna (True, mensagem sucesso) ou (False, mensagem erro).
    """
    valida, msg = validar_senha_forte(senha)
    if not valida:
        return False, msg

    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), salt).decode("utf-8")
    perfil_db = mapear_perfil_cli(perfil)

    try:
        engine = get_connection()
        with engine.begin() as conn:
            query = text(
                "INSERT INTO usuarios (nome, password_hash, perfil) VALUES (:nome, :h, :p)"
            )
            conn.execute(
                query,
                {"nome": username.strip(), "h": senha_hash, "p": perfil_db.lower()},
            )
        return True, (
            f"Usuário '{username.strip()}' criado com perfil '{perfil_db}'."
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
    Atualiza `password_hash` e/ou `perfil` do utilizador com `nome` = username.
    `senha` ou `perfil` deve estar definido (pelo menos um).
    """
    nome = username.strip()
    if not nome:
        return False, "Nome de utilizador vazio."

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
            return False, f"Utilizador '{nome}' não encontrado em `usuarios`."
        partes = []
        if "h" in params:
            partes.append("senha")
        if "p" in params:
            partes.append(f"perfil='{params['p']}'")
        return True, f"Utilizador '{nome}' atualizado ({', '.join(partes)})."
    except Exception as e:
        return False, f"Erro ao atualizar: {e}"


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
        help="Senha forte (evite em shells partilhados — fica no histórico)",
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
        help="Atualiza utilizador existente (use com --perfil e/ou --senha; não insere linha nova)",
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
