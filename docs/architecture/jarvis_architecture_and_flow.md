# 🧠 Visão Consolidada e Grafo de Funcionamento do Jarvis AI

Este documento apresenta a arquitetura completa, o fluxo de dados ponta a ponta e a máquina de estados do **Jarvis AI Assistant** (`python-jarvis`).

---

## 🗺️ 1. Grafo de Fluxo Consolidado Ponta a Ponta

O diagrama abaixo ilustra o ciclo de vida completo de uma instrução: desde a captura de áudio ou texto até a execução física no sistema operacional e feedback ao usuário.

```mermaid
flowchart TD
    %% Entradas
    subgraph INGRESS["🎧 1. Camada de Entrada & Gatilhos"]
        MIC["🎙️ Microfone / PyAudio<br/><code>AudioLoopManager</code>"]
        HOTKEY["⌨️ Push-To-Talk (PTT)<br/><code>Global Hotkey</code>"]
        PALETTE["💻 Interface Gráfica<br/><code>CommandPalette (PySide6)</code>"]
        FULLSCREEN["🎮 Detector de Tela Cheia<br/><code>Win32 API (WS_CAPTION)</code>"]
    end

    %% Detecção e Ativação
    subgraph ACTIVATION["⚡ 2. Ativação & Pré-processamento"]
        OWW["🤖 Detecção de Wake Word<br/><code>openwakeword (Local)</code>"]
        ACT_MGR{"🛡️ <code>ActivationManager</code><br/>Avalia Contexto"}
        SUSPEND_STATE["⏸️ Estado SUSPENDED<br/>(Descarrega modelos)"]
        LISTEN_STATE["👂 Estado LISTENING<br/>(Captura buffer de voz)"]
        SILENCE_CHECK{"🤫 Detecção de Silêncio<br/>RMS < silence_rms"}
        STT["🗣️ Speech-to-Text<br/><code>faster-whisper (STTEngine)</code>"]
    end

    %% Fila de Processamento
    subgraph QUEUE_LAYER["📦 3. Desacoplamento & Fila"]
        JOB_Q[("📥 <code>JobQueue</code> / Thread Worker<br/><code>command_worker</code>")]
    end

    %% Resolução e Roteamento
    subgraph ROUTING["🧭 4. Roteador de Intenções (3 Estágios)"]
        RESOLVER["🔍 <code>CommandResolver</code><br/>Normalização Simétrica"]
        STAGE1{"1. Match Local?<br/>(Exato / Fuzzy Levenshtein)"}
        STAGE2{"2. Sistema Especial?<br/>(Replay / Macro)"}
        STAGE3["3. Cloud LLM / LiteLLM<br/><code>LiteLLMProvider</code> + <code>SQLiteCache</code>"]
        MEDIA_ROUTER["🎵 Roteador de Mídia<br/><code>MediaResolver</code> & NLP"]
    end

    %% Segurança & Planejamento
    subgraph SECURITY["🛡️ 5. Segurança & Planejamento"]
        PROMPT_GUARD["🔒 <code>PromptGuard</code><br/>Sanitização & Anti-Injection"]
        RISK_CHECK{"Nível de Risco?<br/><code>RiskLevel</code>"}
        BLOCKED["⛔ Bloqueado<br/>(Ação Perigosa / Catastrófica)"]
        CONFIRM_DLG["⚠️ <code>SecurityDialog</code> / Dry-Run<br/>(Voz / Clique do Usuário)"]
        PLAN_BUILDER["📋 <code>PlanBuilder</code><br/>Gera <code>ExecutionPlan</code> com <code>ExecutionStep</code>s"]
    end

    %% Execução Física
    subgraph EXECUTION["⚙️ 6. Motor de Execução (StepExecutor)"]
        STEP_EXEC["⚡ <code>StepExecutor</code><br/>(Execução Sequencial Isolada)"]
        WIN_MGR["🪟 <code>WindowManager</code><br/>(Foco, Estabilização & Layout)"]
        CMD_SUBPROCESS["💻 Execução de Comandos<br/><code>subprocess</code> / <code>cmd</code>"]
        PYAUTOGUI["⌨️ Digitação & Teclas<br/><code>pyautogui</code> / Hotkeys"]
        SPOTIFY_CV["👁️ Automação Spotify<br/><code>TemplateMatcher</code> (OpenCV)"]
    end

    %% Feedback & Persistência
    subgraph FEEDBACK["📢 7. Feedback & Auditoria"]
        TTS["🔊 Síntese de Voz (TTS)<br/><code>TTSEngine (SAPI5)</code>"]
        TRAY_NOTIF["🔔 Notificações Windows<br/><code>JarvisNotifier</code> / Tray Icon"]
        HIST_DB[("💾 Banco SQLite<br/><code>HistoryManager (history_db.py)</code>")]
        STATE_MGR["🔄 <code>state_manager</code><br/>Transições & Limpeza"]
    end

    %% Conexões do Fluxo
    MIC --> OWW
    OWW --> ACT_MGR
    HOTKEY --> ACT_MGR
    FULLSCREEN --> ACT_MGR

    ACT_MGR -- "Jogo em Tela Cheia" --> SUSPEND_STATE
    ACT_MGR -- "Wake Word / PTT Ativado" --> LISTEN_STATE
    LISTEN_STATE --> SILENCE_CHECK
    SILENCE_CHECK -- "Fala Finalizada" --> STT
    STT --> JOB_Q
    PALETTE --> JOB_Q

    JOB_Q --> RESOLVER
    RESOLVER --> STAGE1

    STAGE1 -- "Sim (Plugin YAML)" --> PLAN_BUILDER
    STAGE1 -- "Não" --> STAGE2

    STAGE2 -- "Sim (Replay/Macro)" --> HIST_DB
    STAGE2 -- "Não" --> STAGE3

    STAGE3 -- "Intenção de Mídia" --> MEDIA_ROUTER
    MEDIA_ROUTER --> PLAN_BUILDER
    STAGE3 -- "Comando / Automação" --> PROMPT_GUARD

    PROMPT_GUARD --> RISK_CHECK
    RISK_CHECK -- "Blocked" --> BLOCKED
    RISK_CHECK -- "Dangerous / Dry-Run" --> CONFIRM_DLG
    CONFIRM_DLG -- "Aprovado" --> PLAN_BUILDER
    CONFIRM_DLG -- "Rejeitado" --> TTS
    RISK_CHECK -- "Safe" --> PLAN_BUILDER

    PLAN_BUILDER --> STEP_EXEC

    STEP_EXEC --> WIN_MGR
    STEP_EXEC --> CMD_SUBPROCESS
    STEP_EXEC --> PYAUTOGUI
    STEP_EXEC --> SPOTIFY_CV

    STEP_EXEC --> TTS
    STEP_EXEC --> TRAY_NOTIF
    STEP_EXEC --> HIST_DB
    STEP_EXEC --> STATE_MGR
    BLOCKED --> TTS
```

