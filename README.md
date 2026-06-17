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
| `GLOBAL_CONCURRENT_MARGIN` | Margem de segurança para calcular a concorrência global (descontada do total de modelos). | `4` |
| `MODEL_RPM_BURST_THRESHOLD` | Limiar de requisições por minuto (RPM) em um único modelo antes de transbordar na Fase 1. | `4` |
| `MODEL_MARGIN` | (Legado) Margem padrão caso as novas variáveis não estejam definidas. | `4` |
| `OPENROUTER_PRESET` | Nome do preset criado no OpenRouter para filtrar provedores. | `meu_preset_de_provedores` |
| `ALLOWED_DOMAINS` | Lista de domínios com permissão (CORS) para acessar a API separados por vírgula. Use `*` para liberar todos. | `https://meuapp.com,http://localhost:3000` |
| `APP_NAME` | Nome do aplicativo enviado ao OpenRouter no cabeçalho `X-Title` para identificação da sua app. | `API_LLM_Router` |
| `APP_URL` | URL do aplicativo enviada no cabeçalho `HTTP-Referer` para o OpenRouter. | `https://educampo.com.br` |

---

## 🏗️ Arquitetura Multi-Tenant e Fila Justa (Anti-Thundering Herd)

Para proteger nossos modelos de picos intensos de requisições concorrentes (ex: Celery despachando 300 tarefas simultâneas), a API implementa uma **Fila Justa com Jitter**:

1. **Multi-Tenant (`clients.json`)**: Em vez de uma única chave global para todos, usamos o arquivo `clients.json` na raiz do projeto. A própria chave (senha) do usuário atua como a raiz do objeto JSON, mapeando para o identificador (`client_id`) e a prioridade na fila (`weight`):

   ```json
   {
       "senha_secreta_do_cliente_aqui": {
           "client_id": "nome-do-sistema",
           "weight": 1.0
       }
   }
   ```
   
2. **Concorrência Máxima**: O roteador só abre requisições simultâneas até um teto seguro (`MAX_CONCURRENT`), baseado na quantidade de modelos ativos disponíveis.
3. **Cota e Rejeição (Jitter)**: Cada cliente ganha uma cota de "espaço na fila" proporcional ao seu peso. Se o cliente estourar essa cota enviando requisições demais, a API barra a requisição com o erro `429 Too Many Requests` e injeta um cabeçalho `Retry-After` com um tempo aleatório entre 30 e 45 segundos (Jitter). Isso espalha as retentativas no tempo e impede que o servidor caia.

---

## 🛰️ Como Integrar com o Roteador

Qualquer aplicação cliente deve direcionar suas requisições para o endereço deste Roteador (ex: `http://localhost:8000/analise_severidade/v1/chat/completions`) em vez de apontar direto para o OpenRouter.

### 🔑 Autenticação
**Importante:** O cliente **NÃO** deve enviar o seu `client_id`. Ele deve enviar apenas a sua **Chave Secreta** configurada no `clients.json` usando o cabeçalho Bearer Token padrão. O roteador vai ler a chave e inferir internamente quem é o cliente.

*(Nota: Para fins de retrocompatibilidade ou testes rápidos no `/docs`, a chave global do `.env` chamada `ROUTER_SECRET_KEY` continua funcionando como um "administrador padrão", mas em produção cada serviço deve ter sua chave no JSON).*

### Exemplo de Requisição (cURL)

```bash
curl -X POST http://localhost:8000/analise_severidade/v1/chat/completions \
  -H "Authorization: Bearer chave_teste_pesado_789" \
  -H "Content-Type: application/json" \
  -d '{
    "stream": true,
    "messages": [{"role": "user", "content": "Olá, gere um relatório estatístico."}]
  }'
```

---

## 🪵 Como Monitorar o Status do Roteamento

A API implementa um painel de monitoramento dinâmico no console (Live Dashboard) utilizando a biblioteca `rich`.

Como o container roda em segundo plano, o comando tradicional `docker logs -f` ou `docker-compose logs -f` **não** renderiza os caracteres ANSI de cursor adequadamente, gerando um efeito de rolagem de tela infinita e quebra de layout.

Para visualizar o painel interativo perfeitamente atualizado em tempo real no console, conecte-se diretamente (attach) ao container:

```bash
docker attach api_llm_router-llm_router_api-1
```
*(Caso seu container possua outro nome, substitua `api_llm_router-llm_router_api-1` pelo nome retornado em `docker ps`).*

> [!IMPORTANT]
> **Como desanexar com segurança:** Para sair da visualização do terminal sem encerrar ou desligar o container da API, pressione a sequência de teclas **`CTRL + P` seguido de `CTRL + Q`**.