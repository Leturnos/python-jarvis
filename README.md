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

Diferente de versões anteriores, agora toda a configuração é feita via **`config.yaml`**. Você não precisa mais mexer no código principal para ajustar o comportamento:

- **`warp_path`**: Caminho do executável do Warp.
- **`working_directory`**: Pasta onde os comandos serão executados.
- **`commands`**: Lista de comandos que o Jarvis deve digitar ao ser ativado.
- **`threshold`**: Sensibilidade da detecção (padrão: 0.4).

## 🗺️ Evolução do Projeto

O Jarvis é um projeto em constante evolução. Para entender a visão de longo prazo e o progresso técnico, consulte os arquivos de documentação detalhada:

- **[ROADMAP.md](./ROADMAP.md)**: Planejamento estratégico das fases de desenvolvimento (Estabilidade, UX, Performance, Inteligência).
- **[TODO.md](./TODO.md)**: Checklist técnico em tempo real das tarefas concluídas e pendentes.

---
*Desenvolvido para facilitar a rotina de quem busca produtividade máxima no Windows.*
