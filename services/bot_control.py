"""
Controle centralizado dos bots de varredura.
Estado: robo_state.json. Raspagens individuais, segurança e etapas.
"""
import json
import os
from datetime import datetime
from typing import Optional

ARQUIVO_ESTADO = "robo_state.json"

# Chaves para cada tipo de raspagem (usadas pelo motor e pela UI)
RASPAGENS = {
    "chamados": {"label": "Chamados Tecnuv", "icon": "📋"},
    "tickets": {"label": "Tickets EPSY", "icon": "🎫"},
    "releases": {"label": "Releases", "icon": "🧩"},
    "plantoes": {"label": "Plantões", "icon": "📅"},
    "manuais": {"label": "Manuais", "icon": "📚"},
    "wikis": {"label": "Wikis", "icon": "📖"},
    "email": {"label": "Email Empresa", "icon": "📧"},
}

# Segurança: limites para não sobrecarregar o servidor Tecnuv
MIN_INTERVALO_MINUTOS = 30
MAX_RASPAGENS_POR_HORA = 3
MIN_INTERVALO_ENTRE_REQUISICOES_SEG = 5
HORARIOS_FIXOS_PADRAO = ["00:00", "12:00"]


def _estado_default():
    return {
        "ultima_execucao": None,
        "em_andamento": False,
        "auto_ativo": True,
        "intervalo": 60,
        "etapa_atual": None,
        "tarefa_solicitada": None,
        "raspagens_por_hora": 0,
        "ultima_raspagem_hora": None,
        "min_intervalo": MIN_INTERVALO_MINUTOS,
        "max_raspagens_hora": MAX_RASPAGENS_POR_HORA,
        "horario_inicio": None,
        "horario_fim": None,
        "horarios_fixos": HORARIOS_FIXOS_PADRAO.copy(),
        "janela_execucao_min": 20,
        "parar_solicitada": False,
    }


def ler_estado() -> dict:
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in _estado_default().items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return _estado_default().copy()


def salvar_estado(estado: dict) -> None:
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)


def pode_executar_raspagem(estado: dict) -> tuple[bool, str]:
    """Retorna (pode_executar, motivo_se_nao)."""
    if estado.get("em_andamento"):
        return False, "Uma varredura já está em execução."
    now = datetime.now()
    # Reset contador por hora
    ultima_h = estado.get("ultima_raspagem_hora")
    if ultima_h:
        try:
            dt = datetime.fromisoformat(ultima_h)
            if (now - dt).total_seconds() > 3600:
                estado["raspagens_por_hora"] = 0
                estado["ultima_raspagem_hora"] = None
                salvar_estado(estado)
        except Exception:
            pass
    if estado.get("raspagens_por_hora", 0) >= estado.get("max_raspagens_hora", MAX_RASPAGENS_POR_HORA):
        return False, f"Limite de {estado.get('max_raspagens_hora')} raspagens/hora atingido. Aguarde."
    ultima = estado.get("ultima_execucao")
    if ultima:
        try:
            dt_ultima = datetime.fromisoformat(ultima)
            min_intervalo = estado.get("min_intervalo", MIN_INTERVALO_MINUTOS) * 60
            if (now - dt_ultima).total_seconds() < min_intervalo:
                return False, f"Aguarde {min_intervalo // 60} min entre raspagens para não sobrecarregar o servidor."
        except Exception:
            pass
    return True, ""


def solicitar_raspagem(tipo: str) -> tuple[bool, str]:
    """Solicita execução de uma raspagem específica. Retorna (ok, msg)."""
    estado = ler_estado()
    ok, motivo = pode_executar_raspagem(estado)
    if not ok:
        return False, motivo
    if tipo not in RASPAGENS:
        return False, f"Tipo de raspagem inválido: {tipo}"
    estado["tarefa_solicitada"] = tipo
    salvar_estado(estado)
    return True, f"Raspagem de {RASPAGENS[tipo]['label']} solicitada."


def definir_etapa(etapa: Optional[str]) -> None:
    estado = ler_estado()
    estado["etapa_atual"] = etapa
    salvar_estado(estado)


def consumir_tarefa() -> Optional[str]:
    """
    Lê e consome a tarefa solicitada (seta None depois de ler).
    Retorna o tipo de raspagem ou None se não houver.
    """
    estado = ler_estado()
    tarefa = estado.get("tarefa_solicitada")
    if tarefa:
        estado["tarefa_solicitada"] = None
        salvar_estado(estado)
    return tarefa


