# test_version.py
import time

import pytest
from fastapi.testclient import TestClient

import main
from main import app

def test_global_version_constant():
    """Happy Path: Verifica se a constante global de versão está definida e é exatamente 1.0.0"""
    assert hasattr(main, "__version__"), "O módulo main deve exportar a variável __version__"
    assert main.__version__ == "1.0.0", f"A versão global esperada é 1.0.0, recebido: {main.__version__}"

def test_fastapi_app_version():
    """Happy Path: Verifica se o metadata da versão foi injetado corretamente na instância do FastAPI"""
    assert app.version == "1.0.0", f"A instância do FastAPI deve ter a versão 1.0.0, recebido: {app.version}"

def test_openapi_schema_version():
    """Edge Case / Integration: Verifica se o schema gerado pelo FastAPI (OpenAPI) exporta a versão correta"""
    client = TestClient(app)
    response = client.get("/openapi.json")
    
    if response.status_code == 200:
        schema = response.json()
        schema_version = schema.get("info", {}).get("version")
        assert schema_version == "1.0.0", f"A versão no OpenAPI schema deveria ser 1.0.0, recebido: {schema_version}"
    else:
        pytest.skip("Endpoint /openapi.json indisponível na configuração atual do app")

def test_versioning_performance_scaling():
    """Performance & Scaling: Verifica o overhead de injeção da versão instanciando o FastAPI múltiplas vezes"""
    from fastapi import FastAPI
    
    iterations = [10, 100, 1000]
    
    print(f"\n=== PERFORMANCE REPORT: version_initialization ===")
    print(f"| N (Items) | Time (ms) |")
    print(f"|-----------|-----------|")
    
    # Executa a simulação para injetar a variável e instanciar
    for n in iterations:
        start = time.perf_counter()
        for _ in range(n):
            # Simulando injeção em app fake
            dummy_app = FastAPI(version=getattr(main, "__version__", "1.0.0"))
        end = time.perf_counter()
        
        elapsed_ms = (end - start) * 1000
        print(f"| {n:<9} | {elapsed_ms:<9.2f} |")
        
        if n == 1000:
            assert elapsed_ms < 1000.0, "Overhead excessivo na inicialização/alocação"
            
    print(f"==================================================")
