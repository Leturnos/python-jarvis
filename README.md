# 🎙️ Python Jarvis

Um assistente de voz minimalista e eficiente desenvolvido em Python para automatizar o fluxo de trabalho no Windows, focado especialmente na integração com o terminal **Warp**.

O projeto utiliza inteligência artificial local para detecção de comandos de voz, permitindo que você prepare seu ambiente de desenvolvimento sem tirar as mãos do teclado.

## ✨ Funcionalidades

-   **Detecção de Wake Word Offline:** Utiliza o `openwakeword` para ouvir o comando "Hey Jarvis" em tempo real, sem necessidade de conexão com a internet.
-   **Gerenciamento Inteligente de Janelas:** Localiza, restaura e foca na janela do terminal Warp automaticamente, mesmo que ele esteja minimizado ou fechado.
-   **Automação de Comandos:**
    -   Abre automaticamente uma nova aba no Warp (`Ctrl + Shift + T`).
    -   Navega para diretórios específicos (ex: `C:\Programacao\MVP`).
    -   Executa ferramentas de produtividade (ex: comando `gemini`).
-   **Digitação Segura:** Utiliza manipulação de clipboard para garantir que caracteres especiais e caminhos do Windows sejam inseridos corretamente no terminal.

## 🚀 Tecnologias

-   **Linguagem:** [Python 3.13+](https://www.python.org/)
-   **IA/Voz:** `openwakeword` (baseado em modelos TFLite).
-   **Automação de Interface:** `pyautogui`, `pygetwindow` e `pywin32`.
-   **Gerenciamento de Processos:** `psutil`.
-   **Gerenciador de Pacotes:** [uv](https://github.com/astral-sh/uv) (extremamente rápido e moderno).

## 📋 Pré-requisitos

1.  **Sistema Operacional:** Windows (devido às APIs de manipulação de janelas `win32gui`).
2.  **Terminal Warp:** Certifique-se de que o [Warp](https://www.warp.dev/) está instalado.
3.  **Microfone:** Um dispositivo de entrada de áudio configurado como padrão.

## 🛠️ Instalação e Uso

Este projeto utiliza o `uv` para gerenciar dependências de forma simplificada.

1.  **Instale as dependências:**
    ```bash
    uv sync
    ```

2.  **Execute o assistente:**
    ```bash
    uv run main.py
    ```

O script ficará em modo de escuta. Assim que detectar "Hey Jarvis", ele iniciará a sequência de automação configurada.

## ⚙️ Customização

Para adaptar o Jarvis ao seu fluxo, você pode editar o arquivo `main.py`:

-   **Caminho do Warp:** Altere a variável `warp_path` caso seu executável esteja em outro local.
-   **Comandos:** Modifique as linhas dentro do bloco `try` no loop principal para alterar os comandos enviados ao terminal (ex: trocar o diretório ou o comando final).

---
*Desenvolvido para facilitar a rotina de quem busca produtividade máxima no Windows.*
