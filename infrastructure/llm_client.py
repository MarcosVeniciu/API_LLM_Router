import json
import time
import asyncio
import httpx
import random
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from core.config import OPENROUTER_API_KEY, APP_URL, APP_NAME
from core.state import (
    client_active_requests,
    model_active_requests,
    request_timestamps,
    model_real_rpm_limit,
    model_cooldown,
    model_tps,
    get_current_rpm
)
from domain.routing import get_best_model, MAX_CONCURRENT, MAX_QUEUE_SIZE
from infrastructure.dashboard import log_dashboard_error, log_debug_error_to_file
from domain.dto import ChatCompletionRequest
import core.state

async def _handle_stream(body_dict: dict, headers: dict, models_pool: list, http_client: httpx.AsyncClient, client_id: str):
    async def stream_generator():
        if core.state.active_requests_semaphore is None:
            core.state.active_requests_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
        async with core.state.active_requests_semaphore:
            tried_models = set()
            max_attempts = len(models_pool)
            last_error_response = None
            
            for attempt in range(max_attempts):
                selected_model = get_best_model(models_pool, exclude_models=tried_models)
                if not selected_model:
                    break
                    
                # Immutability: update the model dynamically
                current_payload = body_dict.copy()
                current_payload["model"] = selected_model
                
                start_time = time.time()
                start_time_perf = time.perf_counter()
                request_timestamps[selected_model].append(start_time)
                model_active_requests[selected_model] = model_active_requests.get(selected_model, 0) + 1
                
                last_error_status = None
                
                chunk_count = 0
                success = False
                try:
                    async with http_client.stream("POST", "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=current_payload, timeout=60.0) as response:
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
                    last_error_status = 500
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
                        
                        metadata = err_json.get("error", {}).get("metadata", {})
                        if metadata and "provider" in err_msg.lower():
                            raw_err = metadata.get("raw", str(metadata))
                            err_msg = f"{err_msg} - {raw_err}"
                    except:
                        err_msg = str(last_error_response)
                        
                    err_msg_trunc = (err_msg[:75] + '...') if len(err_msg) > 75 else err_msg
                        
                    if last_error_status in (500, 502, 503) or "No endpoints found" in err_msg or "provider" in err_msg.lower() or "502" in err_msg:
                        log_debug_error_to_file(selected_model, current_payload, str(last_error_response))
                        log_dashboard_error(f"[!] {selected_model} FALHOU (Erro Conexão/Provedor | Msg: {err_msg_trunc})")
                        tried_models.add(selected_model)
                        await asyncio.sleep(random.uniform(0.1, 0.5))
                        continue

                    is_429 = (last_error_status == 429) or ("429" in err_msg) or ("Too Many Requests" in err_msg)
                    if is_429:
                        new_limit = max(1, get_current_rpm(selected_model) - 1)
                        model_real_rpm_limit[selected_model] = new_limit
                        model_cooldown[selected_model] = time.time() + 60.0
                        log_dashboard_error(f"[!] {selected_model} 429 (Ajustando Limite p/ {new_limit})")
                        tried_models.add(selected_model)
                        await asyncio.sleep(random.uniform(0.1, 0.5))
                        continue
                        
                    log_debug_error_to_file(selected_model, current_payload, str(last_error_response))
                    log_dashboard_error(f"[!] {selected_model} ERRO IRRECUPERÁVEL: {err_msg_trunc}")
                    yield last_error_response
                    return

            if last_error_response:
                yield last_error_response
            else:
                yield json.dumps({"error": {"message": "Nenhum modelo disponível", "code": 503}}).encode('utf-8')

    async def safe_stream_generator():
        try:
            async for chunk in stream_generator():
                yield chunk
        finally:
            client_active_requests[client_id] -= 1
            
    return StreamingResponse(safe_stream_generator(), media_type="application/json")


async def _handle_blocking(body_dict: dict, headers: dict, models_pool: list, http_client: httpx.AsyncClient, client_id: str):
    if core.state.active_requests_semaphore is None:
        core.state.active_requests_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
    try:
        async with core.state.active_requests_semaphore:
            tried_models = set()
            max_attempts = len(models_pool)
            
            for attempt in range(max_attempts):
                selected_model = get_best_model(models_pool, exclude_models=tried_models)
                if not selected_model:
                    break
                    
                current_payload = body_dict.copy()
                current_payload["model"] = selected_model
                
                start_time = time.time()
                start_time_perf = time.perf_counter()
                request_timestamps[selected_model].append(start_time)
                model_active_requests[selected_model] = model_active_requests.get(selected_model, 0) + 1
                
                try:
                    response = await http_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=current_payload, timeout=60.0)
                    
                    if response.status_code == 200:
                        response_data = response.json()
                        elapsed_time = time.perf_counter() - start_time_perf
                        if elapsed_time > 0:
                            tokens_gerados = 0
                            if "usage" in response_data and response_data["usage"]:
                                tokens_gerados = response_data["usage"].get("completion_tokens", 0)
                                
                            if tokens_gerados <= 0:
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
                            
                            metadata = response_data.get("error", {}).get("metadata", {})
                            if metadata and "provider" in err_msg.lower():
                                raw_err = metadata.get("raw", str(metadata))
                                err_msg = f"{err_msg} - {raw_err}"
                        except:
                            response_data = {"error": {"message": response.text, "code": response.status_code}}
                            err_msg = response.text
                            
                        err_msg_trunc = (err_msg[:75] + '...') if len(err_msg) > 75 else err_msg
                            
                        if response.status_code in (500, 502, 503) or "No endpoints found" in err_msg or "provider" in err_msg.lower():
                            log_debug_error_to_file(selected_model, current_payload, response.text)
                            log_dashboard_error(f"[!] {selected_model} FALHOU (Erro Conexão/Provedor | Msg: {err_msg_trunc})")
                            tried_models.add(selected_model)
                            await asyncio.sleep(random.uniform(0.1, 0.5))
                            continue
                            
                        if response.status_code == 429 or "429" in err_msg or "Too Many Requests" in err_msg:
                            new_limit = max(1, get_current_rpm(selected_model) - 1)
                            model_real_rpm_limit[selected_model] = new_limit
                            model_cooldown[selected_model] = time.time() + 60.0
                            log_dashboard_error(f"[!] {selected_model} 429 (Ajustando Limite p/ {new_limit})")
                            tried_models.add(selected_model)
                            await asyncio.sleep(random.uniform(0.1, 0.5))
                            continue
                            
                        log_debug_error_to_file(selected_model, current_payload, response.text)
                        log_dashboard_error(f"[!] {selected_model} ERRO IRRECUPERÁVEL (Status {response.status_code}): {err_msg_trunc}")
                        return JSONResponse(status_code=response.status_code, content=response_data)
                        
                except Exception as e:
                    err_msg_trunc = (str(e)[:75] + '...') if len(str(e)) > 75 else str(e)
                    log_dashboard_error(f"[!] {selected_model} Exception: {err_msg_trunc}")
                    tried_models.add(selected_model)
                    await asyncio.sleep(random.uniform(0.1, 0.5))
                    continue
                finally:
                    model_active_requests[selected_model] = max(0, model_active_requests.get(selected_model, 0) - 1)
                    
            return JSONResponse(status_code=503, content={"error": {"message": "Todos os modelos configurados falharam ou estão indisponíveis.", "code": 503}})
            
    finally:
        client_active_requests[client_id] -= 1


