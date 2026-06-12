# 🗺️ Roadmap de Evolução: Python Jarvis

Este documento detalha as frentes de melhoria para transformar o Python Jarvis de um script utilitário em uma ferramenta de automação profissional e escalável.

---

## 🏗️ 1. Arquitetura e Engenharia de Software
*O objetivo aqui é tornar o código sustentável, testável e fácil de distribuir.*

### 🔹 Modularização e POO
- **Refatoração para Classes:** Criar uma classe base `JarvisEngine` para gerenciar o ciclo de vida do áudio e instâncias de `WindowManager` para lidar com a lógica específica de cada sistema operacional ou aplicação (Warp, VS Code, etc).
- **Injeção de Dependências:** Isolar a detecção de áudio da execução de comandos para permitir a troca fácil do motor de voz (ex: trocar `openwakeword` por outra tecnologia no futuro).
- **SQLiteBase Unificada (Concluído):** Abstração de persistência em uma classe base única gerenciando criação de pastas, concorrência (WAL/timeout de 5s) e transações seguras no histórico e cache.
- **Fixtures de Teste Centralizadas (Concluído):** Criação do `conftest.py` com fixtures de isolamento de estado do `state_manager` (limpeza pós-teste) e mocks reutilizáveis, otimizando o setup de testes.

### 🔹 Configuração Externa (Config-as-Code)
- **Arquivo `config.yaml`:** Mover todos os caminhos de arquivos (`warp_path`), comandos de terminal e thresholds de sensibilidade para um arquivo de configuração externo.
- **Suporte a Múltiplos Perfis:** Permitir que o usuário defina "Workspaces" (ex: perfil `frontend` abre o Warp em uma pasta, perfil `backend` em outra).

### 🔹 Sistema de Plugins (Extensibilidade)
- **Arquitetura Baseada em Eventos:** Criar uma arquitetura baseada em eventos ou *hooks* que permita a adição de novas automações (ex: "plugin-vscode", "plugin-spotify") sem alterar o núcleo do projeto. *(Aviso: Manter a implementação simples e evitar overengineering. O foco é facilitar a adição de comandos sem criar um framework excessivamente complexo).*

### 🔹 Automação Baseada em DSL
- **Mini DSL Declarativo:** Criar uma mini DSL (Domain Specific Language) em YAML ou JSON para definir intenções de voz e suas respectivas automações de forma simplificada, separando a lógica da configuração de novos comandos.

### 🔹 Job Queue Interna (Concorrência Estruturada)
- **Fila de Execução Leve:** Implementar uma fila estruturada nativa (usando `asyncio.Queue` ou `queue.Queue`) para gerenciar a execução de comandos, permitindo retentativas, controle de prioridade e status de jobs sem a complexidade de brokers externos como Redis.

---

## 🎨 2. Experiência do Usuário (UX/UI) (Concluído)
*Tornar a interação com o assistente fluida, informativa e integrada ao sistema.*

### 🔹 Interface de Comandos
- **Command Palette:** Implementada uma interface moderna e responsiva em **PySide6 / Qt** (acessível via hotkey global `Ctrl+Alt+P`) que unifica comandos de voz, digitação manual e exibição de histórico.

### 🔹 Feedback Multimodal
- **Síntese de Voz (TTS):** Implementado `pyttsx3` com suporte a SAPI5 (voz local do Windows) para confirmações faladas rápidas de estado e execução.
- **Interface Visual (PySide6 / Qt):** O log de terminal legado do Rich UI foi completamente migrado para um painel visual do sistema em PySide6/Qt, contendo um cartão dinâmico de status visual para o assistente (Status Card).

### 🔹 Integração com Windows
- **System Tray (Bandeja do Sistema):** Implementado usando o `QSystemTrayIcon` do PySide6. Permite que o Jarvis rode silenciosamente em segundo plano, contendo menu de controle para mutar/pausar, alterar provedores de LLM e acessar a Command Palette.
- **Notificações Toast:** Integradas notificações nativas do Windows via biblioteca `plyer` para sinalizar transições de estado críticas e término de tarefas em background.

---

## 🛡️ 3. Robustez, Performance e Resiliência (Concluído)
*Garantir que o assistente seja rápido, consuma poucos recursos e não falhe silenciosamente.*

### 🔹 Segurança e Permissões
- **Permission System:** Sistema de Security Ranks integrado que categoriza comandos por nível de risco (`risk_level`) e aciona um diálogo modal de segurança em PySide6 (`security_ui.py`) solicitando aprovação expressa do usuário antes de rodar comandos perigosos.
- **Armazenamento Seguro (Keyring):** Migração das chaves de APIs do LLM (`.env`) para o Windows Credential Manager de forma nativa e criptografada via biblioteca `keyring` (com `keyring_manager.py`).

### 🔹 Monitoramento de Estado (State Machine)
- **Gestão Centralizada:** Máquina de estados baseada em enum (`JarvisState` em `state.py`) que gerencia estados em thread-safe e sincroniza a interface gráfica nativa para evitar race conditions ou digitação cruzada.
- **Validação de Execução:** Validação de execução de aplicativos e manipulação de janelas via APIs do Windows (`win32gui`, `win32con`, `pygetwindow`).

