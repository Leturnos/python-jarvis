# 🧠 Módulo Core - Diretrizes para Agentes

Este diretório contém a lógica de negócios essencial e as integrações para o assistente Jarvis.

## 📁 Detalhamento do Módulo

- **`audio_engine.py`**: 
  - Gerencia os streams do PyAudio.
  - Gerencia os modelos do `openwakeword`.
  - Contém `record_command_audio` para audição ativa após a detecção da palavra de ativação.
  - *Regra:* O processamento de áudio deve ser rápido. Evite operações de bloqueio aqui.

- **`stt_engine.py`**: 
  - Cria um wrapper em volta do modelo local `faster-whisper`.
  - *Regra:* Atualmente usa o modelo `tiny` para desempenho. Mantenha as dependências mínimas para garantir tempos de carregamento rápidos.

- **`llm_agent.py`**: 
  - Faz a interface com o SDK `google-genai`.
  - *Regra:* Os prompts devem impor uma saída JSON estrita. O agente espera o contexto dos comandos disponíveis para realizar o roteamento inteligente entre ações técnicas (`"type": "action"`) e respostas conversacionais (`"type": "chat"`).

- **`dispatcher.py`**: 
  - Roteia os comandos para o motor de execução apropriado (Sistema, Warp ou Plugin).
  - *Regra:* Deve validar o `risk_level` via `_check_authorization()` antes da execução.
  - *Regra:* DEVE registrar o resultado de toda tentativa no `history_manager`.

- **`plugin_manager.py`**:
  - Carrega dinamicamente arquivos YAML de automação de `plugins/`.
  - *Regra:* Suporta `shared_actions` via `type: include` e expansão de `${VAR}`.

- **`history_db.py`**:
  - Gerencia o banco SQLite `data/history.db`.
  - *Regra:* Toda execução deve ser persistida para auditoria futura.

- **`security_ui.py`**:
  - Interface modal para autorização de comandos `dangerous`.
  - *Regra:* Deve suportar aprovação híbrida (Clique ou Voz via STT paralelo).

- **`command_palette.py`**:
  - Interface de entrada rápida (Hotkeys).
  - *Regra:* Não deve bloquear a thread principal de áudio.

- **`automator.py`**: 
  - Lida com a interação física com o Sistema Operacional (OS) (encontrar janelas, clicar, digitar).
  - Usa uma thread em segundo plano dedicada para o TTS (SAPI5).
  - *Regra:* Sempre inclua estratégias de fallback e verifique o HWND ativo antes de digitar.

- **`config.py`**: 
  - Carregador centralizado de configuração (YAML + ENV).

- **`utils.py`**: 
  - Funções de ajuda, incluindo `normalize_text` (Symmetrical Normalization).

## ⚠️ Considerações Importantes
- **Especificidades do Windows:** Muitos módulos aqui dependem fortemente das APIs do Windows (`win32gui`, `win32con`, `pythoncom`). Garanta a compatibilidade ao fazer alterações.
- **Tratamento de Erros:** A degradação suave é fundamental. Se o STT ou o LLM falharem, o sistema deve se recuperar e notificar o usuário via TTS (`automator.speak()`) ou pela interface gráfica (UI), em vez de travar (crash).
