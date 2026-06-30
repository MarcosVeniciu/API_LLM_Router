import time
from collections import deque
from core.config import ALL_MODELS

# Rastreador de requisições ativas por modelo
model_active_requests = {model: 0 for model in ALL_MODELS}

# Histórico de erros recentes (limite de 5)
recent_errors = deque(maxlen=5)

# Semáforo global de concorrência e fila de clientes
active_requests_semaphore = None
client_active_requests = {}  # { "client_id": int_count }

# Rastreador de requisições por minuto (RPM) usando janela deslizante
request_timestamps = {model: deque() for model in ALL_MODELS}
model_real_rpm_limit = {model: float('inf') for model in ALL_MODELS}
model_cooldown = {model: 0.0 for model in ALL_MODELS}

model_tps = {model: 1000.0 for model in ALL_MODELS}

def get_current_rpm(model: str) -> int:
    current_time = time.time()
    if model not in request_timestamps:
        request_timestamps[model] = deque()
    while request_timestamps[model] and request_timestamps[model][0] < current_time - 60:
        request_timestamps[model].popleft()
    return len(request_timestamps[model])

# Limites absolutos de segurança
MIN_CONCURRENT_CAP = 1
MAX_CONCURRENT_CAP = 100
QUEUE_MULTIPLIER = 3
