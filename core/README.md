# 📁 core / Configuração e Estado Global

> **Projeto:** API_LLM_Router
> **Branch:** feature/dynamic-concurrency-cap
> **Versão da Documentação:** 1.0.0
> **Última Atualização:** 2026-06-30
> **Status:** Active

---

## 🎯 Visão Geral (The Blueprint)

Este diretório gerencia o "coração" operacional do sistema: o estado distribuído em memória (Rate limits dinâmicos, contadores de filas, timestamps por modelo) e a camada transversal de segurança e autorização. Ele isola os estados voláteis da lógica de negócio funcional.

---

## 🏗️ Arquitetura e Fluxo de Dados

* **Entrada:** Validação de Bearer tokens injetados pelos routers, e updates de estado gerados pela infraestrutura.
* **Saída:** Decisões de autenticação, cotas (`MAX_QUEUE_SIZE`) e estruturas de controle (`client_active_requests`).

---

## 🗂️ Mapeamento de Componentes

### 📄 Arquivos Chave

#### `📄 auth.py`

* **Responsabilidade:** Proteger endpoints e determinar os limites de uso baseados na identidade do cliente.
* **Principais Funções/Classes:**
    * `verify_auth`: Valida JWTs em tempo constante para mitigar Timing Attacks e injeta o `client_weight` no estado da request.
* **Dependências Críticas:** `secrets.compare_digest`.

#### `📄 state.py`

* **Responsabilidade:** Concentrar variáveis mutáveis e filas necessárias para balanceamento em memória.
* **Principais Funções/Classes:**
    * `get_current_rpm(model)`: Limpa timestamps expirados (janela 60s) e devolve a RPM real atual.

---

## 🧠 Decisões de Design & Trade-offs

* **Decisão:** Uso de `secrets.compare_digest` para validação de tokens simples de configuração.
* **Motivo:** Segurança (OWASP A07 - Vulnerabilidades Criptográficas) bloqueando adivinhação estatística do tamanho das chaves em redes rápidas.

---

## 🧪 Estratégia de Testes

* **Tipo de Teste dominante:** Unit tests.
* **Cenários Críticos:** Testes de Time-based attacks e rejeição assertiva de credenciais (401).

---

## Related Context

*Links to vault notes documenting this module:*
- [[2026-06-30-dynamic-concurrency-cap-architecture]]
