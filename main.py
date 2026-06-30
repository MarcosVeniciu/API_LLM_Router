from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager
import httpx

from core.config import __version__, ALLOWED_DOMAINS, ALL_MODELS
from core.state import model_active_requests
from infrastructure.dashboard import live_dashboard
from api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa estado
    for m in ALL_MODELS:
        model_active_requests[m] = 0
    app.state.http_client = httpx.AsyncClient()
    task = asyncio.create_task(live_dashboard())
    yield
    task.cancel()
    await app.state.http_client.aclose()

app = FastAPI(title="LLM Router - Educampo", version=__version__, lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    for error in exc.errors():
        if error.get("type") == "json_invalid":
            return JSONResponse(status_code=400, content={"detail": "JSON inválido"})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_DOMAINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)