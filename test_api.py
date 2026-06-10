import pytest
import httpx
import os
import asyncio

from dotenv import load_dotenv

load_dotenv()

# Função auxiliar para testes
def clean_env_str(val: str) -> str:
    return val.strip().replace('"', '').replace("'", "")

# Configurações do teste
ROUTER_SECRET_KEY = clean_env_str(os.getenv("ROUTER_SECRET_KEY", "chave_secreta_educampo_123"))
API_URL = "http://localhost:8000/v1/chat/completions"

@pytest.mark.asyncio
async def test_security_no_token():
    async with httpx.AsyncClient() as client:
        res = await client.post(API_URL, json={"messages": []})
        assert res.status_code == 401

@pytest.mark.asyncio
async def test_security_wrong_token():
    headers_wrong = {"Authorization": "Bearer senha_errada"}
    async with httpx.AsyncClient() as client:
        res = await client.post(API_URL, headers=headers_wrong, json={"messages": []})
        assert res.status_code == 401

@pytest.mark.asyncio
async def test_invalid_json():
    headers_ok = {"Authorization": f"Bearer {ROUTER_SECRET_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        res = await client.post(API_URL, headers=headers_ok, content="Isso não é um JSON")
        assert res.status_code == 400

@pytest.mark.asyncio
async def test_streaming():
    headers = {"Authorization": f"Bearer {ROUTER_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "stream": True,
        "messages": [{"role": "user", "content": "Conte de 1 a 3."}]
    }
    
    chunks_received = 0
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", API_URL, headers=headers, json=payload, timeout=60.0) as response:
            assert response.status_code == 200
            async for chunk in response.aiter_bytes():
                if chunk:
                    chunks_received += 1
                    
    assert chunks_received > 0

async def _send_request(client: httpx.AsyncClient, request_id: int):
    headers = {"Authorization": f"Bearer {ROUTER_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "stream": False,
        "messages": [{"role": "user", "content": f"Responda extremamente curto: raiz de {request_id * 144}?"}]
    }
    response = await client.post(API_URL, headers=headers, json=payload, timeout=120.0)
    return response

@pytest.mark.asyncio
async def test_concurrency():
    NUM_REQUESTS = 30
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [_send_request(client, i) for i in range(1, NUM_REQUESTS + 1)]
        results = await asyncio.gather(*tasks)
        
        sucessos = sum(1 for r in results if r.status_code == 200)
        assert sucessos == NUM_REQUESTS, f"Algumas requisições falharam. Sucessos: {sucessos}/{NUM_REQUESTS}"