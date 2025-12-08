import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from rich.logging import RichHandler

from app.api.v2.api import router as api_v2_router
from app.core.config import settings


def configure_logging():
    logging.basicConfig(
        level="INFO",
        format="[blue]%(name)s[/]  %(message)s", 
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
        force=True
    )

    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True
        
    if not settings.USE_API_KEY:
        logging.getLogger(__name__).warning("API Key authentication is DISABLED. Do not use in production environments.")

app = FastAPI(
    title="Proxy Generator",
    docs_url="/api/v2/docs",
    openapi_url="/api/v2/openapi.json"
)

app.add_event_handler("startup", configure_logging)

app.include_router(api_v2_router, prefix="/api/v2")