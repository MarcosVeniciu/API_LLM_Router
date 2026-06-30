import pytest
import httpx
import os
import asyncio
from httpx import ASGITransport

from dotenv import load_dotenv

load_dotenv()

# Função auxiliar para testes
def clean_env_str(val: str) -> str:
    return val.strip().replace('"', '').replace("'", "").replace("[", "").replace("]", "")

# Configurações do teste
ROUTER_SECRET_KEY = clean_env_str(os.getenv("ROUTER_SECRET_KEY", "chave_secreta_educampo_123"))
API_URL = "http://localhost:8000/analise_severidade/v1/chat/completions"

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
    NUM_REQUESTS = 5  # Reduzido de 30 para 5 para não abusar do Rate Limit dos modelos gratuitos em testes unitários
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [_send_request(client, i) for i in range(1, NUM_REQUESTS + 1)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Como estamos usando provedores gratuitos, a concorrência pode causar Rate Limit em todos os modelos.
        # Nesse caso, nosso Router deve responder 503 (Nenhum modelo disponível) graciosamente, ou 200 (Sucesso).
        sucessos = 0
        falhas_esperadas = 0
        for r in results:
            if isinstance(r, Exception):
                continue
            if r.status_code == 200:
                sucessos += 1
            elif r.status_code == 503:
                falhas_esperadas += 1
                
        assert (sucessos + falhas_esperadas) == NUM_REQUESTS, f"Algumas requisições falharam com erros inesperados. Sucessos: {sucessos}, 503s: {falhas_esperadas}"

@pytest.mark.asyncio
async def test_rpm_tracking():
    """
    Testa se o sistema rastreia as Requisições Por Minuto (RPM) corretamente.
    Ao contrário da lógica antiga de concorrência, o RPM deve se manter incrementado 
    mesmo após a requisição finalizar (pois ainda está na janela de 60 segundos).
    """
    from main import app
    from core.state import request_timestamps, get_current_rpm
    from core.config import ALL_MODELS as MODELS
    
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ROUTER_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "stream": False,
        "messages": [{"role": "user", "content": "Responda apenas 'teste'."}]
    }
    
    # Coleta o RPM inicial
    initial_rpm = sum(get_current_rpm(m) for m in MODELS)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Executa a requisição real de forma síncrona/blocking pro cliente
        res = await client.post("/analise_severidade/v1/chat/completions", headers=headers, json=payload, timeout=60.0)
        assert res.status_code == 200, f"A requisição falhou com status {res.status_code}"
                
    # Após a requisição terminar, o timestamp deve continuar na janela de 60s
    final_rpm = sum(get_current_rpm(m) for m in MODELS)
    assert final_rpm > initial_rpm, "O contador de RPM deve manter o incremento na janela de 60 segundos mesmo após a requisição finalizar."

@pytest.mark.asyncio
async def test_dynamic_rpm_and_cooldown():
    """
    Testa a Abordagem Híbrida de limitação de RPM real e Cooldown.
    Garante que se o RPM atingir o model_real_rpm_limit, o modelo seja preterido,
    e que modelos em cooldown não sejam selecionados.
    """
    import time
    from core.config import ALL_MODELS as MODELS
    from domain.routing import get_best_model
    from core.state import request_timestamps, model_real_rpm_limit, model_cooldown
    
    # Reseta o estado
    for m in MODELS:
        request_timestamps[m].clear()
        model_real_rpm_limit[m] = float('inf')
        model_cooldown[m] = 0.0
        
    model_a = MODELS[0]
    
    # Simula o cooldown do model_a
    model_cooldown[model_a] = time.time() + 60.0
    
    # model_a não deve ser escolhido, pois está em cooldown
    best = get_best_model(MODELS)
    assert best != model_a, "Modelo em cooldown não deveria ser escolhido"
    
    # Remove cooldown
    model_cooldown[model_a] = 0.0
    
    # Simula o alcance do limite dinâmico (limite real = 2)
    model_real_rpm_limit[model_a] = 2
    # Adiciona 2 requisições recentes
    now = time.time()
    request_timestamps[model_a].append(now - 10)
    request_timestamps[model_a].append(now - 5)
    
    # model_a tem 2 requisições, logo RPM atual (2) >= model_real_rpm_limit (2). Não deve ser selecionado.
    best_2 = get_best_model(MODELS)
    assert best_2 != model_a, "Modelo que atingiu limite RPM real não deveria ser selecionado"

