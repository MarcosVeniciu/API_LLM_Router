import time
from core.state import (
    model_cooldown,
    model_real_rpm_limit,
    model_tps,
    get_current_rpm,
    MIN_CONCURRENT_CAP,
    MAX_CONCURRENT_CAP
)
from core.config import MODEL_RPM_BURST_THRESHOLD, ALL_MODELS, GLOBAL_CONCURRENT_MARGIN

def _calculate_max_concurrent(total_models: int, margin: int, burst_threshold: int) -> int:
    """Calculate the maximum global concurrency allowed for the router."""
    base_capacity = total_models - margin
    projected_concurrency = base_capacity * burst_threshold
    
    # Apply lower bound to prevent deadlocks if math goes negative
    safe_floor = max(MIN_CONCURRENT_CAP, projected_concurrency)
    
    # Apply upper bound (Hard Cap) to protect local sockets and memory
    return min(MAX_CONCURRENT_CAP, safe_floor)

MAX_CONCURRENT = _calculate_max_concurrent(len(ALL_MODELS), GLOBAL_CONCURRENT_MARGIN, MODEL_RPM_BURST_THRESHOLD)
QUEUE_MULTIPLIER = 3
MAX_QUEUE_SIZE = MAX_CONCURRENT * QUEUE_MULTIPLIER

def get_best_model(models_pool: list, exclude_models: set = None):
    """
    Escolhe o melhor modelo disponível com base no TPS em tempo real, na margem 
    de RPM individual, no limite dinâmico de RPM e nos estados de cooldown.
    """
    if exclude_models is None:
        exclude_models = set()
        
    current_time = time.time()
    # Memoize RPM values to avoid multiple O(1)/O(n) deque iterations per request
    rpm_cache = {m: get_current_rpm(m) for m in models_pool if m not in exclude_models}
    
    available_models = [
        m for m in models_pool 
        if m not in exclude_models 
        and current_time >= model_cooldown.get(m, 0.0) 
        and rpm_cache[m] < model_real_rpm_limit.get(m, float('inf'))
    ]
    
    if not available_models:
        return None
        
    # Ordena a lista de modelos do MAIS RÁPIDO para o MAIS LENTO no momento atual
    modelos_ordenados_por_tps = sorted(available_models, key=lambda m: model_tps.get(m, 0), reverse=True)
    
    # Fase 1: Verifica os modelos (do mais rápido para o mais lento). 
    for model in modelos_ordenados_por_tps:
        effective_margin = min(MODEL_RPM_BURST_THRESHOLD, model_real_rpm_limit.get(model, float('inf')))
        if rpm_cache[model] < effective_margin:
            return model
            
    # Fase 2: Todos estouraram a margem. Transbordamento igualitário.
    best_model = min(available_models, key=lambda m: rpm_cache[m])
    return best_model