---

## 🔄 2. Máquina de Estados Global (`JarvisState`)

O Jarvis opera sob uma máquina de estados finitos centralizada gerenciada pelo [`state_manager`](../../core/runtime/state.py). Modelos pesados (como STT) são descarregados dinamicamente para poupar memória RAM quando o assistente está inativo ou suspenso.

```mermaid
stateDiagram-v2
    [*] --> IDLE : Inicialização (main.py)

    IDLE --> LISTENING : Wake Word Detectada / PTT Pressionado
    IDLE --> SUSPENDED : Jogo / Janela em Tela Cheia
    IDLE --> SLEEPING : Comando "dormir" / "stop listening"
    IDLE --> MUTED : Bandeja do Sistema (Mudo temporário)

    SUSPENDED --> IDLE : Janela restaurada / minimizada
    SLEEPING --> LISTENING : PTT Pressionado / Bandeja
    MUTED --> IDLE : Fim do Timer / Desmutar

    LISTENING --> THINKING : Silêncio detectado / PTT solto
    THINKING --> CONFIRMING_DRY_RUN : Ação perigosa / Dry-Run ativado
    THINKING --> EXECUTING : Ação segura aprovada
    THINKING --> ERROR : Falha técnica no STT / LLM

    CONFIRMING_DRY_RUN --> EXECUTING : Confirmação por Voz / Clique
    CONFIRMING_DRY_RUN --> IDLE : Rejeitado pelo Usuário / Timeout

    EXECUTING --> IDLE : Sucesso no Plano (TTS: "Pronto!")
    EXECUTING --> ERROR : Falha em algum Step do Plano
    ERROR --> IDLE : Reset de buffers & Log
```

---

## 🏛️ 3. Visão Consolidada das Camadas da Aplicação

