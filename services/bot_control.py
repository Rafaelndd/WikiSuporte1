"""
Controle centralizado do robô de varredura.
Estado: robo_state.json. Etapa atual, instrumentação e parada cooperativa.

Desde 2026-09-11 o robô tem um único modo de operação — ciclo completo
automático, uma vez por dia à meia-noite (ver motor_extracao.py). Não há
mais fila de tarefas manuais nem intervalo configurável pela UI; por isso
RASPAGENS, solicitar_raspagem() e o rate-limit por hora (pode_executar_
raspagem) foram removidos daqui — existiam só para proteger esse modo
manual/configurável, que não existe mais.
"""
import json
import os
from datetime import datetime
from typing import Optional

ARQUIVO_ESTADO = "robo_state.json"

MIN_INTERVALO_ENTRE_REQUISICOES_SEG = 5


def _estado_default():
    return {
        "ultima_execucao": None,
        "em_andamento": False,
        "etapa_atual": None,
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


def definir_etapa(etapa: Optional[str]) -> None:
    estado = ler_estado()
    estado["etapa_atual"] = etapa
    salvar_estado(estado)


def iniciar_execucao(etapa: str = "Iniciando") -> dict:
    """Marca o bot como em andamento e define a etapa. Retorna o estado."""
    estado = ler_estado()
    estado["em_andamento"] = True
    estado["etapa_atual"] = etapa
    salvar_estado(estado)
    return estado


def finalizar_execucao() -> None:
    """Marca o bot como parado, limpa etapa e grava última execução."""
    estado = ler_estado()
    estado["em_andamento"] = False
    estado["etapa_atual"] = None
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
