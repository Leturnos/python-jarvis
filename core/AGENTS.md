# 🧠 Módulo Core - Diretrizes para Agentes

Este diretório contém a lógica de negócios essencial e as integrações para o assistente Jarvis.

## 📁 Detalhamento do Módulo

- **`audio_engine.py`**: 
  - Gerencia os streams do PyAudio.
  - Gerencia os modelos do `openwakeword`.
  - Contém `record_command_audio` para audição ativa após a detecção da palavra de ativação.
  - *Regra:* O processamento de áudio deve ser rápido. Evite operações de bloqueio aqui.

- **`stt_engine.py`**: 
  - Cria um wrapper em volta do modelo local `whisper`.
  - *Regra:* Atualmente usa o modelo `tiny` para desempenho. Mantenha as dependências mínimas para garantir tempos de carregamento rápidos.

- **`llm_agent.py`**: 
  - Faz a interface com o SDK `google-genai`.
  - *Regra:* Os prompts devem impor uma saída JSON estrita. O agente espera o contexto dos comandos disponíveis para realizar o roteamento inteligente entre ações técnicas (`"type": "action"`) e respostas conversacionais (`"type": "chat"`).

- **`dispatcher.py`**: 
  - Roteia os comandos para o motor de execução apropriado (Sistema ou Warp).
  - *Regra:* Deve lidar com configurações JSON dinâmicas de forma segura. Sempre forneça um feedback de TTS (voz) alternativo caso uma ação falhe.

- **`automator.py`**: 
  - Lida com a interação física com o Sistema Operacional (OS) (encontrar janelas, clicar, digitar).
  - Usa uma thread em segundo plano dedicada para o TTS (SAPI5) para evitar bloquear o fluxo de execução.
  - *Regra:* A manipulação de janelas no Windows é frágil. Sempre inclua estratégias de fallback (alternativas em caso de falha), novas tentativas e verificações de segurança (ex: verificar o HWND da janela ativa antes de digitar).

- **`config.py`**: 
  - Carregador centralizado de configuração (YAML + ENV).

- **`utils.py`**: 
  - Funções de ajuda (helpers), incluindo `normalize_text` para correspondência (matching) consistente de comandos e manipulação do Registro do Windows para o autostart.

## ⚠️ Considerações Importantes
- **Especificidades do Windows:** Muitos módulos aqui dependem fortemente das APIs do Windows (`win32gui`, `win32con`, `pythoncom`). Garanta a compatibilidade ao fazer alterações.
- **Tratamento de Erros:** A degradação suave é fundamental. Se o STT ou o LLM falharem, o sistema deve se recuperar e notificar o usuário via TTS (`automator.speak()`) ou pela interface gráfica (UI), em vez de travar (crash).
