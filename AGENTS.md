# 🤖 Assistente Jarvis AI - Diretrizes para Agentes

Bem-vindo, Agente de IA! Este documento fornece o contexto essencial, diretrizes arquiteturais e regras para trabalhar no projeto `python-jarvis`.

## 🎯 Visão Geral do Projeto
O Jarvis é um assistente minimalista controlado por voz para Windows, projetado especificamente para automatizar fluxos de trabalho no terminal (Warp) e comandos de sistema. Ele usa detecção de palavra de ativação offline local (`openwakeword`) combinada com um sistema inteligente de roteamento de comandos em múltiplos estágios (Match Exato -> Fuzzy Match -> Cloud LLM via Google Gemini).

## 🏗️ Arquitetura
- **Ponto de Entrada:** `main.py` gerencia o loop principal de áudio, atualizações da interface de usuário (UI) e inicia a thread `command_worker`.
- **Lógica Central:** Localizada no diretório `core/`.
  - `audio_engine.py`: Gerencia o stream do microfone e a detecção da palavra de ativação.
  - `stt_engine.py`: Speech-to-text (fala para texto) local usando Faster Whisper.
  - `llm_agent.py`: Faz a interface com o Google Gemini para processamento de linguagem natural e geração dinâmica de comandos.
  - `dispatcher.py`: Executa as ações (comandos de sistema ou automação do terminal Warp).
  - `automator.py`: Lida com foco de janelas, digitação e TTS (SAPI5).
- **Configuração:** Gerenciada via `config.yaml` (comandos, limites) e `.env` (chaves de API).
- **Interface Gráfica (UI):** Usa `rich` para a interface do terminal e `pystray` para o ícone na bandeja do sistema (system tray).

## 🛠️ Stack Tecnológica
- **Linguagem:** Python 3.13+
- **Gerenciamento de Dependências:** `uv`
- **Bibliotecas Principais:** `openwakeword`, `openai-whisper`, `google-genai` (SDK v2.0+), `pyautogui`, `pygetwindow`, `rich`.

## 📜 Convenções de Código e Regras
1. **Concorrência e Threads:** 
   - O loop principal gerencia a captura de áudio e a detecção da palavra de ativação.
   - O processamento de comandos (STT, LLM, Dispatch) roda em uma thread separada chamada `command_worker` para evitar o bloqueio do stream de áudio.
   - **Crucial:** Sempre use `pythoncom.CoInitialize()` no início de novas threads que interagem com objetos COM do Windows (como SAPI5 para TTS) e `pythoncom.CoUninitialize()` no final.
2. **Normalização Simétrica (NLP):**
   - **Regra:** Sempre aplique `normalize_text` em ambos os lados da comparação (input do usuário E strings de comando/frases dos plugins). Isso evita falhas causadas por espaços vs underscores ou capitalização.
3. **Configuração:** 
   - Nunca coloque chaves de API ou caminhos (paths) fixos no código (hardcode). Use `core/config.py` que mescla os arquivos `.env` e `config.yaml`.
4. **Roteamento de Comandos:**
   - Prefira o match local (Exato ou Fuzzy via `difflib`) em vez de chamadas ao LLM pela velocidade e confiabilidade.
   - O agente LLM retorna um formato JSON estrito com um discriminador `type` (`"action"` ou `"chat"`).
5. **UI e Logs:**
   - Use `core.logger_config.logger` para todos os registros (logs).
   - A interface do terminal é gerenciada por `core.ui.JarvisUI`. Não use `print` diretamente no console dentro do loop principal para não quebrar a exibição ao vivo (Live) do `rich`.
6. **Idioma:**
   - O usuário interage em Português. O TTS (texto para fala), prompts do LLM e documentações internas (como esta) devem usar o Português como padrão. Para o restante, incluindo código e comentários, utilize inglês.

## 🧪 Testes
- Os testes estão localizados no diretório `tests/`.
- Rode os testes usando `uv run python -m unittest discover tests/`.

Sempre revise os arquivos `AGENTS.md` específicos em subdiretórios para obter um contexto mais localizado.

## 🐛 Histórico de Bugs e Causa Raiz (Knowledge Base)

| Bug | Causa Raiz | Solução Arquitetural |
| :--- | :--- | :--- |
| `NameError: 'palette' is not defined` | Acesso a variáveis de UI (Main Thread) dentro da Thread de Áudio (Worker) sem injeção de dependência. | Injetar dependências via construtor ou usar Singletons como `plugin_manager` para lógica de negócios. |
| Falha no Match de frases com espaço (ex: "hora de trabalhar") | O texto do STT era normalizado ("hora_de_trabalhar"), mas as frases do YAML não, causando mismatch. | **Normalização Simétrica:** Aplicar o mesmo transformador de texto no carregamento dos plugins e no processamento do input. |
| Crash `No wakewords found` | `audio_engine` dependia estritamente de chaves deletadas no `config.yaml`. | Implementar Descoberta Dinâmica: varrer pastas físicas (ex: `models/`) em vez de confiar apenas em manifestos de configuração. |
