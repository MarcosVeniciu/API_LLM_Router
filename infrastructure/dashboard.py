import os
import json
import copy
import asyncio
import time
from datetime import datetime
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Group, Console
from rich import box

from core.config import ALL_MODELS
from core.state import (
    model_active_requests,
    recent_errors,
    model_real_rpm_limit,
    model_cooldown,
    get_current_rpm,
    model_tps,
    client_active_requests
)
from domain.routing import MAX_CONCURRENT, MAX_QUEUE_SIZE

def log_dashboard_error(msg: str):
    """Adiciona um erro ao histórico do dashboard com formatação de data/hora."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    recent_errors.append(f"[{timestamp}] {msg}")

def log_debug_error_to_file(selected_model: str, payload: dict, error_response: str) -> None:
    timestamp = datetime.now().isoformat()
    safe_payload = copy.deepcopy(payload)
    if isinstance(safe_payload, dict) and "messages" in safe_payload:
        safe_payload["messages"] = "[REDACTED]"
        
    log_entry = {
        "timestamp": timestamp,
        "model": selected_model,
        "payload": safe_payload,
        "error_raw": error_response
    }
    try:
        lines = []
        if os.path.exists("debug_errors.json"):
            with open("debug_errors.json", "r", encoding="utf-8") as f:
                lines = f.readlines()
        
        lines.append(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        if len(lines) > 50:
            lines = lines[-50:]
            
        with open("debug_errors.json", "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass

async def live_dashboard():
    """Tarefa em background para atualizar o console do Docker usando rich."""
    console = Console(force_terminal=True, color_system="standard")
    with Live(auto_refresh=False, console=console) as live:
        while True:
            try:
                table = Table(title=f"LLM Router Dashboard - {datetime.now().strftime('%H:%M:%S')}", box=box.ROUNDED, expand=True)
                table.add_column("Modelo", style="cyan", no_wrap=True)
                table.add_column("Status", justify="center")
                table.add_column("Reqs Ativas", justify="right", style="magenta")
                table.add_column("Limite RPM", justify="right", style="red")
                table.add_column("RPM Atual", justify="right", style="yellow")
                table.add_column("Velocidade (TPS)", justify="right", style="green")

                modelos_ordenados = sorted(ALL_MODELS, key=lambda m: (-model_tps.get(m, 0.0), m))
                for model in modelos_ordenados:
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

                total_active = sum(model_active_requests.values())
                total_clientes_na_fila = sum(client_active_requests.values())
                esperando = max(0, total_clientes_na_fila - total_active)
                
                resumo_texto = (
                    f"[bold]Concorrência Global (Executando):[/bold] {total_active} / {MAX_CONCURRENT}\n"
                    f"[bold]Requisições em Espera (Fila):[/bold] {esperando} / {MAX_QUEUE_SIZE}"
                )
                painel_resumo = Panel(resumo_texto, title="Visão Geral", border_style="blue")

                texto_erros = "\n".join(recent_errors) if recent_errors else "Nenhum erro recente."
                painel_erros = Panel(texto_erros, title="Últimos Erros (Top 5)", border_style="red")

                group = Group(table, painel_resumo, painel_erros)
                live.update(group, refresh=True)
            except Exception as e:
                console.print(f"[red]Erro no dashboard: {str(e)}[/red]")
            await asyncio.sleep(1.0)
