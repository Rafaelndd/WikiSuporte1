import json
import logging
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Métodos que devem ser auditados
AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Endpoints que não devem ser auditados (ex: health check, docs)
EXCLUDED_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra ações de escrita (POST, PUT, PATCH, DELETE)
    na tabela de auditoria do banco de dados.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Somente auditar métodos de escrita fora de paths excluídos
        if request.method not in AUDIT_METHODS:
            return response
        if request.url.path in EXCLUDED_PATHS:
            return response

        # Tentar registrar na tabela de auditoria
        try:
            from ..database import SessionLocal
            from ..models.auditoria import Auditoria
            from ..services.auth_service import decode_token

            usuario_id = None
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                token_data = decode_token(token)
                if token_data:
                    usuario_id = token_data.usuario_id

            ip_origem = request.client.host if request.client else None

            db = SessionLocal()
            try:
                auditoria = Auditoria(
                    usuario_id=usuario_id,
                    metodo=request.method,
                    endpoint=str(request.url.path),
                    status_code=response.status_code,
                    ip_origem=ip_origem,
                    criado_em=datetime.utcnow(),
                )
                db.add(auditoria)
                db.commit()
            except Exception as db_exc:
                logger.warning(f"Falha ao registrar auditoria: {db_exc}")
                db.rollback()
            finally:
                db.close()

        except Exception as exc:
            logger.warning(f"Middleware de auditoria ignorou erro: {exc}")

        return response
