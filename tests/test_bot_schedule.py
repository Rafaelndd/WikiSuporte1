from datetime import datetime

from services.bot_control import deve_executar_no_horario_fixo


def test_deve_executar_na_janela_sem_execucao_previa():
    estado = {
        "horarios_fixos": ["00:00", "12:00"],
        "janela_execucao_min": 20,
        "ultima_execucao": None,
    }
    ok, slot = deve_executar_no_horario_fixo(estado, datetime(2026, 4, 18, 12, 5, 0))
    assert ok is True
    assert slot == "12:00"


def test_nao_executa_duplicado_no_mesmo_slot():
    estado = {
        "horarios_fixos": ["00:00", "12:00"],
        "janela_execucao_min": 20,
        "ultima_execucao": "2026-04-18T12:03:00",
    }
    ok, slot = deve_executar_no_horario_fixo(estado, datetime(2026, 4, 18, 12, 10, 0))
    assert ok is False
    assert slot == ""


def test_executa_no_proximo_slot_mesmo_dia():
    estado = {
        "horarios_fixos": ["00:00", "12:00"],
        "janela_execucao_min": 20,
        "ultima_execucao": "2026-04-18T00:02:00",
    }
    ok, slot = deve_executar_no_horario_fixo(estado, datetime(2026, 4, 18, 12, 1, 0))
    assert ok is True
    assert slot == "12:00"
