from modules.models import ChamadoTecnuv


def test_chamado_tecnuv_coluna_nome_cliente():
    colunas = set(ChamadoTecnuv.__table__.c.keys())
    assert "nome_cliente" in colunas
    assert "cliente_nome" not in colunas
