# LLM Router - Gateway Inteligente para Educampo

API intermediária (Gateway) desenvolvida em Python com FastAPI para fazer a orquestração e balanceamento de carga inteligente entre múltiplos modelos através do OpenRouter. 

O objetivo principal é evitar a sobrecarga de um único modelo em cenários de alta concorrência (até 30 chamadas paralelas) através de um algoritmo de transbordamento dinâmico e ordenação por velocidade (Tokens por Segundo) calculada em tempo real.

## 📂 Estrutura do Projeto

```text
llm_router/
├── main.py              # Código fonte da API (FastAPI)
├── requirements.txt     # Dependências do Python
├── Dockerfile           # Instruções de build do container
├── .env                 # Variáveis de ambiente (crie a partir do .env.example)
├── .env.example         # Exemplo de variáveis de ambiente
└── README.md            # Documentação de uso e deploy
```

## 🚀 Como Executar Localmente com Docker

### 1. Construir a imagem Docker
Na raiz do projeto, execute:
```bash
docker build -t llm-router-educampo .
```

### 2. Rodar o container

Crie um arquivo `.env` a partir do `.env.example` e preencha com suas credenciais. Depois, rode o container:

```bash
docker run -d \
  -p 8000:8000 \
  --name llm-router \
  --env-file .env \
  llm-router-educampo
```

---

## 🔒 Variáveis de Ambiente (Configuração)

| Variável | Descrição | Exemplo |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Sua chave de API real do OpenRouter. | `sk-or-v1-...` |
| `ROUTER_SECRET_KEY` | Chave criada por você para autenticar os clientes que usarão este Roteador. | `token_secreto_123` |
| `MODELS` | Lista de modelos elegíveis separados por vírgula. | `google/gemini-1.5-flash,anthropic/claude-3-haiku` |
| `MODEL_MARGIN` | Margem de segurança de requisições simultâneas por modelo. | `4` |
| `OPENROUTER_PRESET` | Nome do preset criado no OpenRouter para filtrar provedores. | `meu_preset_de_provedores` |
| `ALLOWED_DOMAINS` | Lista de domínios com permissão (CORS) para acessar a API separados por vírgula. Use `*` para liberar todos. | `https://meuapp.com,http://localhost:3000` |

---

## 🛰️ Como Integrar com o Roteador

Qualquer aplicação cliente deve direcionar suas requisições para o endereço deste Roteador (`http://localhost:8000/v1/chat/completions`) em vez de apontar direto para o OpenRouter.

### Exemplo de Requisição (cURL)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sua_chave_secreta_interna_aqui" \
  -H "Content-Type: application/json" \
  -d '{
    "stream": true,
    "messages": [{"role": "user", "content": "Olá, gere um relatório estatístico."}]
  }'
```

---

## 🪵 Como Monitorar o Status do Roteamento

Como o container roda em segundo plano, para acompanhar qual modelo está sendo escolhido e a velocidade real em tempo real, use o comando:

```bash
docker logs -f llm-router
```

Você verá saídas no terminal como esta:

```text
-> Disparando para google/gemini-1.5-flash | Estado atual: {'google/gemini-1.5-flash': 1, 'anthropic/claude-3-haiku': 0}
<- Conexão fechada para google/gemini-1.5-flash | Estado atual: {'google/gemini-1.5-flash': 0, 'anthropic/claude-3-haiku': 0}
[google/gemini-1.5-flash] Vel: 120.5 TPS | Em uso: 0
```