def iniciar_execucao(etapa: str = "Iniciando") -> dict:
    """Marca o bot como em andamento, define etapa, incrementa contadores. Retorna o estado."""
    estado = ler_estado()
    estado["em_andamento"] = True
    estado["etapa_atual"] = etapa
    agora = datetime.now()
    if not estado.get("ultima_raspagem_hora"):
        estado["ultima_raspagem_hora"] = agora.isoformat()
    estado["raspagens_por_hora"] = estado.get("raspagens_por_hora", 0) + 1
    salvar_estado(estado)
    return estado


def finalizar_execucao() -> None:
    """Marca o bot como parado, limpa etapa e grava última execução."""
    estado = ler_estado()
    estado["em_andamento"] = False
    estado["etapa_atual"] = None
    estado["tarefa_solicitada"] = None
    estado["parar_solicitada"] = False
    estado["ultima_execucao"] = datetime.now().isoformat()
    salvar_estado(estado)


def solicitar_parada_bots() -> None:
    """Pedido cooperativo: o motor / ciclo de chamados deve encerrar na próxima verificação."""
    estado = ler_estado()
    estado["parar_solicitada"] = True
    salvar_estado(estado)


def forcar_estado_parado() -> None:
    """
    Grava no JSON que o motor está parado. Use quando:
    - o terminal do motor foi fechado (em_andamento ficou preso em True);
    - a UI precisa voltar a permitir raspagens.
    Não mata processo em segundo plano — só corrige o arquivo de estado.
    """
    estado = ler_estado()
    estado["em_andamento"] = False
    estado["etapa_atual"] = None
    estado["tarefa_solicitada"] = None
    estado["parar_solicitada"] = False
    estado["ultima_execucao"] = datetime.now().isoformat()
    salvar_estado(estado)


def processo_motor_provavelmente_ativo() -> bool:
    """
    True se existir processo Python com motor_extracao no comando.
    Ajuda a detectar estado 'Executando' fantasma (JSON preso sem processo).
    """
    try:
        import psutil
    except ImportError:
        return True  # sem psutil, não adivinhar — assume ativo se JSON disser
    alvo = "motor_extracao"
    for p in psutil.process_iter(attrs=["name", "cmdline"]):
        try:
            cmd = p.info.get("cmdline") or []
            line = " ".join(str(c) for c in cmd).lower()
            if alvo in line and "python" in line:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def sincronizar_estado_se_motor_morto() -> bool:
    """
    Se JSON diz 'em_andamento' mas não há processo do motor, força parado.
    Retorna True se corrigiu o estado.
    """
    estado = ler_estado()
    if not estado.get("em_andamento"):
        return False
    if processo_motor_provavelmente_ativo():
        return False
    forcar_estado_parado()
    return True


def deve_parar() -> bool:
    return bool(ler_estado().get("parar_solicitada"))


def _parse_hhmm(valor: str) -> tuple[int, int] | None:
    try:
        hh_str, mm_str = (valor or "").strip().split(":")
        hh = int(hh_str)
        mm = int(mm_str)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        return None
    return None


def deve_executar_no_horario_fixo(estado: dict, agora: Optional[datetime] = None) -> tuple[bool, str]:
    """
    Verifica se o ciclo automático deve rodar no momento, baseado em horários fixos.
    Executa no máximo uma vez por slot diário (ex.: 00:00 e 12:00).
    """
    now = agora or datetime.now()
    horarios = estado.get("horarios_fixos") or HORARIOS_FIXOS_PADRAO
    janela_min = int(estado.get("janela_execucao_min", 20) or 20)

    ultima_exec = None
    ultima_exec_str = estado.get("ultima_execucao")
    if ultima_exec_str:
        try:
            ultima_exec = datetime.fromisoformat(ultima_exec_str)
        except Exception:
            ultima_exec = None

    for horario in horarios:
        parsed = _parse_hhmm(horario)
        if not parsed:
            continue
        hh, mm = parsed
        slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta_seg = (now - slot).total_seconds()
        # Roda apenas dentro da janela após o horário definido.
        if 0 <= delta_seg <= janela_min * 60:
            if not ultima_exec or ultima_exec < slot:
                return True, horario
    return False, ""
