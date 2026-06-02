# 🎙️ Checklist de Teste Manual do Jarvis

Este documento fornece as instruções passo a passo para testar manualmente as features visuais e físicas do Jarvis locais no Windows.

---

## 🚀 Como Iniciar

No terminal, execute:
```powershell
uv run main.py
```

---

## 📋 Lista de Validação de Componentes

### 1. Inicialização e Instância Única (Mutex)
- [ ] Abra o Jarvis pela primeira vez (`uv run main.py`). Confirme que a janela gráfica abre no tema escuro.
- [ ] Abra um segundo terminal e execute o mesmo comando (`uv run main.py`).
- [ ] **Esperado**: A segunda execução deve detectar a instância única, trazer a janela do primeiro Jarvis para o primeiro plano (foco) e fechar o segundo processo limpo.

### 2. Bandeja do Sistema (System Tray) e Notificações
- [ ] Minimize a janela do Jarvis clicando no botão fechar `[X]` ou minimizando.
- [ ] **Esperado**: O aplicativo deve ir para a bandeja do sistema (perto do relógio). A primeira vez que for ocultado, deve exibir uma notificação toast no Windows: *"O Jarvis continua rodando em segundo plano."*
- [ ] Dê dois cliques no ícone do Jarvis no relógio. A janela do painel principal (Dashboard) deve reaparecer.
- [ ] Clique com o botão direito no ícone da bandeja.
- [ ] **Esperado**: Visualizar opções como:
  - *Show Dashboard*
  - *Listening (Active)*
  - *On (Suspended)*
  - *Disable for...* (Submenu com durações 30m, 1h, 3h)
  - *Autostart*
  - *Quit*

### 3. Silenciamento Temporário (Mute Timer)
- [ ] Clique com o botão direito no ícone da bandeja e selecione **Disable for...** -> **30 min**.
- [ ] **Esperado**:
  - O status no Dashboard muda para `MUTED` (tema cinza/vermelho).
  - O processamento de áudio do microfone é desligado.
  - Uma notificação toast informa que o Jarvis voltará a ouvir após o tempo determinado.
- [ ] Clique novamente na bandeja e selecione **Listening (Active)** para restabelecer o modo normal.

### 4. Paleta de Comandos (Teclado)
- [ ] Com o Jarvis ativo, pressione o atalho global `Ctrl + Alt + P`.
- [ ] **Esperado**: A paleta de comandos (barra de pesquisa escura) aparece no centro da tela.
- [ ] Digite `programar` e navegue com as setas para baixo e para cima.
- [ ] Pressione `Enter` para selecionar. A paleta se fecha e o comando de plugin é acionado.

### 5. Modo Gamer e Apresentações (Auto-Suspend)
- [ ] Deixe o Dashboard do Jarvis visível.
- [ ] Abra o navegador ou um player de vídeo e pressione `F11` (Tela Cheia).
- [ ] **Esperado**: O status do Jarvis no console e no Dashboard deve mudar imediatamente para `SUSPENDED` (Fullscreen).
- [ ] Saia da tela cheia.
- [ ] **Esperado**: Após 2 segundos (histerese para evitar flickering), o Jarvis deve voltar ao estado `IDLE` / `Listening` e continuar a escuta de voz.

### 6. Ativação por Voz (Wake Word e STT)
- [ ] Fale de forma clara próximo ao microfone: *"Hey Jarvis"*.
- [ ] **Esperado**:
  - O Jarvis emite um feedback de voz falado *"Sim?"*.
  - O status no dashboard muda para `LISTENING` (Gravando...).
  - O nível do microfone no dashboard registra variação de volume.
- [ ] Diga em seguida: *"Ligar o servidor"* ou *"Rodar o backend"*.
- [ ] **Esperado**: O Jarvis processa o áudio, transcreve com Whisper, detecta a intenção local e executa as ações em sequência abrindo o terminal e digitando `npm run dev`.

### 7. Caixa de Confirmação de Risco (Dry-run e PromptGuard)
- [ ] Ative o Jarvis com *"Hey Jarvis"* e diga *"Modo descanso"* ou *"Encerrar expediente"*.
- [ ] **Esperado**:
  - A intenção identificada é `fechar_tudo`, configurada como `dangerous`.
  - O Jarvis emite um feedback de voz: *"Planejo o seguinte: Executando plugin: fechar_tudo. Posso executar?"*.
  - Abre-se uma caixa de diálogo Tkinter no centro da tela com botões SIM/NÃO.
  - A aplicação entra no estado `CONFIRMING_DRY_RUN`.
- [ ] Teste a aprovação por **Voz**: Fale *"Sim"* ou *"Confirma"*. A caixa de diálogo se fecha e o comando simula a execução (`echo "Simulating close all..."`).
- [ ] Teste a rejeição por **Clique**: Dispare o comando novamente e clique no botão **NÃO**. O Jarvis cancela a ação e retorna ao repouso.

### 8. Macros e Repetição
- [ ] Execute algum comando com sucesso.
- [ ] Diga *"Faz de novo"* ou *"De novo"*. A última ação bem sucedida deve rodar novamente.
- [ ] Após executar alguns comandos, diga *"Salvar como macro"*. O Jarvis propõe uma macro inteligente contendo os passos anteriores para você salvar.
