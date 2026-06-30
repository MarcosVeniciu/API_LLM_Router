import json
from core.config import ROUTER_SECRET_KEY

class ClientRepository:
    def __init__(self, filepath: str = "clients.json"):
        self.filepath = filepath

    def get_all_clients(self) -> dict:
        try:
            with open(self.filepath, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                ROUTER_SECRET_KEY: {
                    "client_id": "default-admin",
                    "weight": 1.0
                }
            }

def get_client_repository() -> ClientRepository:
    return ClientRepository()