@pytest.mark.asyncio
async def test_fair_queue_and_jitter():
    """
    Testa a cota justa por cliente e o sistema de Jitter (Retry-After) quando a fila máxima é atingida.
    Como usamos o cliente 'teste-pesado' (chave_teste_pesado_789), ele tem um limite de requisições baseado
    no tamanho da fila. Vamos simular várias requisições concorrentes que excedem a cota.
    """
    from main import app
    from core.state import client_active_requests
    from domain.routing import MAX_QUEUE_SIZE
    
    transport = ASGITransport(app=app)
    # Chave para o cliente 'teste-pesado' configurada no clients.json
    headers = {"Authorization": "Bearer chave_teste_pesado_789", "Content-Type": "application/json"}
    payload = {
        "stream": False,
        "messages": [{"role": "user", "content": "Teste."}]
    }
    
    # O peso desse cliente no json é 2.0. Então sua cota é MAX_QUEUE_SIZE * 2.0.
    # Vamos enviar mais do que essa quantidade de requisições simultâneas.
    NUM_REQUESTS = int(MAX_QUEUE_SIZE * 2.0) + 5
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Precisamos simular requests que fiquem presas ou apenas disparar tudo ao mesmo tempo.
        tasks = [client.post("/analise_severidade/v1/chat/completions", headers=headers, json=payload, timeout=60.0) for _ in range(NUM_REQUESTS)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        status_429_count = 0
        tem_retry_after = False
        
        for r in results:
            if isinstance(r, Exception):
                continue
            if r.status_code == 429:
                status_429_count += 1
                if "Retry-After" in r.headers:
                    tem_retry_after = True
                    # Verifica se o Jitter está no range configurado (1 a 5)
                    retry_val = int(r.headers["Retry-After"])
                    assert 1 <= retry_val <= 5, f"Jitter fora do limite: {retry_val}"
                    
        # Esperamos que pelo menos 5 requisições tenham retornado 429
        assert status_429_count > 0, "O sistema não rejeitou requisições com 429 apesar de exceder a cota justa."
        assert tem_retry_after, "O cabeçalho 'Retry-After' não foi incluído na resposta 429."
        
        # Garante que o contador de requisições ativas do cliente zerou após o término
        assert client_active_requests.get("teste-pesado", 0) == 0, "Vazamento de memória no contador de fila do cliente."

@pytest.mark.asyncio
async def test_tps_fallback_no_usage():
    """
    [Domain Context] Roteamento Dinâmico: Resolve a falha do TPS travar em 1000.0
    Testa se o TPS é atualizado quando a resposta da API não contém o bloco 'usage' 
    (simulando hit de cache ou provedores limitados).
    O fallback deve calcular os tokens com base na heurística len(content) / 4.
    """
    from main import app
    from core.state import model_tps
    from core.config import ALL_MODELS as MODELS
    from unittest.mock import patch, MagicMock
    import time
    
    # Reseta TPS para 1000.0 em todos
    for m in MODELS:
        model_tps[m] = 1000.0
        
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ROUTER_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "stream": False,
        "messages": [{"role": "user", "content": "Teste fallback de TPS."}]
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Esta é uma resposta fictícia moderadamente longa para simular o fallback de cálculo de tokens gerados com base em caracteres."}}]
        # Observe que não há chave "usage" aqui.
    }
    
    import httpx
    original_post = httpx.AsyncClient.post
    
    async def side_effect_post(self, url, *args, **kwargs):
        if "openrouter.ai" in str(url):
            return mock_response
        return await original_post(self, url, *args, **kwargs)
    
    with patch("httpx.AsyncClient.post", new=side_effect_post):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/analise_severidade/v1/chat/completions", headers=headers, json=payload, timeout=5.0)
            assert res.status_code == 200
            
    # Ao menos um modelo deve ter o TPS alterado (pois o fallback preencheu os tokens)
    tps_atualizado = any(model_tps[m] != 1000.0 for m in MODELS)
    assert tps_atualizado, "O TPS não foi atualizado! O fallback heurístico (content / 4) falhou ao substituir o usage inexistente."

@pytest.mark.asyncio
async def test_split_margin_variables():
    """
    [Domain Context] Roteamento Dinâmico: Verifica se as variáveis de margem global 
    e limiar de RPM individual foram separadas com sucesso e são independentes.
    
    Verifica se:
    1. GLOBAL_CONCURRENT_MARGIN e MODEL_RPM_BURST_THRESHOLD são carregados corretamente.
    2. MAX_CONCURRENT é derivado de GLOBAL_CONCURRENT_MARGIN.
    """
    from core.config import GLOBAL_CONCURRENT_MARGIN, MODEL_RPM_BURST_THRESHOLD, ALL_MODELS
    from domain.routing import MAX_CONCURRENT
    
    assert GLOBAL_CONCURRENT_MARGIN is not None
    assert MODEL_RPM_BURST_THRESHOLD is not None
    assert MAX_CONCURRENT == min(100, max(1, (len(ALL_MODELS) - GLOBAL_CONCURRENT_MARGIN) * MODEL_RPM_BURST_THRESHOLD))