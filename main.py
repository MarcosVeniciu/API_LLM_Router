from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import os
import json
import time
import random
import asyncio
from collections import deque
from contextlib import asynccontextmanager
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Group, Console
from rich import box
from datetime import datetime

# Rastreador de requisições ativas por modelo
model_active_requests = {}
# Histórico de erros recentes (limite de 5)
recent_errors = deque(maxlen=5)

def log_dashboard_error(msg: str):
    """
    Adiciona um erro ao histórico do dashboard com formatação de data/hora.
    
    Args:
        msg (str): A mensagem de erro a ser exibida.
        
    Domain Context:
        Dashboard: Mantém o registro rastreável (com timestamp) das últimas 
        falhas para observabilidade em tempo real.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    recent_errors.append(f"[{timestamp}] {msg}")

async def live_dashboard():
    """Tarefa em background para atualizar o console do Docker usando rich."""
    console = Console(force_terminal=True, color_system="standard")
    with Live(auto_refresh=False, console=console) as live:
        while True:
            try:
                # 1. Tabela de Modelos
                table = Table(title=f"LLM Router Dashboard - {datetime.now().strftime('%H:%M:%S')}", box=box.ROUNDED, expand=True)
                table.add_column("Modelo", style="cyan", no_wrap=True)
                table.add_column("Status", justify="center")
                table.add_column("Reqs Ativas", justify="right", style="magenta")
                table.add_column("Limite RPM", justify="right", style="red")
                table.add_column("RPM Atual", justify="right", style="yellow")
                table.add_column("Velocidade (TPS)", justify="right", style="green")

                for model in sorted(ALL_MODELS):
                    ativas = model_active_requests.get(model, 0)
                    limite = model_real_rpm_limit.get(model, float('inf'))
                    limite_str = str(limite) if limite != float('inf') else "∞"
                    atual = get_current_rpm(model)
                    tps = model_tps.get(model, 0.0)
                    
                    status = "[green]Disponível[/green]"
                    if time.time() < model_cooldown.get(model, 0.0):
                        status = "[red]Cooldown[/red]"
                    elif atual >= limite:
                        status = "[yellow]Limite Atingido[/yellow]"

                    table.add_row(
                        model,
                        status,
                        str(ativas),
                        limite_str,
                        str(atual),
                        f"{tps:.1f}"
                    )

                # 2. Resumo Global
                total_active = sum(model_active_requests.values())
                total_clientes_na_fila = sum(client_active_requests.values())
                esperando = max(0, total_clientes_na_fila - total_active)
                
                resumo_texto = (
                    f"[bold]Concorrência Global (Executando):[/bold] {total_active} / {MAX_CONCURRENT}\n"
                    f"[bold]Requisições em Espera (Fila):[/bold] {esperando} / {MAX_QUEUE_SIZE}"
                )
                painel_resumo = Panel(resumo_texto, title="Visão Geral", border_style="blue")

                # 3. Erros
                texto_erros = "\n".join(recent_errors) if recent_errors else "Nenhum erro recente."
                painel_erros = Panel(texto_erros, title="Últimos Erros (Top 5)", border_style="red")

                group = Group(table, painel_resumo, painel_erros)
                live.update(group, refresh=True)
            except Exception as e:
                console.print(f"[red]Erro no dashboard: {str(e)}[/red]")
            await asyncio.sleep(1.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa estado
    for m in ALL_MODELS:
        model_active_requests[m] = 0
    task = asyncio.create_task(live_dashboard())
    yield
    task.cancel()

app = FastAPI(title="LLM Router - Educampo", lifespan=lifespan)

# ==========================================
# 0. ESTADO GLOBAL DA FILA (SEMAPHORE & COTAS)
# ==========================================
active_requests_semaphore = None
client_active_requests = {}  # { "client_id": int_count }


# ==========================================
# 1. VARIÁVEIS DE AMBIENTE (CONFIGURAÇÕES)
# ==========================================

# Função auxiliar para limpar aspas injetadas pelo Docker
def clean_env_str(val: str) -> str:
    return val.strip().replace('"', '').replace("'", "").replace("[", "").replace("]", "")

ROUTER_SECRET_KEY = clean_env_str(os.getenv("ROUTER_SECRET_KEY", "chave_secreta_educampo_123"))
OPENROUTER_API_KEY = clean_env_str(os.getenv("OPENROUTER_API_KEY", "sk-or-v1-..."))

# Carrega a lista de modelos (Severidade e Ishikawa)
SEVERIDADE_MODELS_ENV = clean_env_str(os.getenv("SEVERIDADE_MODELS", "openrouter/free"))
SEVERIDADE_MODELS = [m.strip() for m in SEVERIDADE_MODELS_ENV.split(",") if m.strip()]

ISHIKAWA_MODELS_ENV = clean_env_str(os.getenv("ISHIKAWA_MODELS", "openrouter/free"))
ISHIKAWA_MODELS = [m.strip() for m in ISHIKAWA_MODELS_ENV.split(",") if m.strip()]

ALL_MODELS = list(set(SEVERIDADE_MODELS + ISHIKAWA_MODELS))

# Margem de segurança e Presets
MODEL_MARGIN = int(clean_env_str(os.getenv("MODEL_MARGIN", "4")))
GLOBAL_CONCURRENT_MARGIN = int(clean_env_str(os.getenv("GLOBAL_CONCURRENT_MARGIN", str(MODEL_MARGIN))))
MODEL_RPM_BURST_THRESHOLD = int(clean_env_str(os.getenv("MODEL_RPM_BURST_THRESHOLD", str(MODEL_MARGIN))))
SEVERIDADE_OPENROUTER_PRESET = clean_env_str(os.getenv("SEVERIDADE_OPENROUTER_PRESET", "preset_padrao_educampo"))
ISHIKAWA_OPENROUTER_PRESET = clean_env_str(os.getenv("ISHIKAWA_OPENROUTER_PRESET", "preset_padrao_educampo"))

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
# 2. ESTADO EM MEMÓRIA E LEI DE LITTLE
# ==========================================
# Rastreador de requisições por minuto (RPM) usando janela deslizante
request_timestamps = {model: deque() for model in ALL_MODELS}
model_real_rpm_limit = {model: float('inf') for model in ALL_MODELS}
model_cooldown = {model: 0.0 for model in ALL_MODELS}

def get_current_rpm(model: str) -> int:
    current_time = time.time()
    while request_timestamps[model] and request_timestamps[model][0] < current_time - 60:
        request_timestamps[model].popleft()
    return len(request_timestamps[model])

model_tps = {model: 1000.0 for model in ALL_MODELS}

# Cálculo Dinâmico da Fila Máxima (Lei de Little)
# Concorrência Global: Número de modelos menos a margem de segurança global.
MAX_CONCURRENT = max(1, len(ALL_MODELS) - GLOBAL_CONCURRENT_MARGIN)
# Tamanho Máximo da Fila de Espera (estimado):
# Permitimos que a fila cresça até 3x a capacidade de concorrência simultânea global.
MAX_QUEUE_SIZE = MAX_CONCURRENT * 3



# ==========================================
# 3. LÓGICA DE ROTEAMENTO (ALGORITMO DINÂMICO)
# ==========================================
def get_best_model(models_pool: list, exclude_models: set = None):
    """
    Escolhe o melhor modelo disponível com base no TPS em tempo real, na margem 
    de RPM individual, no limite dinâmico de RPM e nos estados de cooldown.

    Args:
        models_pool (list): Lista de nomes dos modelos candidatos a serem selecionados.
        exclude_models (set, optional): Conjunto de modelos a serem desconsiderados/excluídos da seleção.

    Returns:
        str | None: O nome do melhor modelo selecionado para a requisição ou None se nenhum modelo estiver disponível.

    Raises:
        None: A função trata erros internamente e retorna None caso nenhum modelo seja elegível.

    Domain Context:
        Roteamento Dinâmico Resiliente: Garante a escolha eficiente do modelo com maior TPS (velocidade)
        mantendo o tráfego abaixo do limite seguro de RPM individual (MODEL_RPM_BURST_THRESHOLD) e 
        fazendo o fallback/transbordo igualitário quando todos os limites de segurança são excedidos.
    """
    if exclude_models is None:
        exclude_models = set()
        
    current_time = time.time()
    
    available_models = [
        m for m in models_pool 
        if m not in exclude_models 
        and current_time >= model_cooldown.get(m, 0.0) 
        and get_current_rpm(m) < model_real_rpm_limit.get(m, float('inf'))
    ]
    
    if not available_models:
        return None
        
    # Ordena a lista de modelos do MAIS RÁPIDO para o MAIS LENTO no momento atual
    modelos_ordenados_por_tps = sorted(available_models, key=lambda m: model_tps.get(m, 0), reverse=True)
    
    # Fase 1: Verifica os modelos (do mais rápido para o mais lento). 
    # Se algum estiver abaixo do limiar de RPM individual (ex: < 4), pega ele na hora.
    for model in modelos_ordenados_por_tps:
        effective_margin = min(MODEL_RPM_BURST_THRESHOLD, model_real_rpm_limit.get(model, float('inf')))
        if get_current_rpm(model) < effective_margin:
            return model
            
    # Fase 2: Todos estouraram a margem. Transbordamento igualitário.
    # Pega o modelo com o menor RPM no último minuto.
    best_model = min(available_models, key=lambda m: get_current_rpm(m))
    return best_model


# ==========================================
# ROTA DE HEALTHCHECK (LEVE PARA O DOCKER)
# ==========================================
@app.get("/health")
async def health_check():
    # Retorna uma resposta simples e ultraleve apenas para dizer que a API está viva
    return {"status": "ok"}

# ==========================================
# 4. AUTENTICAÇÃO INTERNA MULTI-TENANT
# ==========================================
security = HTTPBearer(auto_error=False)

def load_clients_db():
    try:
        with open("clients.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback de segurança se o arquivo não existir
        return {
            ROUTER_SECRET_KEY: {
                "client_id": "default-admin",
                "weight": 1.0
            }
        }

async def verify_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Não autorizado (Token ausente)")
        
    clients_db = load_clients_db()
    token = credentials.credentials
    
    if token not in clients_db:
        # Mantém compatibilidade retroativa com chave antiga do .env caso não esteja no JSON
        if token == ROUTER_SECRET_KEY:
            request.state.client_id = "default-admin"
            request.state.client_weight = 1.0
            return
        raise HTTPException(status_code=401, detail="Não autorizado (Token inválido)")
        
    client_info = clients_db[token]
    request.state.client_id = client_info.get("client_id", "unknown-client")
    request.state.client_weight = float(client_info.get("weight", 1.0))



# ==========================================
# 5. LÓGICA DE ROTEAMENTO PRINCIPAL (PROXY E CÁLCULO DE TPS)
# ==========================================
async def handle_chat_completions(request: Request, models_pool: list, preset: str):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    body["preset"] = preset 

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_URL,
        "X-OpenRouter-Title": APP_NAME
    }

    # Verifica se o cliente pediu streaming
    is_stream = body.get("stream", False)
    
    # -----------------------------------------------------
    # FAIR QUEUEING & JITTER: Controle de Cota por Cliente
    # -----------------------------------------------------
    client_id = request.state.client_id
    weight = request.state.client_weight
    
    # A cota de cada cliente na fila é proporcional ao seu 'weight'
    client_quota = max(1, int(MAX_QUEUE_SIZE * weight))
    current_load = client_active_requests.get(client_id, 0)
    
    if current_load >= client_quota:
        # Cliente atingiu seu limite de fila. Aplica o Jitter (Dispersão).
        retry_after = random.randint(1, 5)
        headers_429 = {"Retry-After": str(retry_after)}
        log_dashboard_error(f"[!] REJEIÇÃO (429) Cota da Fila | Cliente: {client_id} | In-Flight: {current_load}/{client_quota}")
        return JSONResponse(
            status_code=429, 
            content={"error": {"message": f"Servidor sobrecarregado. Cota de fila excedida para este cliente ({current_load}/{client_quota}).", "code": 429}},
            headers=headers_429
        )
        
    # Cliente autorizado a entrar na fila / processar. Registramos a carga.
    client_active_requests[client_id] = current_load + 1

    # ==========================================
    # ROTA A: MODO STREAMING
    # ==========================================
    if is_stream:
        async def stream_generator():
            global active_requests_semaphore
            if active_requests_semaphore is None:
                active_requests_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
                
            async with active_requests_semaphore:
                tried_models = set()
                max_attempts = len(models_pool)
                last_error_response = None
                
                for attempt in range(max_attempts):
                    selected_model = get_best_model(models_pool, exclude_models=tried_models)
                    if not selected_model:
                        break
                        
                    body["model"] = selected_model
                    start_time = time.time()
                    start_time_perf = time.perf_counter()
                    request_timestamps[selected_model].append(start_time)
                    model_active_requests[selected_model] = model_active_requests.get(selected_model, 0) + 1
                    
                    last_error_status = None
                    
                    chunk_count = 0
                    success = False
                    try:
                        async with httpx.AsyncClient() as client:
                            async with client.stream("POST", "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=None) as response:
                                if response.status_code == 200:
                                    success = True
                                    async for chunk in response.aiter_bytes():
                                        chunk_count += 1
                                        yield chunk
                                else:
                                    last_error_response = await response.aread()
                                    last_error_status = response.status_code
                    except Exception as e:
                        last_error_response = json.dumps({"error": {"message": str(e), "code": 500}}).encode('utf-8')
                    finally:
                        model_active_requests[selected_model] = max(0, model_active_requests.get(selected_model, 0) - 1)
                        elapsed_time = time.perf_counter() - start_time_perf
                        if success and elapsed_time > 0 and chunk_count > 0:
                            current_tps = chunk_count / elapsed_time
                            historico = model_tps[selected_model]
                            model_tps[selected_model] = current_tps if historico == 1000.0 else (historico * 0.8) + (current_tps * 0.2)
    
                    if success:
                        return
                    else:
                        try:
                            err_json = json.loads(last_error_response)
                            err_msg = err_json.get("error", {}).get("message", "")
                            
                            # Tentar extrair o erro original do provedor
                            metadata = err_json.get("error", {}).get("metadata", {})
                            if metadata and "provider" in err_msg.lower():
                                raw_err = metadata.get("raw", str(metadata))
                                err_msg = f"{err_msg} - {raw_err}"
                        except:
                            err_msg = str(last_error_response)
                            
                        # Limitar o tamanho da mensagem para não quebrar o layout
                        err_msg_trunc = (err_msg[:75] + '...') if len(err_msg) > 75 else err_msg
                            
                        if "No endpoints found" in err_msg or "provider" in err_msg.lower() or "502" in err_msg:
                            # Contexto: Erro do provedor é tratado como falha transiente, não afeta limite RPM
                            log_dashboard_error(f"[!] {selected_model} FALHOU (Erro no Provedor | Msg: {err_msg_trunc})")
                            tried_models.add(selected_model)
                            continue
    
                        is_429 = (last_error_status == 429) or ("429" in err_msg) or ("Too Many Requests" in err_msg)
                        if is_429:
                            new_limit = max(1, get_current_rpm(selected_model) - 1)
                            model_real_rpm_limit[selected_model] = new_limit
                            model_cooldown[selected_model] = time.time() + 60.0
                            log_dashboard_error(f"[!] {selected_model} 429 (Ajustando Limite p/ {new_limit})")
                            tried_models.add(selected_model)
                            continue
                            
                        # Se não for um erro tratável de fallback, repassa imediatamente
                        log_dashboard_error(f"[!] {selected_model} ERRO IRRECUPERÁVEL: {err_msg_trunc}")
                        yield last_error_response
                        return
    
                # Se todos falharam
                if last_error_response:
                    yield last_error_response
                else:
                    yield json.dumps({"error": {"message": "Nenhum modelo disponível", "code": 503}}).encode('utf-8')

        # Cria uma função geradora com um try/finally por fora para garantir limpeza
        async def safe_stream_generator():
            try:
                async for chunk in stream_generator():
                    yield chunk
            finally:
                client_active_requests[client_id] -= 1
                
        return StreamingResponse(safe_stream_generator(), media_type="application/json")

    # ==========================================
    # ROTA B: MODO NORMAL (BLOCKING)
    # ==========================================
    else:
        global active_requests_semaphore
        if active_requests_semaphore is None:
            active_requests_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
        try:
            async with active_requests_semaphore:
                tried_models = set()
                max_attempts = len(models_pool)
                
                for attempt in range(max_attempts):
                    selected_model = get_best_model(models_pool, exclude_models=tried_models)
                    if not selected_model:
                        break
                        
                    body["model"] = selected_model
                    start_time = time.time()
                    start_time_perf = time.perf_counter()
                    request_timestamps[selected_model].append(start_time)
                    model_active_requests[selected_model] = model_active_requests.get(selected_model, 0) + 1
                    
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=None)
                            
                            if response.status_code == 200:
                                response_data = response.json()
                                elapsed_time = time.perf_counter() - start_time_perf
                                if elapsed_time > 0:
                                    tokens_gerados = 0
                                    if "usage" in response_data and response_data["usage"]:
                                        tokens_gerados = response_data["usage"].get("completion_tokens", 0)
                                        
                                    if tokens_gerados <= 0:
                                        # Heurística: fallback baseado no tamanho da resposta para contornar falta de usage
                                        try:
                                            content_str = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                                            if content_str:
                                                tokens_gerados = max(1, len(content_str) / 4.0)
                                        except Exception:
                                            pass

                                    if tokens_gerados > 0:
                                        current_tps = tokens_gerados / elapsed_time
                                        historico = model_tps[selected_model]
                                        model_tps[selected_model] = current_tps if historico == 1000.0 else (historico * 0.8) + (current_tps * 0.2)
                                
                                return JSONResponse(content=response_data)
                            else:
                                try:
                                    response_data = response.json()
                                    err_msg = response_data.get("error", {}).get("message", "")
                                    
                                    # Tentar extrair o erro original do provedor
                                    metadata = response_data.get("error", {}).get("metadata", {})
                                    if metadata and "provider" in err_msg.lower():
                                        raw_err = metadata.get("raw", str(metadata))
                                        err_msg = f"{err_msg} - {raw_err}"
                                except:
                                    response_data = {"error": {"message": response.text, "code": response.status_code}}
                                    err_msg = response.text
                                    
                                # Limitar o tamanho da mensagem para não quebrar o layout
                                err_msg_trunc = (err_msg[:75] + '...') if len(err_msg) > 75 else err_msg
                                    
                                if response.status_code in (502, 503) or "No endpoints found" in err_msg or "provider" in err_msg.lower():
                                    # Contexto: Erro do provedor é tratado como falha transiente, não afeta limite RPM
                                    log_dashboard_error(f"[!] {selected_model} FALHOU (Erro no Provedor | Msg: {err_msg_trunc})")
                                    tried_models.add(selected_model)
                                    continue
                                    
                                if response.status_code == 429 or "429" in err_msg or "Too Many Requests" in err_msg:
                                    new_limit = max(1, get_current_rpm(selected_model) - 1)
                                    model_real_rpm_limit[selected_model] = new_limit
                                    model_cooldown[selected_model] = time.time() + 60.0
                                    log_dashboard_error(f"[!] {selected_model} 429 (Ajustando Limite p/ {new_limit})")
                                    tried_models.add(selected_model)
                                    continue
                                    
                                log_dashboard_error(f"[!] {selected_model} ERRO IRRECUPERÁVEL (Status {response.status_code}): {err_msg_trunc}")
                                return JSONResponse(status_code=response.status_code, content=response_data)
                                
                    except Exception as e:
                        err_msg_trunc = (str(e)[:75] + '...') if len(str(e)) > 75 else str(e)
                        log_dashboard_error(f"[!] {selected_model} Exception: {err_msg_trunc}")
                        return JSONResponse(status_code=500, content={"error": {"message": f"Erro interno: {str(e)}", "code": 500}})
                    finally:
                        model_active_requests[selected_model] = max(0, model_active_requests.get(selected_model, 0) - 1)
                        
                return JSONResponse(status_code=503, content={"error": {"message": "Todos os modelos configurados falharam ou estão indisponíveis.", "code": 503}})
                
        finally:
            client_active_requests[client_id] -= 1

# ==========================================
# 6. ROTAS ESPECÍFICAS DE COMPLEXIDADE
# ==========================================
@app.post("/analise_severidade/v1/chat/completions", dependencies=[Depends(verify_auth)])
async def route_llm_request_severidade(request: Request):
    return await handle_chat_completions(request, SEVERIDADE_MODELS, SEVERIDADE_OPENROUTER_PRESET)

@app.post("/analise_ishikawa/v1/chat/completions", dependencies=[Depends(verify_auth)])
async def route_llm_request_ishikawa(request: Request):
    return await handle_chat_completions(request, ISHIKAWA_MODELS, ISHIKAWA_OPENROUTER_PRESET)