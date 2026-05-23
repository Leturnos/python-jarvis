# 🤖 Assistente Jarvis AI - Diretrizes para Agentes

Bem-vindo, Agente de IA! Este documento fornece o contexto essencial, diretrizes arquiteturais e regras para trabalhar no projeto `python-jarvis`.

## 🎯 Visão Geral do Projeto
O Jarvis é um assistente minimalista controlado por voz para Windows, projetado especificamente para automatizar fluxos de trabalho no terminal (Warp) e comandos de sistema. Ele usa detecção de palavra de ativação offline local (`openwakeword`) combinada com um sistema inteligente de roteamento de comandos em múltiplos estágios (Match Exato -> Fuzzy Match -> Cloud LLM via Google Gemini).

## 🏗️ Arquitetura
O projeto segue uma estrutura de domínios dentro do módulo `core/` para facilitar a escalabilidade e manutenção.

- **Ponto de Entrada:** `main.py` gerencia o bootstrap, chaves de API e inicia a thread `command_worker`.
- **Lógica Central (`core/`):**
  - `controller.py`: Orquestrador do loop de áudio e transições de estado.
  - `activation.py`: Lógica de ativação híbrida (PTT, Wake Word, Fullscreen).
  - **`audio/`**: Motores de áudio e Speech-to-Text (`faster-whisper`).
  - **`ai/`**: Inteligência Artificial, Agentes e Segurança de Prompt.
  - **`execution/`**: Roteamento (`dispatcher`), planos de automação e interação com OS.
  - **`infra/`**: Configurações, Logging e Gerenciamento de Segredos.
  - **`runtime/`**: Estado Global (`JarvisState`), monitoramento e rate limiting.
  - **`plugins/`**: Carregamento dinâmico de comandos DSL e macros.
  - **`ui/`**: Componentes visuais (Rich terminal, Tray, Diálogos).
  - **`persistence/`**: Histórico de execução e métricas (SQLite).
  - **`shared/`**: Funções utilitárias e definições de erros.
- **Interface Gráfica (UI):** Usa `rich` para o terminal e `pystray` para a bandeja do sistema.

## 🛠️ Stack Tecnológica
- **Linguagem:** Python 3.13+
- **Gerenciamento de Dependências:** `uv`
- **Bibliotecas Principais:** `openwakeword`, `faster-whisper`, `litellm`, `pyautogui`, `rich`, `sqlite3`.

## 📜 Convenções de Código e Regras
1. **Concorrência e Threads:** 
   - O processamento pesado roda na thread `command_worker`.
   - **Crucial:** Use `pythoncom.CoInitialize()` em novas threads que interagem com o Windows.
2. **Segurança e Auditoria:**
   - **Regra:** Toda ação deve ter um `risk_level`.
   - **Regra:** Toda execução DEVE ser registrada no `history_manager`.
3. **Normalização Simétrica (NLP):**
   - **Regra:** Sempre use `core.shared.utils.normalize_text` em ambos os lados da comparação.
4. **Configuração:** 
   - Use `core.infra.config.config`. Nunca use hardcoded secrets.
5. **Roteamento de Comandos:**
   - Prioridade: Match Local (Exato/Fuzzy) > LLM.
6. **Idioma:**
   - Interação com usuário: Português.
   - Código, comentários e documentação técnica: Inglês.

## 🧪 Testes
- Rode os testes usando `uv run pytest`.

Sempre revise os arquivos `AGENTS.md` específicos em subdiretórios para obter um contexto localizado.

## 🐛 Histórico de Bugs e Causa Raiz (Knowledge Base)

| Bug | Causa Raiz | Solução Arquitetural |
| :--- | :--- | :--- |
| `NameError: 'palette' is not defined` | Acesso a variáveis de UI dentro da Thread de Áudio sem injeção. | Injetar dependências via construtor ou usar Singletons. |
| Falha no Match de frases com espaço | Texto do STT normalizado vs Frases YAML não normalizadas. | **Normalização Simétrica:** Aplicar o mesmo transformador no carregamento e input. |
| Crash `No wakewords found` | Dependência de chaves fixas no YAML. | Implementar Descoberta Dinâmica de arquivos na pasta `models/`. |
| Falha em teste de Wake Word | Detecção de tela cheia interferindo no ambiente de CI/Mock. | Mockar o `ActivationManager` em testes unitários do controller. |
