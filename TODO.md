# ✅ Checklist de Evolução: Jarvis Project

Esta lista contém as tarefas técnicas necessárias para levar o Jarvis do estado atual para uma ferramenta profissional. As tarefas estão em ordem lógica de execução.

---

## 🛠️ Fase 1: Refatoração e Estabilidade (O Alicerce)
- [ ] **Configuração Externa:** Criar um arquivo `config.yaml` ou `.json` para armazenar `warp_path`, `working_directory` e `wakeword_threshold`.
- [ ] **Tratamento de Erros:** Implementar um bloco `try-except` global para capturar falhas no microfone e tentar reconectar sem fechar o script.
- [ ] **Logging:** Substituir todos os `print()` por `logging.info()` e `logging.error()`, salvando-os em `jarvis.log`.
- [ ] **POO Inicial:** Criar a classe `WarpAutomator` para encapsular a lógica de busca e ativação da janela.
- [ ] **Sensibilidade Dinâmica:** Ajustar o código para ler o threshold de sensibilidade do arquivo de config, facilitando o ajuste fino sem mexer no código.

## 🎨 Fase 2: Experiência do Usuário (Dando Vida)
- [ ] **Feedback de Voz (TTS):** Integrar a biblioteca `pyttsx3` para o Jarvis falar "Sim?" ao detectar o comando e "Pronto!" ao terminar.
- [ ] **Interface de Terminal (Rich):** Implementar um painel visual que mostre o status do microfone em tempo real usando a biblioteca `rich`.
- [ ] **Notificações Nativas:** Adicionar notificações de balão (Toast) no Windows para avisar sobre o status da automação.
- [ ] **Ícone na Bandeja (System Tray):** Implementar o `pystray` para permitir minimizar o Jarvis para perto do relógio do Windows.

## 🚀 Fase 3: Performance e Background (Profissionalismo)
- [ ] **Threads Separadas:** Mover a detecção de áudio para uma thread e a execução de comandos para outra (evita "surdez" temporária do script).
- [ ] **Autostart opcional:** Criar um pequeno script ou comando para adicionar o Jarvis ao "Iniciar" do Windows.
- [ ] **Otimização de Recursos:** Garantir que o script use o mínimo de CPU possível quando estiver apenas em modo de escuta.
- [ ] **Validação de Comandos:** Adicionar uma verificação via `pyautogui` para confirmar se a aba do Warp realmente abriu antes de digitar o `cd`.

## 🧠 Fase 4: Expansão de Inteligência (O Próximo Nível)
- [ ] **Múltiplos Comandos de Voz:** Treinar ou adicionar modelos para "Jarvis, fechar tudo" ou "Jarvis, modo trabalho".
- [ ] **Integração com LLM:** Permitir que, após o comando "Hey Jarvis", o usuário possa falar uma instrução que será processada por uma IA (ex: "Abra o projeto MVP e rode os testes").
- [ ] **Visão Computacional:** Usar screenshots parciais para identificar se o Warp está travado ou esperando por uma atualização.

---

### 💡 Como usar este arquivo
- Marque com um `[x]` as tarefas conforme forem sendo concluídas.
- Use este checklist como guia para futuras solicitações de implementação.
