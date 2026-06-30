import pytest
import time
from domain.routing import _calculate_max_concurrent

def test_dynamic_concurrency_happy_path():
    """
    [Happy Path] Testa o cenário nominal onde a capacidade está dentro dos limites seguros.
    Fórmula: min(100, max(1, (len(ALL_MODELS) - GLOBAL_CONCURRENT_MARGIN) * MODEL_RPM_BURST_THRESHOLD))
    """
    total_models = 5
    margin = 1
    burst_threshold = 7
    
    # Expected: (5 - 1) * 7 = 28.  28 is within [1, 100]
    result = _calculate_max_concurrent(total_models, margin, burst_threshold)
    assert result == 28, f"Esperava 28, obteve {result}"

def test_dynamic_concurrency_hard_cap():
    """
    [Edge Case] Testa o limite máximo absoluto (Hard Cap de 100) para evitar esgotamento de recursos.
    """
    total_models = 5
    margin = 1
    burst_threshold = 50
    
    # Expected: (5 - 1) * 50 = 200. Should be capped at 100.
    result = _calculate_max_concurrent(total_models, margin, burst_threshold)
    assert result == 100, f"Esperava 100 (Hard Cap), obteve {result}"

def test_dynamic_concurrency_negative_values():
    """
    [Exception Path] Testa margens muito agressivas ou pouquíssimos modelos onde a conta matemática seria negativa ou zero.
    O limite de fallback absoluto na base deve ser sempre 1.
    """
    total_models = 1
    margin = 2
    burst_threshold = 10
    
    # Expected: (1 - 2) * 10 = -10. Should be bounded to minimum 1.
    result = _calculate_max_concurrent(total_models, margin, burst_threshold)
    assert result == 1, f"Esperava piso de 1 para matemática negativa, obteve {result}"

def test_dynamic_concurrency_zero_burst():
    """
    [Exception Path] Testa configuração incorreta onde o burst_threshold foi setado para 0.
    """
    total_models = 5
    margin = 1
    burst_threshold = 0
    
    # Expected: (5 - 1) * 0 = 0. Should be bounded to minimum 1.
    result = _calculate_max_concurrent(total_models, margin, burst_threshold)
    assert result == 1, f"Esperava piso de 1 para burst 0, obteve {result}"

def test_dynamic_concurrency_performance():
    """
    [Performance & Scaling] Avalia a estabilidade do cálculo para chamadas sucessivas
    e emite o relatório nativo de performance obrigatório para a API_LLM_Router.
    """
    scales = [10, 100, 1000, 10000]
    
    print("\n=== PERFORMANCE REPORT: _calculate_max_concurrent ===")
    print("| N (Executions) | Time (ms) |")
    print("|----------------|-----------|")
    
    for n in scales:
        start = time.perf_counter()
        for _ in range(n):
            # Simulando chamadas de cálculo com diversos tamanhos randômicos ou fixos
            _calculate_max_concurrent(10, 2, 5)
        end = time.perf_counter()
        
        elapsed_ms = (end - start) * 1000
        print(f"| {n:<14} | {elapsed_ms:<9.3f} |")
        
    print("=====================================================")
    
    # Garantimos que a execução mesmo de 10k loops de uma matemática simples é extremamente rápida (< 50ms)
    assert elapsed_ms < 50.0, "O cálculo está excessivamente lento."
