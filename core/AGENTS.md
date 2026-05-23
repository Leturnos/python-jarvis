# 🧠 Módulo Core - Diretrizes para Agentes

Este diretório contém a lógica de negócios essencial e as integrações para o assistente Jarvis, agora organizado por domínios de responsabilidade.

## 📁 Detalhamento do Módulo

### 🏗️ Orquestração (Raiz de `core/`)
- **`controller.py`**: Orquestrador do loop de áudio que delega ativações ao `ActivationManager` e gerencia estados de ciclo de vida (`SLEEPING`, `SUSPENDED`).
- **`activation.py`**: Centraliza a lógica de decisão para ativação. Avalia o `ActivationContext` (scores de wake word, hotkeys e janelas em tela cheia). *Regra:* Não deve conter lógica de gravação, apenas decisão de estado.

### 🎙️ Áudio (`core/audio/`)
- **`audio_engine.py`**: Gerencia os streams do PyAudio e detecção de wake word offline. *Regra:* O processamento deve ser rápido e não bloqueante.
- **`stt_engine.py`**: Wrapper para o modelo `faster-whisper` com suporte a lazy loading.

### 🤖 Inteligência Artificial (`core/ai/`)
- **`llm_agent.py`**: Interface com o provedor de LLM. *Regra:* Prompts devem impor saída JSON estrita.
- **`command_resolver.py`**: Lógica de roteamento local (Match Exato e Fuzzy Match).
- **`prompt_guard.py`**: Camada de segurança contra injeção de prompt e sanitização de saída.

### ⚙️ Execução e Automação (`core/execution/`)
- **`dispatcher.py`**: Roteia comandos e valida `risk_level` antes da execução.
- **`execution_plan.py`**: Define o esquema estruturado de passos para automação.
- **`worker.py`**: Thread worker que processa a fila de tarefas de forma assíncrona.
- **`automator.py`**: Interação física com o Windows (janelas, digitação) e TTS (SAPI5).
- **`job_queue.py`**: Gerenciamento e histórico de tarefas da sessão.

### 🔌 Extensibilidade (`core/plugins/`)
- **`plugin_manager.py`**: Carregador dinâmico de arquivos YAML de automação.
- **`macro_manager.py`**: Criação inteligente de macros (plugins) a partir do histórico via LLM.

### 🕒 Runtime e Estado (`core/runtime/`)
- **`state.py`**: Single Source of Truth para o estado lógico (`JarvisState`).
- **`monitor.py`**: Monitoramento de memória e coleta de lixo (GC) automática.
- **`rate_limiter.py`**: Controle de quotas e limites de uso da API de LLM.

### 🛠️ Infraestrutura e Dados (`core/infra/` & `core/persistence/`)
- **`infra/config.py`**: Carregador centralizado de configuração (YAML + ENV).
- **`infra/logger_config.py`**: Configuração global de logs.
- **`infra/keyring_manager.py`**: Acesso seguro a segredos via OS Keyring.
- **`persistence/history_db.py`**: Gerencia o SQLite `data/history.db` para auditoria.

### 💻 Interface de Usuário (`core/ui/`)
- **`ui.py`**: Interface Rich no terminal.
- **`tray.py`**: Ícone e menu na bandeja do sistema.
- **`security_ui.py`**: Diálogo modal para autorização de comandos perigosos.
- **`command_palette.py`**: Interface de entrada rápida via teclado.
- **`notifications.py`**: Notificações nativas do Windows.

### 🧱 Utilitários Compartilhados (`core/shared/`)
- **`utils.py`**: Funções auxiliares (ex: `normalize_text`).
- **`errors.py`**: Definições de exceções (Technical vs Business).

## ⚠️ Considerações Importantes
- **Especificidades do Windows:** Muitos módulos dependem fortemente de `win32gui`, `win32con` e `pythoncom`.
- **Tratamento de Erros:** A degradação suave é fundamental. Falhas em IA não devem travar o sistema.
- **Segurança:** O `risk_level` deve ser validado sempre no `dispatcher` antes da execução física.
