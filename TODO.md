# ✅ Checklist de Evolução: Jarvis Project

Esta lista contém as tarefas técnicas necessárias para levar o Jarvis do estado atual para uma ferramenta profissional. As tarefas estão em ordem lógica de execução.

---

## 🛠️ Fase 1: Refatoração e Estabilidade (O Alicerce)
- [x] **Configuração Externa:** Criar um arquivo `config.yaml` ou `.json` para armazenar `warp_path`, `working_directory` e `wakeword_threshold`.
- [x] **Tratamento de Erros:** Implementar um bloco `try-except` global para capturar falhas no microfone e tentar reconectar sem fechar o script.
- [x] **Logging:** Substituir todos os `print()` por `logging.info()` e `logging.error()`, salvando-os em `jarvis.log`.
- [x] **POO Inicial:** Criar a classe `WarpAutomator` para encapsular a lógica de busca e ativação da janela.
- [x] **Sensibilidade Dinâmica:** Ajustar o código para ler o threshold de sensibilidade do arquivo de config, facilitando o ajuste fino sem mexer no código.
- [x] **Sistema de Plugins (Arquitetura):** Refatorar o roteamento de comandos (`dispatcher.py`) para carregar "habilidades" dinamicamente de uma pasta `plugins/` *(Cuidado: evitar overengineering, manter simples)*.
- [x] **Mini DSL Declarativa:** Criar formato simplificado (`.yaml` ou `.json`) para definir comandos de voz e suas respectivas automações.

## 🎨 Fase 2: Experiência do Usuário (Dando Vida)
- [x] **Feedback de Voz (TTS):** Integrar a biblioteca `pyttsx3` para o Jarvis falar "Sim?" ao detectar o comando e "Pronto!" ao terminar.
- [x] **Interface de Terminal (Rich):** Implementar um painel visual que mostre o status do microfone em tempo real usando a biblioteca `rich`.
- [x] **Notificações Nativas:** Adicionar notificações de balão (Toast) no Windows para avisar sobre o status da automação.
- [x] **Ícone na Bandeja (System Tray):** Implementar o `pystray` para permitir minimizar o Jarvis para perto do relógio do Windows.
- [x] **Temporizador de Desativação (Disable for...):** Opção para silenciar o Jarvis por 30min, 1h ou 3h via menu da bandeja.
- [x] **Command Palette:** Criar paleta de comandos (tipo Ctrl+Shift+P) misturando input de teclado com o processamento do assistente.

## 🚀 Fase 3: Performance e Background (Profissionalismo)
- [x] **Threads Separadas:** Mover a detecção de áudio para uma thread e a execução de comandos para outra (evita "surdez" temporária do script).
- [x] **Autostart opcional:** Criar um pequeno script ou comando para adicionar o Jarvis ao "Iniciar" do Windows.
- [x] **Início Minimizado:** Suporte ao argumento `--minimized` para rodar diretamente na bandeja ao iniciar o Windows.
- [x] **Instância Única (Mutex):** Impedir múltiplas instâncias e restaurar a janela principal ao tentar abrir novamente.
- [x] **Otimização de Recursos:** Garantir que o script use o mínimo de CPU possível quando estiver apenas em modo de escuta.
- [x] **Validação de Comandos:** Adicionar uma verificação via `pyautogui` para confirmar se a aba do Warp realmente abriu antes de digitar o `cd`.
- [x] **Self-healing de Áudio:** Implementar rotina de *watchdog* que verifique o stream do microfone a cada N segundos e force o reset do dispositivo (nível de SO) se detectar silêncio absoluto anômalo ou erros de I/O.
- [x] **Sistema de Permissões:** Formalizar as roles e security ranks (já iniciados) para requerer aprovação prévia em comandos destrutivos.

