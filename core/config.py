import os
from dotenv import load_dotenv

load_dotenv()

def clean_env_str(val: str) -> str:
    return val.strip().replace('"', '').replace("'", "").replace("[", "").replace("]", "")

__version__ = "1.0.0"

ROUTER_SECRET_KEY = clean_env_str(os.getenv("ROUTER_SECRET_KEY", "chave_secreta_educampo_123"))
OPENROUTER_API_KEY = clean_env_str(os.getenv("OPENROUTER_API_KEY", "sk-or-v1-..."))

SEVERIDADE_MODELS_ENV = clean_env_str(os.getenv("SEVERIDADE_MODELS", "openrouter/free"))
SEVERIDADE_MODELS = [m.strip() for m in SEVERIDADE_MODELS_ENV.split(",") if m.strip()]

ISHIKAWA_MODELS_ENV = clean_env_str(os.getenv("ISHIKAWA_MODELS", "openrouter/free"))
ISHIKAWA_MODELS = [m.strip() for m in ISHIKAWA_MODELS_ENV.split(",") if m.strip()]

ALL_MODELS = list(set(SEVERIDADE_MODELS + ISHIKAWA_MODELS))

MODEL_MARGIN = int(clean_env_str(os.getenv("MODEL_MARGIN", "4")))
GLOBAL_CONCURRENT_MARGIN = int(clean_env_str(os.getenv("GLOBAL_CONCURRENT_MARGIN", str(MODEL_MARGIN))))
MODEL_RPM_BURST_THRESHOLD = int(clean_env_str(os.getenv("MODEL_RPM_BURST_THRESHOLD", str(MODEL_MARGIN))))

SEVERIDADE_OPENROUTER_PRESET = clean_env_str(os.getenv("SEVERIDADE_OPENROUTER_PRESET", "preset_padrao_educampo"))
ISHIKAWA_OPENROUTER_PRESET = clean_env_str(os.getenv("ISHIKAWA_OPENROUTER_PRESET", "preset_padrao_educampo"))

ALLOWED_DOMAINS_ENV = clean_env_str(os.getenv("ALLOWED_DOMAINS", "*"))
ALLOWED_DOMAINS = [d.strip() for d in ALLOWED_DOMAINS_ENV.split(",") if d.strip()]

APP_NAME = clean_env_str(os.getenv("APP_NAME", "API_LLM_Router"))
APP_URL = clean_env_str(os.getenv("APP_URL", "none"))
