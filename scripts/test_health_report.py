"""Gera um resumo de saude a partir do relatorio JUnit do pytest."""

from __future__ import annotations

import argparse
import statistics
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

XML_DEFAULT = Path("test-reports/pytest-report.xml")


def _ascii_safe(valor: str) -> str:
    valor = re.sub(r"\\U[0-9A-Fa-f]{8}|\\u[0-9A-Fa-f]{4}", "?", valor)
    valor = re.sub(r"\\x[0-9A-Fa-f]{2}", "?", valor)
    return re.sub(r"[^\x00-\x7F]", "?", valor)


def _to_float(valor: str | None) -> float:
    try:
        return float(valor or "0")
    except (TypeError, ValueError):
        return 0.0


def _formatar_tempo(segundos: float) -> str:
    return f"{segundos:.2f}s"


def parse_report(path: Path) -> Tuple[dict, List[Tuple[str, float]]]:
    root = ET.parse(path).getroot()
    suite = root.find("testsuite")
    if suite is None:
        raise ValueError(f"XML de pytest invalido: {path}")

    total = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    tempo_total = _to_float(suite.attrib.get("time"))

    casos: List[Tuple[str, float]] = []
    for tc in suite.findall("testcase"):
        nome = tc.attrib.get("name", "")
        classe = tc.attrib.get("classname", "")
        tempo = _to_float(tc.attrib.get("time"))
        casos.append((f"{classe}::{nome}", tempo))

    return (
        {
            "total": total,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "time": tempo_total,
            "passed": total - failures - errors - skipped,
        },
        casos,
    )


def gerar_resumo(stats: dict, casos: List[Tuple[str, float]], limite_lento: float = 3.0, top: int = 10) -> str:
    total = stats["total"]
    if total <= 0:
        return "Relatorio vazio: nenhum teste encontrado."

    failures = stats["failures"]
    errors = stats["errors"]
    skipped = stats["skipped"]
    passed = stats["passed"]
    tempo_total = stats["time"]
    taxa = (passed / total) * 100 if total else 0.0

    tempos = [tempo for _, tempo in casos]
    mais_lentos = sorted(casos, key=lambda item: item[1], reverse=True)[:top]
    tempo_medio = statistics.mean(tempos) if tempos else 0.0
    tempo_maximo = max(tempos) if tempos else 0.0

    if failures or errors:
        status = "NEGATIVO"
    elif skipped > 0:
        status = "ATENCAO"
    elif tempo_maximo >= limite_lento:
        status = "ATENCAO"
    else:
        status = "POSITIVO"

    linhas = [
        "=== RELATORIO DE SAUDE DOS TESTES ===",
        f"Arquivo: {XML_DEFAULT}",
        f"Status de saude: {status}",
        "",
        f"Total de testes: {total}",
        f"Passou: {passed}",
        f"Falhou: {failures}",
        f"Erro: {errors}",
        f"Pulado: {skipped}",
        f"Taxa de sucesso: {taxa:.2f}%",
        f"Duracao total: {_formatar_tempo(tempo_total)}",
        f"Tempo medio por teste: {_formatar_tempo(tempo_medio)}",
        f"Teste mais lento: {_formatar_tempo(tempo_maximo)}",
        "",
    ]

    if tempo_maximo:
        if status == "POSITIVO":
            linhas.append("Pontos de atencao: nenhum ponto critico identificado.")
        else:
            linhas.append("Pontos de atencao:")
            if failures or errors:
                linhas.append("- Existem falhas/erros de execucao. Resultado NEGATIVO do gate de QA.")
            if skipped:
                linhas.append("- Ha testes pulados; validar se a cobertura continua intencional.")
            if tempo_maximo >= limite_lento:
                linhas.append(f"- Ha testes acima do limiar de {limite_lento:.1f}s (sinal de risco de desempenho de regressao).")

            for nome, duracao in mais_lentos:
                if duracao < limite_lento:
                    continue
                linhas.append(f"  * {_ascii_safe(nome)} -> {_formatar_tempo(duracao)}")
    linhas.append("")
    linhas.append(f"Top {top} mais lentos:")
    if mais_lentos:
        for idx, (nome, duracao) in enumerate(mais_lentos, start=1):
            if idx > top:
                break
            linhas.append(f"{idx:2d}. {_formatar_tempo(duracao)} | {_ascii_safe(nome)}")
    else:
        linhas.append("- Nenhum teste encontrado")

    return "\n".join(linhas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumo de saude para relatorio JUnit do pytest")
    parser.add_argument(
        "xml_path",
        nargs="?",
        default=str(XML_DEFAULT),
        help="Caminho do arquivo junitxml (ex.: test-reports/pytest-report.xml)",
    )
    parser.add_argument(
        "--limite-lento",
        type=float,
        default=3.0,
        help="Tempo limite (segundos) para considerar teste lento",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Quantidade de testes mais lentos a listar",
    )
    args = parser.parse_args()

    path = Path(args.xml_path)
    if not path.exists():
        print(f"Relatorio nao encontrado: {path}")
        print("Execute antes: python -m pytest --junitxml=test-reports/pytest-report.xml")
        return 1

    stats, casos = parse_report(path)
    if not stats["total"]:
        print("Relatorio vazio: nenhum teste encontrado.")
        return 2

    print(gerar_resumo(stats, casos, limite_lento=args.limite_lento, top=args.top))
    if stats["failures"] + stats["errors"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
