# 📁 api / Camada de Roteamento

> **Projeto:** API_LLM_Router
> **Branch:** feature/dynamic-concurrency-cap
> **Versão da Documentação:** 1.0.0
> **Última Atualização:** 2026-06-30
> **Status:** Active

---

## 🎯 Visão Geral (The Blueprint)

Este diretório concentra a camada de transporte HTTP (Controllers/Routers) da aplicação FastAPI. Sua principal responsabilidade é expor os endpoints de rede, processar o input bruto inicial e despachar as requisições autenticadas para as camadas de infraestrutura e domínio. Ele atua como um "Port" de entrada, isolando as regras de HTTP (cabeçalhos, injeção de dependências do framework) do resto do sistema.

---

## 🏗️ Arquitetura e Fluxo de Dados

* **Entrada:** Requisições HTTP (POST `/analise_severidade/v1/chat/completions`) com payloads raw JSON.
* **Saída:** Respostas JSON validadas (ou Streams ASGI) após orquestração pelas funções de cliente.

---

## 🗂️ Mapeamento de Componentes

### 📄 Arquivos Chave

#### `📄 routes.py`

* **Responsabilidade:** Registrar as rotas do FastAPI (APIRouter), plugar as dependências (`verify_auth`, `get_http_client`) e invocar o orquestrador `handle_chat_completions`.
* **Principais Funções/Classes:**
    * `route_llm_request_severidade`: Endpoint principal da API para inferência.
    * `get_http_client`: Dependency injector para o client HTTPX global do lifespan.
* **Dependências Críticas:** Depende fortemente do `FastAPI` (APIRouter) e do módulo `core.auth`.

---

## 🧠 Decisões de Design & Trade-offs

* **Decisão:** Injeção do Client HTTPX global via Dependency Injection (Depends) em vez de instanciar localmente.
* **Motivo:** Evitar o antipattern de cold-starts na conexão TCP (TCP/TLS handshake overhead), viabilizando connection pooling persistente gerenciado no lifespan da aplicação raiz.
* **Trade-off / Débito Técnico:** Adiciona uma ligeira complexidade na mockagem de testes unitários que usam clients ASGI síncronos fora de lifespans reais.

---

## 🧪 Estratégia de Testes

* **Tipo de Teste dominante:** Testes de Integração com `httpx.AsyncClient(app)`.
* **Cenários Críticos:** Validação de injeção de erros `AttributeError` e dependências não autorizadas (401).

---

## Related Context

*Links to vault notes documenting this module:*
- [[2026-06-30-dynamic-concurrency-cap-architecture]]
