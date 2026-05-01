"""
API REST – WikiSuporte Migration
Backend: FastAPI
Endpoints:
  POST /importar           – upload e processamento de CSV/XLSX/ZIP
  GET  /exportar/csv       – download CSV dos dados da sessão
  GET  /exportar/xlsx      – download XLSX dos dados da sessão
  GET  /exportar/pdf       – download PDF dos dados da sessão
  GET  /relatorio          – consulta filtrada por analista/período/plantão
  GET  /health             – healthcheck
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import Cookie, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from processador import MAX_BYTES_UPLOAD, processar_arquivo

# ──────────────────────────────────────────────
# Inicialização
# ──────────────────────────────────────────────

app = FastAPI(
    title="WikiSuporte – API de Importação GoTo + Multi360",
    version="1.0.0",
    description="API REST para ingestão, processamento e exportação de relatórios GoTo e Multi360.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento em memória indexado por session_id.
# Cada cliente recebe um ID de sessão via cookie ao fazer upload.
_SESSION_DATA: dict[str, list[dict]] = {}
_SESSION_META: dict[str, dict] = {}

_SESSION_COOKIE = "ws_session_id"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_dados(session_id: str) -> list[dict]:
    return _SESSION_DATA.get(session_id, [])


def _set_dados(session_id: str, dados: list[dict], meta: dict) -> None:
    _SESSION_DATA[session_id] = dados
    _SESSION_META[session_id] = meta


def _df_from_session(
    session_id: str,
    analista: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    plantao: Optional[str] = None,
) -> pd.DataFrame:
    dados = _get_dados(session_id)
    if not dados:
        raise HTTPException(status_code=404, detail="Nenhum dado em sessão. Faça upload primeiro.")

    df = pd.DataFrame(dados)

    # Filtros dinâmicos
    if analista:
        col = _detect_agent_col(df)
        if col:
            df = df[df[col].astype(str).str.lower().str.contains(analista.lower(), na=False)]

    if data_inicio or data_fim:
        col = _detect_date_col(df)
        if col:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            if data_inicio:
                df = df[df[col] >= pd.Timestamp(data_inicio)]
            if data_fim:
                df = df[df[col] <= pd.Timestamp(data_fim).replace(hour=23, minute=59, second=59)]

    if plantao:
        if "plantao" in df.columns:
            df = df[df["plantao"].astype(str).str.lower().str.contains(plantao.lower(), na=False)]
        elif "queue_name" in df.columns:
            df = df[df["queue_name"].astype(str).str.lower().str.contains(plantao.lower(), na=False)]

    return df


def _detect_agent_col(df: pd.DataFrame) -> Optional[str]:
    for c in ("agent_name", "atendente", "participantes"):
        if c in df.columns:
            return c
    return None


def _detect_date_col(df: pd.DataFrame) -> Optional[str]:
    for c in ("contact_creation_time", "data_chamada", "data_inicio", "data_importacao"):
        if c in df.columns:
            return c
    return None


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@app.get("/health", tags=["Status"])
def health():
    """Verifica se a API está no ar."""
    return {"status": "ok"}


@app.post(
    "/importar",
    tags=["Importação"],
    summary="Upload e processamento de arquivo CSV/XLSX/ZIP",
    responses={
        200: {"description": "Processamento bem-sucedido"},
        400: {"description": "Arquivo inválido ou fora do padrão"},
        413: {"description": "Arquivo excede o limite de tamanho"},
    },
)
async def importar(
    arquivo: UploadFile = File(...),
    response: Response = None,
    ws_session_id: Optional[str] = Cookie(None, alias=_SESSION_COOKIE),
):
    """
    Recebe um arquivo CSV, XLSX ou ZIP (multipart/form-data).
    - Valida tamanho (máx. `MAX_BYTES_UPLOAD_IMPORTACAO`, padrão 10 MB).
    - Detecta automaticamente o tipo (GoTo Agent Calls / GoTo Conversations / Multi360).
    - Processa, limpa e normaliza os dados.
    - Retorna JSON com status, preview (15 linhas) e metadados.
    - Define um cookie de sessão para isolamento de dados por usuário.
    """
    conteudo = await arquivo.read()

    # Validação de tamanho
    if len(conteudo) > MAX_BYTES_UPLOAD:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Limite: {MAX_BYTES_UPLOAD // (1024*1024)} MB.",
        )

    # Validação de extensão
    nome = arquivo.filename or "upload"
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in ("csv", "xlsx", "zip"):
        raise HTTPException(
            status_code=400,
            detail="Formato não suportado. Envie um arquivo .csv, .xlsx ou .zip.",
        )

    try:
        resultado = processar_arquivo(conteudo, nome)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar arquivo: {exc}") from exc

    # Gera ou reutiliza o ID de sessão do usuário
    session_id = ws_session_id or str(uuid.uuid4())

    _set_dados(
        session_id,
        resultado["dados"],
        {
            "tipo": resultado["tipo"],
            "total_registros": resultado["total_registros"],
            "colunas": resultado["colunas"],
        },
    )

    resp_data = {
        "status": "ok",
        "tipo": resultado["tipo"],
        "total_registros": resultado["total_registros"],
        "colunas": resultado["colunas"],
        "preview": resultado["preview"],
    }
    json_resp = JSONResponse(content=resp_data)
    json_resp.set_cookie(
        key=_SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=3600,
    )
    return json_resp


@app.get(
    "/relatorio",
    tags=["Relatórios"],
    summary="Consulta filtrada por analista, período ou plantão",
)
def relatorio(
    analista: Optional[str] = Query(None, description="Filtra por nome do analista/atendente"),
    data_inicio: Optional[date] = Query(None, description="Data inicial (AAAA-MM-DD)"),
    data_fim: Optional[date] = Query(None, description="Data final (AAAA-MM-DD)"),
    plantao: Optional[str] = Query(None, description="Filtra por nome do plantão / fila"),
    ws_session_id: Optional[str] = Cookie(None, alias=_SESSION_COOKIE),
):
    """
    Retorna registros filtrados com base nos parâmetros fornecidos.
    Requer que um arquivo tenha sido importado previamente.
    """
    if not ws_session_id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada. Faça upload primeiro.")
    df = _df_from_session(ws_session_id, analista, data_inicio, data_fim, plantao)
    df = df.where(pd.notnull(df), None)
    return {
        "total_registros": len(df),
        "colunas": list(df.columns),
        "dados": df.to_dict(orient="records"),
    }


@app.get(
    "/exportar/csv",
    tags=["Exportação"],
    summary="Download dos dados em CSV",
    response_class=Response,
)
def exportar_csv(
    analista: Optional[str] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    plantao: Optional[str] = Query(None),
    ws_session_id: Optional[str] = Cookie(None, alias=_SESSION_COOKIE),
):
    """Exporta os dados processados (com filtros opcionais) no formato CSV."""
    if not ws_session_id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada. Faça upload primeiro.")
    df = _df_from_session(ws_session_id, analista, data_inicio, data_fim, plantao)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dados_tratados.csv"},
    )


@app.get(
    "/exportar/xlsx",
    tags=["Exportação"],
    summary="Download dos dados em Excel (.xlsx)",
    response_class=Response,
)
def exportar_xlsx(
    analista: Optional[str] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    plantao: Optional[str] = Query(None),
    ws_session_id: Optional[str] = Cookie(None, alias=_SESSION_COOKIE),
):
    """Exporta os dados processados (com filtros opcionais) no formato XLSX."""
    if not ws_session_id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada. Faça upload primeiro.")
    df = _df_from_session(ws_session_id, analista, data_inicio, data_fim, plantao)

    # Converte colunas datetime (string) de volta para datetime para melhor exibição no Excel
    for col in df.columns:
        if "time" in col.lower() or "data" in col.lower() or "date" in col.lower():
            try:
                df[col] = pd.to_datetime(df[col], errors="ignore")
            except Exception:
                pass

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados Tratados")
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=dados_tratados.xlsx"},
    )


@app.get(
    "/exportar/pdf",
    tags=["Exportação"],
    summary="Download dos dados em PDF",
    response_class=Response,
)
def exportar_pdf(
    analista: Optional[str] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    plantao: Optional[str] = Query(None),
    ws_session_id: Optional[str] = Cookie(None, alias=_SESSION_COOKIE),
):
    """
    Exporta os dados processados em PDF (tabela HTML convertida).
    Requer a biblioteca `weasyprint` instalada.
    """
    if not ws_session_id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada. Faça upload primeiro.")
    df = _df_from_session(ws_session_id, analista, data_inicio, data_fim, plantao)

    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="Exportação PDF indisponível. Instale 'weasyprint' no servidor.",
        ) from exc

    html_table = df.to_html(index=False, border=1, classes="report-table")
    html_content = f"""
    <!DOCTYPE html>
    <html><head>
    <meta charset="UTF-8">
    <style>
      body {{ font-family: Arial, sans-serif; font-size: 9px; }}
      .report-table {{ border-collapse: collapse; width: 100%; }}
      .report-table th, .report-table td {{ border: 1px solid #ccc; padding: 3px 6px; }}
      .report-table th {{ background: #2563eb; color: #fff; }}
      .report-table tr:nth-child(even) {{ background: #f3f4f6; }}
    </style>
    </head><body>
    <h3>Relatório de Dados Tratados</h3>
    {html_table}
    </body></html>
    """
    buf = io.BytesIO()
    HTML(string=html_content).write_pdf(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=dados_tratados.pdf"},
    )


# ──────────────────────────────────────────────
# Servir frontend estático (opcional)
# ──────────────────────────────────────────────

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
