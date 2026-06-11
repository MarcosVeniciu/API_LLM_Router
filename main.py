from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import os
import json
import time
from collections import deque

app = FastAPI(title="LLM Router - Educampo")

# ==========================================
# 1. VARIÁVEIS DE AMBIENTE (CONFIGURAÇÕES)
# ==========================================

# Função auxiliar para limpar aspas injetadas pelo Docker
def clean_env_str(val: str) -> str:
    return val.strip().replace('"', '').replace("'", "").replace("[", "").replace("]", "")

ROUTER_SECRET_KEY = clean_env_str(os.getenv("ROUTER_SECRET_KEY", "chave_secreta_educampo_123"))
OPENROUTER_API_KEY = clean_env_str(os.getenv("OPENROUTER_API_KEY", "sk-or-v1-..."))

# Carrega a lista de modelos de uma string separada por vírgula
MODELS_ENV = clean_env_str(os.getenv("MODELS", "openrouter/free"))
MODELS = [m.strip() for m in MODELS_ENV.split(",") if m.strip()]

# Margem de segurança e Preset
MODEL_MARGIN = int(clean_env_str(os.getenv("MODEL_MARGIN", "4")))
OPENROUTER_PRESET = clean_env_str(os.getenv("OPENROUTER_PRESET", "preset_padrao_educampo"))

# Domínios permitidos (CORS)
ALLOWED_DOMAINS_ENV = clean_env_str(os.getenv("ALLOWED_DOMAINS", "*"))
ALLOWED_DOMAINS = [d.strip() for d in ALLOWED_DOMAINS_ENV.split(",") if d.strip()]

APP_NAME = clean_env_str(os.getenv("APP_NAME", "API_LLM_Router"))
APP_URL = clean_env_str(os.getenv("APP_URL", "none"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_DOMAINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. ESTADO EM MEMÓRIA (IN-FLIGHT E VELOCIDADE)
# ==========================================
# Rastreador de requisições por minuto (RPM) usando janela deslizante (sliding window)
request_timestamps = {model: deque() for model in MODELS}

def get_current_rpm(model: str) -> int:
    """
    Calcula o número de Requisições Por Minuto (RPM) para o modelo.
    Remove da fila (deque) os timestamps mais antigos que 60 segundos.
    """
    current_time = time.time()
    while request_timestamps[model] and request_timestamps[model][0] < current_time - 60:
        request_timestamps[model].popleft()
    return len(request_timestamps[model])

# Rastreador de Velocidade (TPS - Tokens Por Segundo)
# Começamos todos com TPS "infinito" (ou um número alto) para que todos 
# sejam testados pelo menos uma vez na primeira rodada.
model_tps = {model: 1000.0 for model in MODELS}


# ==========================================
# 3. LÓGICA DE ROTEAMENTO (ALGORITMO DINÂMICO)
# ==========================================
def get_best_model():
    """Escolhe o melhor modelo baseado em TPS em tempo real e na Margem (RPM)"""
    
    # Ordena a lista de modelos do MAIS RÁPIDO para o MAIS LENTO no momento atual
    modelos_ordenados_por_tps = sorted(MODELS, key=lambda m: model_tps.get(m, 0), reverse=True)
    
    # Fase 1: Verifica os modelos (do mais rápido para o mais lento). 
    # Se algum estiver abaixo da margem de RPM (ex: < 4), pega ele na hora.
    for model in modelos_ordenados_por_tps:
        if get_current_rpm(model) < MODEL_MARGIN:
            return model
            
    # Fase 2: Todos estouraram a margem. Transbordamento igualitário.
    # Pega o modelo com o menor RPM no último minuto.
    best_model = min(MODELS, key=lambda m: get_current_rpm(m))
    return best_model


# ==========================================
# ROTA DE HEALTHCHECK (LEVE PARA O DOCKER)
# ==========================================
@app.get("/health")
async def health_check():
    # Retorna uma resposta simples e ultraleve apenas para dizer que a API está viva
    return {"status": "ok"}

# ==========================================
# 4. AUTENTICAÇÃO INTERNA
# ==========================================
security = HTTPBearer(auto_error=False)

async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials != ROUTER_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Não autorizado")


# ==========================================
# 5. ENDPOINT PRINCIPAL (PROXY E CÁLCULO DE TPS)
# ==========================================
@app.post("/v1/chat/completions", dependencies=[Depends(verify_auth)])
async def route_llm_request(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    selected_model = get_best_model()
    body["model"] = selected_model
    body["preset"] = OPENROUTER_PRESET 

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_URL,
        "X-OpenRouter-Title": APP_NAME
    }

    # ADICIONE ESTA LINHA PARA DEBUG:
    print(f"[-] DEBUG HEADERS: Referer: '{APP_URL}', Title: '{APP_NAME}'")
    # Verifica se o cliente pediu streaming
    is_stream = body.get("stream", False)

    start_time = time.time()
    request_timestamps[selected_model].append(start_time)
    print(f"[+] INÍCIO [{selected_model}] Vel: {model_tps[selected_model]:.1f} TPS | RPM: {get_current_rpm(selected_model)}")

    # ==========================================
    # ROTA A: MODO STREAMING
    # ==========================================
    if is_stream:
        async def stream_generator():
            chunk_count = 0
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=None) as response:
                        if response.status_code != 200:
                            yield await response.aread()
                            return
                        async for chunk in response.aiter_bytes():
                            chunk_count += 1
                            yield chunk
            except Exception as e:
                yield json.dumps({"error": str(e)}).encode('utf-8')
            finally:
                elapsed_time = time.time() - start_time
                if elapsed_time > 0 and chunk_count > 0:
                    current_tps = chunk_count / elapsed_time
                    historico = model_tps[selected_model]
                    model_tps[selected_model] = current_tps if historico == 1000.0 else (historico * 0.8) + (current_tps * 0.2)
                print(f"[-] FIM    [{selected_model}] Vel: {model_tps[selected_model]:.1f} TPS | RPM: {get_current_rpm(selected_model)}")
                
        return StreamingResponse(stream_generator(), media_type="application/json")

    # ==========================================
    # ROTA B: MODO NORMAL (BLOCKING)
    # ==========================================
    else:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=None)
                response_data = response.json()
                
                # Se houver erro do OpenRouter, repassamos imediatamente
                if response.status_code != 200:
                    return JSONResponse(status_code=response.status_code, content=response_data)

                # Calcula o TPS com precisão absoluta lendo o uso de tokens
                elapsed_time = time.time() - start_time
                if elapsed_time > 0 and "usage" in response_data:
                    # 'completion_tokens' são os tokens gerados pelo modelo
                    tokens_gerados = response_data["usage"].get("completion_tokens", 0)
                    if tokens_gerados > 0:
                        current_tps = tokens_gerados / elapsed_time
                        historico = model_tps[selected_model]
                        model_tps[selected_model] = current_tps if historico == 1000.0 else (historico * 0.8) + (current_tps * 0.2)
                
                return JSONResponse(content=response_data)
                
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Erro interno: {str(e)}"})
            
        finally:
            print(f"[-] FIM    [{selected_model}] Vel: {model_tps[selected_model]:.1f} TPS | RPM: {get_current_rpm(selected_model)}")