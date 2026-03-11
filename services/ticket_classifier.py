"""
Serviço: Classificador de Chamados e Monitoramento de SLA.
- Classifica chamados em: ERRO, MELHORIA, ADEQUACAO_FISCAL.
- Alertas de SLA para 10, 15 e 60 dias conforme categoria e data de abertura.
Uso: importar e chamar classificar_chamado(), obter_alertas_sla() etc.
Não modifica arquivos originais do projeto.
"""
import re
from datetime import datetime, timedelta
from typing import Optional

# Conexão com o banco (reutiliza o motor existente)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

try:
    from modules.database import get_connection
except ImportError:
    get_connection = None

# Tabela auxiliar para armazenar a classificação (criada pelo próprio serviço)
TABELA_CLASSIFICACAO = "chamado_classificacao"

TIPOS = ("ERRO", "MELHORIA", "ADEQUACAO_FISCAL")

# Limites de SLA em dias por tipo (ajustáveis)
SLA_DIAS = {
    "ERRO": [10, 15, 60],
    "MELHORIA": [15, 30, 60],
    "ADEQUACAO_FISCAL": [10, 15, 60],
}


def _engine():
    if get_connection is None:
        raise RuntimeError("modules.database.get_connection não disponível.")
    return get_connection()


def _criar_tabela_classificacao():
    """Cria a tabela de classificação se não existir (não altera schema original)."""
    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {TABELA_CLASSIFICACAO} (
                nr_chamado INTEGER PRIMARY KEY REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
                tipo VARCHAR(50) NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()


def _texto_para_analise(assunto_html: Optional[str], motivo_html: Optional[str]) -> str:
    """Extrai texto para análise a partir de campos HTML."""
    if not assunto_html and not motivo_html:
        return ""
    texto = " ".join(filter(None, [assunto_html or "", motivo_html or ""]))
    # Remove tags HTML simples para análise
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = re.sub(r"\s+", " ", texto).strip().upper()
    return texto


def classificar_por_texto(assunto_html: Optional[str], motivo_abertura_html: Optional[str]) -> str:
    """
    Classifica o tipo do chamado com base em palavras-chave em assunto e motivo.
    Retorna um de: ERRO, MELHORIA, ADEQUACAO_FISCAL.
    """
    texto = _texto_para_analise(assunto_html, motivo_abertura_html)
    if not texto:
        return "ERRO"  # default conservador

    # Adequação fiscal / SPED / obrigações fiscais
    termos_adequacao = (
        "SPED", "FISCAL", "OBRIGAÇÃO", "OBRIGACAO", "NF-E", "NFE", "MDF-E", "CT-E",
        "DIEF", "LMC", "PMPF", "CARTA CORREÇÃO", "ADEQUAÇÃO", "ADEQUACAO", "COMPLIANCE"
    )
    if any(t in texto for t in termos_adequacao):
        return "ADEQUACAO_FISCAL"

    # Melhoria / pedido / solicitação de novo
    termos_melhoria = (
        "MELHORIA", "PEDIDO DE MELHORIA", "SOLICITAÇÃO", "NOVO RELATÓRIO",
        "RELATORIO", "MELHORAR", "IMPLEMENTAR", "INCLUIR FUNCIONALIDADE"
    )
    if any(t in texto for t in termos_melhoria):
        return "MELHORIA"

    # Caso contrário: ERRO (bug, problema, erro de sistema, etc.)
    return "ERRO"


def classificar_chamado(nr_chamado: int, assunto_html: Optional[str], motivo_abertura_html: Optional[str]) -> str:
    """
    Classifica o chamado e persiste na tabela chamado_classificacao.
    Retorna o tipo atribuído.
    """
    _criar_tabela_classificacao()
    tipo = classificar_por_texto(assunto_html, motivo_abertura_html)
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO {TABELA_CLASSIFICACAO} (nr_chamado, tipo)
                VALUES (:nr, :tipo)
                ON CONFLICT (nr_chamado) DO UPDATE SET tipo = EXCLUDED.tipo
            """),
            {"nr": nr_chamado, "tipo": tipo}
        )
    return tipo


def classificar_chamados_pendentes(limite: int = 500) -> int:
    """
    Classifica em lote chamados que ainda não têm registro em chamado_classificacao.
    Retorna a quantidade processada.
    """
    _criar_tabela_classificacao()
    engine = _engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.nr_chamado, c.assunto_html, c.motivo_abertura_html
            FROM chamados_tecnuv c
            LEFT JOIN chamado_classificacao cc ON cc.nr_chamado = c.nr_chamado
            WHERE cc.nr_chamado IS NULL
            ORDER BY c.data_abertura DESC NULLS LAST
            LIMIT :lim
        """), {"lim": limite}).fetchall()
    count = 0
    for row in rows:
        classificar_chamado(row[0], row[1], row[2])
        count += 1
    return count


def _dias_aberto(data_abertura) -> Optional[int]:
    if data_abertura is None:
        return None
    if isinstance(data_abertura, str):
        try:
            data_abertura = datetime.fromisoformat(data_abertura.replace("Z", "+00:00")[:19])
        except Exception:
            return None
    try:
        delta = datetime.now() - data_abertura
        return max(0, delta.days)
    except Exception:
        return None


def obter_alertas_sla(dias_alerta: Optional[list] = None) -> list:
    """
    Retorna lista de chamados em alerta de SLA.
    Cada item: { nr_chamado, tipo, data_abertura, dias_aberto, limite_dias, severidade }.
    dias_alerta: ex. [10, 15, 60] para considerar esses limites (usa SLA_DIAS por tipo se None).
    """
    _criar_tabela_classificacao()
    engine = _engine()
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT c.nr_chamado, c.data_abertura, COALESCE(cc.tipo, 'ERRO') as tipo
            FROM chamados_tecnuv c
            LEFT JOIN {TABELA_CLASSIFICACAO} cc ON cc.nr_chamado = c.nr_chamado
            WHERE c.data_encerramento IS NULL
            ORDER BY c.data_abertura ASC NULLS LAST
        """)).fetchall()

    alertas = []
    for row in rows:
        nr, data_abertura, tipo = row[0], row[1], row[2] or "ERRO"
        dias = _dias_aberto(data_abertura)
        if dias is None:
            continue
        limites = dias_alerta or SLA_DIAS.get(tipo, [10, 15, 60])
        for lim in limites:
            if dias >= lim:
                severidade = "critico" if lim >= 60 else "alto" if lim >= 15 else "medio"
                alertas.append({
                    "nr_chamado": nr,
                    "tipo": tipo,
                    "data_abertura": data_abertura,
                    "dias_aberto": dias,
                    "limite_dias": lim,
                    "severidade": severidade,
                })
                break  # um alerta por chamado (maior limite atingido)
    return alertas


def resumo_alertas_sla() -> dict:
    """Retorna contagem de alertas por severidade e por tipo."""
    alertas = obter_alertas_sla()
    por_severidade = {"medio": 0, "alto": 0, "critico": 0}
    por_tipo = {}
    for a in alertas:
        por_severidade[a["severidade"]] = por_severidade.get(a["severidade"], 0) + 1
        t = a["tipo"]
        por_tipo[t] = por_tipo.get(t, 0) + 1
    return {"por_severidade": por_severidade, "por_tipo": por_tipo, "total": len(alertas)}
