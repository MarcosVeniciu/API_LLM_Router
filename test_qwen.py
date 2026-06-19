import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

def clean_env_str(val: str) -> str:
    """
    Remove caracteres indesejados (aspas, colchetes) da string de variável de ambiente.

    Args:
        val (str): A string original vinda do .env.

    Returns:
        str: A string formatada e limpa.

    Domain Context:
        Parsing: Facilita o particionamento da lista de SEVERIDADE_MODELS que está
        declarada em formato de array no arquivo .env.
    """
    return val.strip().replace('"', '').replace("'", "").replace("[", "").replace("]", "")

def run_tests_production_payload():
    """
    Testa cada modelo definido na variável SEVERIDADE_MODELS utilizando o mesmo
    payload que é enviado em produção (incluindo a chave 'preset').

    Returns:
        None

    Raises:
        None: Apenas exibe o stack trace / erros no console para análise.

    Domain Context:
        Troubleshooting: Reproduzir fielmente as requisições de produção para isolar
        erros 400 (Bad Request) reportados pelo provedor, validando se a chave 
        'preset' no corpo JSON causa violações de schema em certos LLMs.
    """
    api_key = os.getenv('OPENROUTER_API_KEY')
    if api_key:
        api_key = api_key.strip().replace('"', '')

    headers = {
        'Authorization': f'Bearer {api_key}', 
        'Content-Type': 'application/json'
    }

    # Carrega e converte a variável SEVERIDADE_MODELS em uma lista de strings
    severidade_env = clean_env_str(os.getenv("SEVERIDADE_MODELS", ""))
    models = [m.strip() for m in severidade_env.split(",") if m.strip()]

    # Carrega o preset para fidelidade total
    preset = clean_env_str(os.getenv("SEVERIDADE_OPENROUTER_PRESET", "@preset/llm-router-severidade"))

    print(f"Iniciando testes com {len(models)} modelos...")
    print("-" * 50)

    with httpx.Client(timeout=30.0) as client:
        for model in models:
            print(f"# modelo {model}")
            
            # Payload fiel ao que o main.py envia
            body = {
                'model': model, 
                'messages': [{'role': 'user', 'content': 'Test'}],
                'preset': preset
            }

            try:
                r = client.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=body)
                
                try:
                    data = r.json()
                except Exception:
                    data = r.text
                
                if r.status_code == 200:
                    print('Passou com sucesso!')
                    if isinstance(data, dict) and 'usage' in data:
                        print('Usage value:', data['usage'])
                else:
                    # Imprime o erro completo caso não seja 200
                    if isinstance(data, dict):
                        print("Erro completo:", json.dumps(data, indent=2, ensure_ascii=False))
                    else:
                        print(f"Erro completo (Raw): Status {r.status_code} - {data}")
                        
            except Exception as e:
                print(f"Exception durante a requisição: {e}")
            
            print("-" * 50)

if __name__ == '__main__':
    run_tests_production_payload()
