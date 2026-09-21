# 🤖 Assistente Jarvis AI - Diretrizes para Agentes

Bem-vindo, Agente de IA! Este documento fornece o contexto essencial, diretrizes arquiteturais e regras para trabalhar no projeto `python-jarvis`.

## 🎯 Visão Geral do Projeto
O Jarvis é um assistente minimalista controlado por voz para Windows, projetado especificamente para automatizar fluxos de trabalho no terminal (Warp) e comandos de sistema. Ele usa detecção de palavra de ativação offline local (`openwakeword`) combinada com um sistema inteligente de roteamento de comandos em múltiplos estágios (Match Exato/Fuzzy Local -> Match NLP Mídia -> Cloud LLM via LiteLLM).

## 🏗️ Arquitetura
O projeto segue uma estrutura de domínios dentro do módulo `core/` para facilitar a escalabilidade e manutenção.
> 💡 **Referência Visual e Fluxo Ponta a Ponta:** Consulte [`docs/architecture/jarvis_architecture_and_flow.md`](./docs/architecture/jarvis_architecture_and_flow.md) para o diagrama completo do fluxo de dados, máquina de estados (`JarvisState`) e grafo de classes. O índice completo da documentação está em [`docs/README.md`](./docs/README.md).

- **Ponto de Entrada:** `main.py` gerencia o bootstrap, chaves de API, carrega a UI em PySide6 e inicia a thread `command_worker`.
- **Lógica Central (`core/`):**
  - `controller.py`: Orquestrador do loop de áudio e transições de estado.
  - `activation.py`: Lógica de ativação híbrida (PTT, Wake Word, Fullscreen).
  - **`audio/`**: Motores de áudio e Speech-to-Text (`faster-whisper`).
  - **`ai/`**: Inteligência Artificial, Agentes e Segurança de Prompt (Prompt Guard).
  - **`llm/`**: Abstração de múltiplos provedores de LLM via `litellm`.
  - **`cache/`**: Cache de respostas de LLM baseado em SQLite.
  - **`media/`**: Processamento de intenções e automação de controle de mídia (Spotify, OS).
  - **`execution/`**: Roteamento (`dispatcher`), planos de automação e interação com OS.
  - **`infra/`**: Configurações, Logging e Gerenciamento de Segredos.
  - **`runtime/`**: Estado Global (`JarvisState`), monitoramento e rate limiting.
  - **`plugins/`**: Carregamento dinâmico de comandos DSL e macros.
  - **`ui/`**: Componentes gráficos modernos baseados em **PySide6 / Qt**.
  - **`persistence/`**: Histórico de execução e métricas (SQLite).
  - **`shared/`**: Funções utilitárias e definições de erros.
- **Interface Gráfica (UI):** Baseada em **PySide6 / PyQt-Fluent-Widgets** e **qdarktheme**, provendo Command Palette global e ícone na bandeja via `QSystemTrayIcon`.

## 🛠️ Stack Tecnológica
- **Linguagem:** Python 3.13+
- **Gerenciamento de Dependências:** `uv`
- **Bibliotecas Principais:** `openwakeword`, `faster-whisper`, `litellm`, `PySide6`, `pyautogui`, `sqlite3`.

## 📜 Convenções de Código e Regras
1. **Concorrência e Threads:** 
   - O processamento pesado roda na thread `command_worker`.
   - **Crucial:** Use `pythoncom.CoInitialize()` em novas threads que interagem com o Windows (como APIs COM/SAPI5 ou interações de UI).
2. **Segurança e Auditoria:**
   - **Regra:** Toda ação deve ter um `risk_level`.
   - **Regra:** Toda execução DEVE ser registrada no `history_manager`.
3. **Normalização Simétrica (NLP):**
   - **Regra:** Sempre use `core.shared.utils.normalize_text` em ambos os lados da comparação de frases.
4. **Configuração:** 
   - Use `core.infra.config.config`. Nunca use secrets hardcoded.
5. **Roteamento de Comandos:**
   - Prioridade: Match Local (Exato/Fuzzy via Plugins) -> Match de Mídia -> LLM.
