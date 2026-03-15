# -*- coding: utf-8 -*-
"""
Configuração central de ramais especiais e setores para atendimentos GoTo.
- Ramais excluídos: não entram no mapa e ligações para eles são ignoradas nas métricas.
- Ramais com rótulo: nome exibido no lugar do ramal (Caixa Parado, Chamador, etc.).
- Setores: TEF e Suporte Geral (usado no Dashboard e relatórios).
"""

# Ramal que NÃO deve ser considerado: nem no mapa de analistas nem as ligações para ele
RAMAIS_EXCLUIR = ["5355"]

# Ramal -> nome/rotulo (para exibição e identificação do atendente)
# 5366 = Caixa Parado; 5365 = Chamador da central; 5364 = Jairo (TEF)
RAMAL_NOME_ESPECIAL = {
    "5366": "Caixa Parado",
    "5365": "Chamador da central",
    "5364": "Jairo",
}

# Ramais do setor TEF (atualmente só 5364 - Jairo)
SETOR_TEF_RAMAIS = ["5364"]
SETOR_TEF = "TEF"
SETOR_SUPORTE_GERAL = "Suporte Geral"


def ramal_pertence_setor_tef(ramal: str) -> bool:
    """Retorna True se o ramal é do setor TEF."""
    return str(ramal).strip() in SETOR_TEF_RAMAIS


def obter_setor_por_ramal(ramal: str) -> str:
    """Retorna o setor (TEF ou Suporte Geral) para o ramal informado."""
    return SETOR_TEF if ramal_pertence_setor_tef(ramal) else SETOR_SUPORTE_GERAL


def obter_setor_por_nome_analista(nome_analista: str, mapa_ramal_nome: dict) -> str:
    """
    Dado o nome do analista e o mapa ramal->nome usado na identificação,
    retorna o setor (TEF ou Suporte Geral).
    """
    if not nome_analista or not mapa_ramal_nome:
        return SETOR_SUPORTE_GERAL
    nome = str(nome_analista).strip()
    for ramal, n in mapa_ramal_nome.items():
        if n and str(n).strip() == nome:
            return obter_setor_por_ramal(ramal)
    return SETOR_SUPORTE_GERAL
