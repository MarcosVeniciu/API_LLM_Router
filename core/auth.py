import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.config import ROUTER_SECRET_KEY
from infrastructure.client_repo import ClientRepository, get_client_repository

security = HTTPBearer(auto_error=False)

async def verify_auth(
    request: Request, 
    credentials: HTTPAuthorizationCredentials = Depends(security),
    client_repo: ClientRepository = Depends(get_client_repository)
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Não autorizado (Token ausente)")
        
    clients_db = client_repo.get_all_clients()
    token = credentials.credentials
    
    if token not in clients_db:
        # Mantém compatibilidade retroativa com chave antiga do .env caso não esteja no JSON
        if secrets.compare_digest(token, ROUTER_SECRET_KEY):
            request.state.client_id = "default-admin"
            request.state.client_weight = 1.0
            return
        raise HTTPException(status_code=401, detail="Não autorizado (Token inválido)")
        
    client_info = clients_db[token]
    request.state.client_id = client_info.get("client_id", "unknown-client")
    request.state.client_weight = float(client_info.get("weight", 1.0))