### 🔹 Concorrência e Assincronismo
- **AsyncIO/Threading:** A captura e processamento de áudio (STT) foram desacoplados em threads assíncronas do worker de execução (`command_worker`), garantindo que o Jarvis continue ouvindo comandos sem congelar a interface ou a automação do sistema.

### 🔹 Telemetria e Erros
- **Logging Estruturado:** Sistema de log com rotação configurado em `jarvis.log`.
- **Auto-Recuperação e Self-healing:** Monitor de saúde (`monitor.py`) e controle de reinicialização de canais de áudio caso ocorra desconexão ou anomalias físicas nos canais.

### 🔹 Otimização de IA
- **Cache Local de LLMs:** Cache SQLite indexado com hash SHA-256 (`sqlite_cache.py`) integrado ao fluxo do agente de IA para responder de forma imediata e economizar custos de rede/tokens.

---

## 🧠 4. Inteligência e Expansão de Capacidades (Concluído)
*Onde o Jarvis deixa de ser um "disparador de macros" e passa a ser um assistente inteligente.*

### 🔹 Intenções Baseadas em Contexto (NLU)
- **Comandos Dinâmicos & STT:** Transcrição local offline usando `faster-whisper` com suporte a lazy loading para inicialização rápida.
- **Integração Multi-Provedor via LiteLLM:** Abstração completa de LLMs (`BaseLLMProvider` em `core/llm/`) suportando Google Gemini, OpenAI, Anthropic, DeepSeek e OpenRouter com seleção em tempo real através do menu da bandeja.
- **Dry-run e Explainability:** Exibição estruturada do plano de automação proposto pelo LLM na UI antes da execução física.
- **Memória e Histórico de Comandos:** Banco de dados SQLite (`history_db.py`) que salva cada ação efetuada com timestamp, comando transcrito e status.
- **Automação de Mídia e Spotify:** Suporte integrado a controle de mídia local e suporte visual a templates OpenCV e focagem da janela para automações no Spotify.

### 🔹 Segurança de IA
- **Prompt Injection Guard:** Camada protetiva (`prompt_guard.py`) avaliando o risco de instruções do usuário antes do envio ao LLM e sanitização estrita de payloads.
- **Rate Limiting:** Controle de quotas locais para chamadas de API e tokens para precaver loops de execução acidentais.

---

## 📊 5. Observability e Monitoramento
*Garantir a previsibilidade e diagnosticar gargalos de forma eficiente.*

### 🔹 Métricas Leves e Performance
- **Métricas de Operação:** Registrar latência de chamadas do LLM, taxa de acerto (hit rate) do cache semântico e tempo total de execução de comandos diretamente no SQLite ou logs estruturados.
- **Performance Profiling:** Adicionar rastreamento de tempo de execução e do STT para localizar gargalos do sistema.
- **Memory Usage:** Monitoramento contínuo da memória, especialmente para as threads da IA (OpenWakeWord/JarvisEngine), evitando leaks em longas sessões de background.

---

## 📦 6. Distribuição e Empacotamento
*Facilitar a instalação e o uso por usuários que não possuem ambiente Python/UV configurado.*

### 🔹 Compilação para Executável (.exe)
- **Nuitka / PyInstaller:** Pesquisar e implementar a compilação do projeto para um único arquivo executável (binário estático). Preferência pelo `Nuitka` pela performance superior e proteção de código.
- **Modo "Windowed" (No Console):** Configurar o binário para rodar como um aplicativo de janela nativo do Windows, eliminando a necessidade de uma janela de terminal visível por padrão.
- **Resource Embedding:** Utilizar técnicas de inclusão de arquivos (Data Files) para embutir os modelos `.onnx` do OpenWakeWord, o ícone `icon.ico` e possíveis arquivos de áudio de resposta diretamente no `.exe`.

### 🔹 Instalação e Modos de Execução
- **Setup Profissional (Inno Setup / Wix):** Criar um instalador que gerencie a pasta de instalação em `AppData` ou `Program Files`.
- **Portable Mode:** Fornecer uma versão autossuficiente (como um pacote ZIP) permitindo rodar a aplicação sem instalador ou privilégios de administrador.
- **Configuração de Registro:** Automatizar a criação da chave de `Run` no registro do Windows para garantir que o Autostart funcione mesmo se o usuário deletar o atalho manual.

### 🔹 Updates
- **Auto-Update OTA (Over-The-Air):** Implementar um mecanismo silencioso (via GitHub Releases ou AWS S3) que baixe atualizações em segundo plano e reinicie a aplicação transparentemente.

---

## 🔬 7. Experimental Features
*Inovações a serem testadas e avaliadas para viabilidade técnica.*

### 🔹 Pesquisa de Tecnologias
- **Streaming STT (Reconhecimento Contínuo):** Transição de um modelo de "grava e depois processa" para *Streaming Speech-to-Text* (ex: Deepgram, Google Cloud STT ou Whisper em streaming local), permitindo a execução do comando enquanto o usuário ainda está falando.

---
*Este roadmap é um documento vivo e deve ser atualizado conforme novas necessidades e tecnologias surjam.*