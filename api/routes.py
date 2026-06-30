from fastapi import APIRouter, Request, Depends
from domain.dto import ChatCompletionRequest
from infrastructure.llm_client import handle_chat_completions
from core.auth import verify_auth
from core.config import SEVERIDADE_MODELS, ISHIKAWA_MODELS, SEVERIDADE_OPENROUTER_PRESET, ISHIKAWA_OPENROUTER_PRESET
import httpx

router = APIRouter()

async def get_http_client(request: Request):
    if not hasattr(request.app.state, "http_client"):
        request.app.state.http_client = httpx.AsyncClient()
    return request.app.state.http_client

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.post("/analise_severidade/v1/chat/completions", dependencies=[Depends(verify_auth)])
async def route_llm_request_severidade(
    request: Request,
    body: ChatCompletionRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client)
):
    return await handle_chat_completions(
        body_dto=body,
        client_id=request.state.client_id,
        client_weight=request.state.client_weight,
        models_pool=SEVERIDADE_MODELS,
        preset=SEVERIDADE_OPENROUTER_PRESET,
        http_client=http_client
    )

@router.post("/analise_ishikawa/v1/chat/completions", dependencies=[Depends(verify_auth)])
async def route_llm_request_ishikawa(
    request: Request,
    body: ChatCompletionRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client)
):
    return await handle_chat_completions(
        body_dto=body,
        client_id=request.state.client_id,
        client_weight=request.state.client_weight,
        models_pool=ISHIKAWA_MODELS,
        preset=ISHIKAWA_OPENROUTER_PRESET,
        http_client=http_client
    )