6. **Abstração LLM:**
   - **Regra:** Sempre prefira interagir com LLMs usando `BaseLLMProvider` / `LiteLLMProvider` em vez de chamadas diretas a APIs de fornecedores.
7. **Idioma:**
   - Interação com usuário e textos de interface gráfica: Português do Brasil.
   - Código, comentários e documentação técnica: Inglês.
8. **Resolução Portável de Caminhos (`get_app_root`):**
   - **Regra:** Sempre use `core.shared.paths.get_app_root()` para resolver caminhos do projeto (arquivos `config.yaml`, pastas `models/`, `plugins/`, `resources/`, logs e bancos SQLite). Nunca use `os.getcwd()` nem caminhos relativos de `__file__` sem suporte a `sys.frozen`, pois o aplicativo deve funcionar perfeitamente quando compilado para binário único/one-folder.
9. **Desacoplamento de Logs e Caminhos:**
   - **Regra:** O módulo `core.shared.paths` não deve importar `logger` nem módulos de alto nível para evitar dependências circulares durante a inicialização do `setup_logger()`.

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
| AttributeError no `ActivationManager` no Boot | Propriedade `@property` de otimização inserida por engano no corpo do `__init__`, fazendo o construtor encerrar prematuramente e a UI fechar. | Manter decoradores `@property` fora do corpo do `__init__`. |
| Congelamento do PC com Warp | `check_dead_silence()` reiniciando o PyAudio a cada 2.4s de silêncio (`rms < 0.1`) e `is_fullscreen()` detectando janelas maximizadas como jogos. | Validar `rms == 0.0` e checar o estilo Win32 `WS_CAPTION` no detector de tela cheia. |
| Crash silencioso sem chave no boot do `.exe` | `main.py` executava `sys.exit(1)` no console quando nenhuma chave era encontrada; em binários `--noconsole`, o usuário não via erro algum. | **Onboarding Gráfico:** Entrar em `onboarding_mode`, abrir a janela principal na aba de Configurações e salvar chave via Keyring com re-init do LLM. |
| Import circular entre logger e utils | `setup_logger()` precisava de `get_app_root()`, mas `utils.py` importava o logger no topo do módulo. | Isolar funções de caminho puras em `core/shared/paths.py` livre de imports de infraestrutura. |
| Ícones fantasmas na bandeja do Windows | O processo encerrava antes do Windows processar a remoção do ícone da barra de tarefas. | Chamar `tray_icon.hide()` como primeiríssima instrução em `quit_app()`. |
| Falha no Autostart do executável congelado | `manage_autostart()` gerava scripts VBS chamando `uv run main.py`, que não existem no PC do usuário final. | Gravar comando direto `"{sys.executable}" --hidden` no Registro do Windows quando `sys.frozen` for verdadeiro. |
| `FileNotFoundError` em metadados LiteLLM | `litellm` necessita de arquivos `.json` de preços/contexto em tempo de execução, ausentes por padrão no PyInstaller. | Incluir dados de pacotes estáticos via `collect_data_files('litellm')` no `jarvis.spec`. |
| `ValueError: Unknown encoding cl100k_base` no Tiktoken | `tiktoken` descobre plugins via `pkgutil.iter_modules`, que retorna vazio em binários congelados sem declaração explícita de submódulos. | Declarar `tiktoken`, `tiktoken_ext` e `tiktoken_ext.openai_public` em `hidden_imports` e coletar arquivos de extensão no `jarvis.spec`. |
| `PermissionError: [WinError 5] Acesso negado: 'plugins'` no Autostart | Quando iniciado pelo Registro do Windows (`HKCU\...\Run`), o `cwd` padrão é `C:\Windows\System32`. Módulos com caminhos relativos tentavam criar pastas protegidas do sistema. | **Ancoragem de CWD e Resolução Absoluta:** Chamar `os.chdir(get_app_root())` na inicialização do `main()` e resolver `plugins`, `macros`, `sqlite` e `spotify` sempre com `get_app_root()`. |


