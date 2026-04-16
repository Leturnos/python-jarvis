# 🎙️ Python Jarvis

Um assistente de voz minimalista e eficiente desenvolvido em Python para automatizar o fluxo de trabalho no Windows, focado especialmente na integração com o terminal **Warp**.

O projeto utiliza inteligência artificial local para detecção de comandos de voz, permitindo que você prepare seu ambiente de desenvolvimento sem tirar as mãos do teclado.

## ✨ Funcionalidades

- **Detecção de Wake Word Offline:** Utiliza o `openwakeword` para ouvir o comando "Hey Jarvis" em tempo real, sem necessidade de conexão com a internet.
- **Interface Visual (Rich):** Painel interativo no terminal que exibe o status do microfone, volume e pontuação da detecção em tempo real.
- **Gerenciamento Inteligente de Janelas:** Localiza, restaura e foca na janela do terminal Warp automaticamente.
- **Notificações Nativas:** Alertas de balão (Toast) no Windows para confirmar a ativação da automação.
- **Ícone na Bandeja (System Tray):** O Jarvis pode ser minimizado para perto do relógio, permitindo que rode silenciosamente em segundo plano com opção de saída rápida.
- **Automação de Comandos:**
    - Abre automaticamente uma nova aba no Warp (`Ctrl + Shift + T`).
    - Navega para diretórios configurados e executa ferramentas de produtividade.

## 🚀 Tecnologias

- **Linguagem:** [Python 3.13+](https://www.python.org/)
- **IA/Voz:** `openwakeword` (modelos TFLite).
- **Interface & UI:** `rich` (Terminal), `plyer` (Notificações), `pystray` & `Pillow` (System Tray).
- **Automação de Interface:** `pyautogui`, `pygetwindow` e `pywin32`.
- **Gerenciador de Pacotes:** [uv](https://github.com/astral-sh/uv).

## 📋 Pré-requisitos

1. **Sistema Operacional:** Windows 10/11.
2. **Terminal Warp:** Certifique-se de que o [Warp](https://www.warp.dev/) está instalado.
3. **Microfone:** Dispositivo de entrada de áudio configurado como padrão.

## 🛠️ Instalação e Uso

1. **Instale as dependências:**
   ```bash
   uv sync
   ```

2. **Execute o assistente:**
   ```bash
   uv run main.py
   ```

O Jarvis iniciará com uma interface visual no terminal e um ícone na bandeja do sistema.

## ⚙️ Customização

Diferente de versões anteriores, a configuração é separada em dois arquivos para facilitar o versionamento e proteger dados sensíveis.

1. **Crie o arquivo de ambiente local (`.env`)**:
   Copie o arquivo de exemplo fornecido no projeto:
   ```bash
   cp .env.example .env
   ```
   Edite o `.env` com as suas variáveis:
   - **`GEMINI_API_KEY`**: Chave de API do Google Gemini.
   - **`WARP_PATH`**: Caminho local do executável do Warp.
   - **`PROJECT_PATH`**: Caminho do projeto base que os comandos automatizados utilizarão.

2. **Configure o comportamento no `config.yaml`**:
   O arquivo principal é estruturado em blocos lógicos:
   
   - **`jarvis`**:
     - `threshold`: Sensibilidade da detecção (padrão: `0.35`). Valores menores deixam a IA mais sensível.
     - `cooldown_seconds`: Tempo de "descanso" em segundos (padrão: `2.5`).
     - `volume_multiplier`: Multiplicador de ganho do microfone (padrão: `2.0`).

   - **`integrations`**: 
     - Configurações de integrações, referenciando as variáveis de ambiente (ex: `"${WARP_PATH}"`).
     
   - **`wakewords`**: 
     - Cada chave é o nome de um modelo `.tflite`.
     - `action`: Pode ser `warp` ou `system`.
     - `commands`: Lista de comandos a serem digitados. Utiliza expansão de variáveis (ex: `${PROJECT_PATH}`).

## 🧠 Treinando Novos Comandos

O Jarvis suporta múltiplos comandos de voz além do padrão. Para treinar novas palavras-gatilho (arquivos `.tflite`), você pode utilizar o notebook oficial do openWakeWord no Google Colab, que roda 100% na nuvem (não baixa nada na sua máquina):
🔗 [openWakeWord Training Colab](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing#scrollTo=1cbqBebHXjFD)

**Passo a passo resumido:**
1. Faça login com sua conta Google e **faça uma cópia do notebook para o seu Drive** (Arquivo > Salvar uma cópia no Drive) para conseguir editá-lo.
2. Na variável `target_word` (Fase 3), digite a palavra ou frase que deseja treinar (ex: `"jarvis fechar tudo"`).
3. Clique em **Ambiente de execução > Executar tudo**. 
   *(Nota: Na primeira vez, após instalar as bibliotecas na Fase 2, o Colab pode pedir para "Reiniciar a sessão". Se isso ocorrer, reinicie e clique em "Executar tudo" novamente).*
4. Ao final, baixe o arquivo `.tflite` gerado, coloque-o na pasta `models/` do projeto e configure a nova ação no seu `config.yaml`.

## 🚀 Inicialização Automática (Autostart Invisível)

O Jarvis possui integração com a inicialização do Windows através do menu do System Tray (Bandeja do Sistema). 

Ao ativar o **Autostart**, o Jarvis configura automaticamente a inicialização silenciosa. Esse sistema é responsável por iniciar o assistente usando o `uv` de forma **100% invisível**, garantindo que o projeto rode em segundo plano sem abrir nenhuma janela de terminal (console) no Windows.

## 🗺️ Evolução do Projeto

O Jarvis é um projeto em constante evolução. Para entender a visão de longo prazo e o progresso técnico, consulte os arquivos de documentação detalhada:

- **[ROADMAP.md](./ROADMAP.md)**: Planejamento estratégico das fases de desenvolvimento (Estabilidade, UX, Performance, Inteligência).
- **[TODO.md](./TODO.md)**: Checklist técnico em tempo real das tarefas concluídas e pendentes.

---
*Desenvolvido para facilitar a rotina de quem busca produtividade máxima no Windows.*