async def handle_chat_completions(
    body_dto: ChatCompletionRequest,
    client_id: str,
    client_weight: float,
    models_pool: list,
    preset: str,
    http_client: httpx.AsyncClient
):
    body_dict = body_dto.model_dump(exclude_unset=True)
    body_dict["preset"] = preset 

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_URL,
        "X-OpenRouter-Title": APP_NAME
    }

    is_stream = body_dict.get("stream", False)
    
    # -----------------------------------------------------
    # FAIR QUEUEING & JITTER: Controle de Cota por Cliente
    # -----------------------------------------------------
    client_quota = max(1, int(MAX_QUEUE_SIZE * client_weight))
    current_load = client_active_requests.get(client_id, 0)
    
    if current_load >= client_quota:
        retry_after = random.randint(1, 5)
        headers_429 = {"Retry-After": str(retry_after)}
        log_dashboard_error(f"[!] REJEIÇÃO (429) Cota da Fila | Cliente: {client_id} | In-Flight: {current_load}/{client_quota}")
        return JSONResponse(
            status_code=429, 
            content={"error": {"message": f"Servidor sobrecarregado. Cota de fila excedida para este cliente ({current_load}/{client_quota}).", "code": 429}},
            headers=headers_429
        )
        
    client_active_requests[client_id] = current_load + 1

    if is_stream:
        return await _handle_stream(body_dict, headers, models_pool, http_client, client_id)
    else:
        return await _handle_blocking(body_dict, headers, models_pool, http_client, client_id)