```mermaid
classDiagram
    direction TB

    class PontoDeEntrada {
        +main.py
        +SingleInstanceMutex
        +KeyringSecrets
        +WorkerThreads
    }

    class AudioAndActivation {
        +AudioLoopManager (PyAudio)
        +OpenWakeWordModel (Local ML)
        +ActivationManager (PTT & Fullscreen)
        +STTEngine (faster-whisper)
        +TTSEngine (Windows SAPI5)
    }

    class IntentAndAI {
        +CommandResolver (Fuzzy & Exact Match)
        +LLMAgent (Prompt Engineering)
        +LiteLLMProvider (Multi-LLM Gateway)
        +SQLiteCache (Response Caching)
        +MediaResolver (Spotify & OS Media NLP)
        +PromptGuard (Security Filter)
    }

    class OrchestrationAndExecution {
        +JarvisController (State Orchestrator)
        +ActionDispatcher (Action Gateway)
        +PlanBuilder (ExecutionPlan Factory)
        +StepExecutor (Atomic Step Runner)
        +WindowManager (Win32 API & Focus Guard)
        +SpotifyAutomator (CV Template Matcher)
    }

    class PersistenceAndPlugins {
        +HistoryManager (SQLite Execution Log)
        +PluginManager (YAML Declarative Actions)
        +MacroManager (Automatic Macro Learner)
        +MemoryMonitor (Garbage Collector & RAM Limits)
    }

    class PresentationAndUI {
        +QtAppController (PySide6 Event Loop)
        +CommandPalette (Global SpotLight Search)
        +JarvisTrayAdapter (Tray Actions & Timer)
        +SecurityDialog (Dry-Run Confirmation Modal)
    }

    PontoDeEntrada --> AudioAndActivation
    PontoDeEntrada --> OrchestrationAndExecution
    PontoDeEntrada --> PresentationAndUI

    AudioAndActivation --> OrchestrationAndExecution
    OrchestrationAndExecution --> IntentAndAI
    OrchestrationAndExecution --> PersistenceAndPlugins
    OrchestrationAndExecution --> PresentationAndUI
```

---

## 📂 4. Principais Módulos do Sistema

| Camada / Componente | Arquivo Principal | Responsabilidade |
| :--- | :--- | :--- |
| **Ponto de Entrada** | [`main.py`](../../main.py) | Bootstrap, migração segura de credenciais para Keyring, inicialização de threads e interface PySide6. |
| **Orquestrador de Áudio** | [`core/controller.py`](../../core/controller.py) | Loop de áudio em tempo real, detecção de wake words e gestão de estados de escuta. |
| **Gerenciador de Ativação** | [`core/activation.py`](../../core/activation.py) | Avaliação híbrida de ativação (PTT, wake word, supressão em jogos fullscreen via Win32 `WS_CAPTION`). |
| **Speech-to-Text** | [`core/audio/stt_engine.py`](../../core/audio/stt_engine.py) | Transcrição de áudio ultrarrápida usando `faster-whisper` com carregamento sob demanda (*lazy-load*). |
| **Resolução de Comandos** | [`core/ai/command_resolver.py`](../../core/ai/command_resolver.py) | Match exato e fuzzy local com normalização simétrica antes de recorrer a LLMs. |
| **Agente Inteligente** | [`core/ai/llm_agent.py`](../../core/ai/llm_agent.py) | Conexão com LLMs via `LiteLLMProvider` com cache SQLite e fallback de conectividade. |
| **Guarda de Segurança** | [`core/ai/prompt_guard.py`](../../core/ai/prompt_guard.py) | Validação contra injeção de prompt e sanitização de planos de execução. |
| **Fila e Worker** | [`core/execution/worker.py`](../../core/execution/worker.py) | Consumo assíncrono de jobs com separação estrita de `BusinessError` vs `TechnicalError` e retry com backoff exponencial. |
| **Despachante & Segurança** | [`core/execution/dispatcher.py`](../../core/execution/dispatcher.py) | Roteamento de planos, verificação de níveis de risco (`RiskLevel`) e confirmação de Dry-Run. |
| **Executor de Passos** | [`core/execution/step_executor.py`](../../core/execution/step_executor.py) | Execução de ações atômicas (`WRITE`, `COMMAND`, `HOTKEY`, `OPEN_APP`, `SPOTIFY_CLICK_PLAY`) com trava de foco da janela ativa. |
| **Janelas do Windows** | [`core/execution/window_manager.py`](../../core/execution/window_manager.py) | Gerenciamento de janelas via Win32 API, posicionamento e validação de perda de foco. |
| **Visão Computacional & Mídia** | [`core/media/cv_matcher.py`](../../core/media/cv_matcher.py) | Localização visual de elementos na UI do Spotify via OpenCV template matching. |
| **Auditoria & Histórico** | [`core/persistence/history_db.py`](../../core/persistence/history_db.py) | Registro de todas as ações no SQLite para auditoria, repetição de comandos e criação automática de macros. |
| **Estado Global** | [`core/runtime/state.py`](../../core/runtime/state.py) | Máquina de estados com callbacks para transições seguras e gerenciamento de recursos. |