## ⚙️ Fase 3.5: O Núcleo Profissional (Estabilização Pré-Release)
- [x] **State Machine Central:** Implementar máquina de estados centralizada (IDLE, LISTENING, THINKING, CONFIRMING_DRY_RUN, EXECUTING, ERROR) para coordenar a UI e evitar race conditions.
- [x] **Dry-run & Explainability:** Integrar com a State Machine para exibir na UI o plano/script do LLM antes da execução, exigindo confirmação.
- [x] **Rate Limiting & Quotas:** Criar verificador de consumo de API (tokens/chamadas) que bloqueia execuções ao atingir limites configurados no `config.yaml`.
- [x] **Job Queue Interna Leve:** Substituir chamadas isoladas por uma fila estruturada nativa (`asyncio.Queue` ou `queue.Queue` com dataclasses de Job, retries, status).
- [ ] **Replay de Comandos & Macros:** Criar intenções para repetir o último comando salvo no `history.db` e para agrupar uma sequência recente como uma macro no `.yaml`.
- [ ] **Integração com Keyring (Segurança):** Migrar a chave da API do LLM do arquivo `.env` em texto plano para o gerenciador de credenciais seguro do Sistema Operacional.
- [ ] **Explain what I did:** Permitir que o usuário pergunte "o que você fez?" e injetar o último log de ação para o LLM gerar uma explicação humana.
- [ ] **Observabilidade (Métricas Leves):** Salvar no SQLite métricas simples como latência da API, cache hit rate e tempo de execução dos comandos.

## 🧠 Fase 4: Expansão de Inteligência (O Próximo Nível)
- [x] **Múltiplos Comandos de Voz:** Treinar ou adicionar modelos para "Jarvis, fechar tudo" ou "Jarvis, modo trabalho".
- [x] **Integração com LLM:** Permitir que, após o comando "Hey Jarvis", o usuário possa falar uma instrução que será processada por uma IA (ex: "Abra o projeto MVP e rode os testes").
- [x] **Validação de Estado:** Substituir possíveis abordagens de Screenshot por *Process Monitoring*, *Window State tracking* e *Timeout Detection* para gerenciar travamentos de UI.
- [x] **Histórico e Memória:** Criar um banco de dados local SQLite (`history.db`) para armazenar logs de comandos reconhecidos, data, horário e status de execução.
- [x] **Cache de Respostas LLM:** Configurar um sistema de cache de similaridade semântica para retornar scripts instantâneos caso a mesma intenção de voz seja detectada novamente.
- [x] **Prompt Injection Guard:** Adicionar camada de sanitização estrita (Regex + validação heurística) nos *outputs* da LLM antes de enviá-los ao `subprocess` ou `pyautogui`.

## 📊 Fase 5: Observability (Monitoramento)
- [x] **Performance Profiling:** Implementar rastreamento do tempo de execução de rotinas, latência de chamadas de LLM e de modelos locais de IA.
- [x] **Memory Monitoring:** Monitorar o consumo de RAM da thread principal do OpenWakeWord e JarvisEngine em execuções prolongadas no background.

## 📦 Fase 6: Distribuição (Entregando o Produto)
- [ ] **Compilação (.exe):** Usar `Nuitka` ou `PyInstaller` para transformar o projeto em um executável autônomo e otimizado.
- [ ] **Bundle de Recursos:** Embutir modelos `.onnx`, arquivos de áudio e o ícone `.ico` dentro do binário final.
- [ ] **Modo "Windowed":** Configurar o build para que o executável rode sem abrir a janela preta do console por padrão.
- [ ] **Portable Mode:** Gerar build zipada que não exige privilégios de administrador nem instalação no sistema.
- [ ] **Instalador (MSI/EXE):** Criar um setup profissional (ex: Inno Setup) que configure o Autostart e atalhos automaticamente.
- [ ] **Update Automático OTA:** Implementar a lógica de checagem de versão na inicialização e download automático da nova *release* (`.exe`), substituindo o binário na próxima inicialização.

## 🔬 Fase 7: Experimental Features
- [ ] **Streaming STT:** Substituir o STT atual por uma implementação baseada em *chunks* ou *websockets* para processar o áudio e exibir o texto na UI em tempo real, mitigando a latência de processamento em batch.

---

### 💡 Como usar este arquivo
- Marque com um `[x]` as tarefas conforme forem sendo concluídas.
- Use este checklist como guia para futuras solicitações de implementação.