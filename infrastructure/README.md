# 📁 infrastructure / Adaptadores e Integrações

> **Projeto:** API_LLM_Router
> **Branch:** feature/dynamic-concurrency-cap
> **Versão da Documentação:** 1.0.0
> **Última Atualização:** 2026-06-30
> **Status:** Active

---

## 🎯 Visão Geral (The Blueprint)

Este diretório contém os adaptadores para o mundo exterior. Tudo o que necessita de disco (arquivos JSON), console outputs avançados (Rich UI), ou I/O de Rede (cliente HTTPX chamando provedores externos de LLM) reside aqui. Isola a complexidade assíncrona dos retries (Thundering Herd mitigation) da lógica limpa de domínio.

---

## 🏗️ Arquitetura e Fluxo de Dados

* **Entrada:** Comandos autorizados pela rota e configurados pelo domínio.
* **Saída:** Payload recebido do OpenRouter / OpenAI, ou Exceções de rede (gracefully degeneradas).

---

## 🗂️ Mapeamento de Componentes

### 📄 Arquivos Chave

#### `📄 llm_client.py`

* **Responsabilidade:** Fazer as chamadas reais aos backends da inteligência artificial lidando com streams paralelos ou chamadas blocantes, controlando cotas (`MAX_QUEUE_SIZE`) e fallbacks automáticos em caso de indisponibilidade (`HTTP 429` / `502`).
* **Principais Funções/Classes:**
    * `handle_chat_completions`: Proxy de despacho (stream vs normal) e enforcement das contas e retries.
    * `_handle_stream` & `_handle_blocking`: Funções fracionadas extraídas para controle estrito de `Cyclomatic Complexity`.

#### `📄 dashboard.py`

* **Responsabilidade:** Renderização em tempo real das métricas do servidor no CLI. Também mascara os logs brutos para `debug_errors.json` redigindo (redacting) PII e histórico de conversas.

---

## 🧠 Decisões de Design & Trade-offs

* **Decisão:** Separação de responsabilidades de execução HTTPX (`_handle_stream` e `_handle_blocking`).
* **Motivo:** Diminuição extrema do V(G) (Cyclomatic Complexity) facilitando os blocos unificados de `try/finally` e liberação correta dos slots de limite simultâneo `client_active_requests`.

---

## 🧪 Estratégia de Testes

* **Tipo de Teste dominante:** Mocks assíncronos de chamadas HTTP.
* **Cenários Críticos:** Testes de falha graciosa em timeouts, simulação de Retry-After headers (Jitter) e enfileiramentos justos baseados no peso do cliente.

---

## Related Context

*Links to vault notes documenting this module:*
- [[2026-06-30-dynamic-concurrency-cap-architecture]]
