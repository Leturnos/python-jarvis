# 🗺️ Roadmap de Evolução: Python Jarvis

Este documento detalha as frentes de melhoria para transformar o Python Jarvis de um script utilitário em uma ferramenta de automação profissional e escalável.

---

## 🏗️ 1. Arquitetura e Engenharia de Software
*O objetivo aqui é tornar o código sustentável, testável e fácil de distribuir.*

### 🔹 Modularização e POO
- **Refatoração para Classes:** Criar uma classe base `JarvisEngine` para gerenciar o ciclo de vida do áudio e instâncias de `WindowManager` para lidar com a lógica específica de cada sistema operacional ou aplicação (Warp, VS Code, etc).
- **Injeção de Dependências:** Isolar a detecção de áudio da execução de comandos para permitir a troca fácil do motor de voz (ex: trocar `openwakeword` por outra tecnologia no futuro).

### 🔹 Configuração Externa (Config-as-Code)
- **Arquivo `config.yaml`:** Mover todos os caminhos de arquivos (`warp_path`), comandos de terminal e thresholds de sensibilidade para um arquivo de configuração externo.
- **Suporte a Múltiplos Perfis:** Permitir que o usuário defina "Workspaces" (ex: perfil `frontend` abre o Warp em uma pasta, perfil `backend` em outra).

---

## 🎨 2. Experiência do Usuário (UX/UI)
*Tornar a interação com o assistente fluida, informativa e integrada ao sistema.*

### 🔹 Feedback Multimodal
- **Síntese de Voz (TTS):** Implementar `pyttsx3` ou `Edge-TTS` para confirmações rápidas ("Ambiente pronto!", "Warp não encontrado").
- **Interface Visual (Rich UI):** Utilizar a biblioteca `rich` para transformar o log do terminal em um painel elegante com status do microfone, nível de confiança da detecção e histórico de comandos.

### 🔹 Integração com Windows
- **System Tray (Bandeja do Sistema):** Implementar `pystray` para que o Jarvis rode silenciosamente em segundo plano, incluindo controles de estado (Mute/Disable temporário).
- **Notificações Toast:** Enviar alertas nativos do Windows 10/11 informando o sucesso ou falha de automações longas, além de confirmações de alteração de estado.

---

## 🛡️ 3. Robustez, Performance e Resiliência
*Garantir que o assistente seja rápido, consuma poucos recursos e não falhe silenciosamente.*

### 🔹 Concorrência e Assincronismo
- **AsyncIO/Threading:** Separar a captura de áudio (Input), o processamento do modelo (IA) e a automação de interface (PyAutoGUI) em threads ou processos distintos. Isso evita que o Jarvis "pare de ouvir" enquanto está abrindo o Warp.
- **Gerenciamento de Recursos:** Otimizar o uso de CPU limitando a taxa de amostragem do microfone quando o sistema estiver sob alta carga (ex: durante jogos).

### 🔹 Telemetria e Erros
- **Logging Estruturado:** Implementar rotação de logs para diagnóstico de falhas de permissão do Windows ou erros de foco de janela.
- **Auto-Recuperação:** Se o fluxo de áudio cair ou o microfone for desconectado, o Jarvis deve tentar re-inicializar o stream automaticamente sem travar o programa.

---

## 🧠 4. Inteligência e Expansão de Capacidades
*Onde o Jarvis deixa de ser um "disparador de macros" e passa a ser um assistente inteligente.*

### 🔹 Intenções Baseadas em Contexto (NLU)
- **Comandos Dinâmicos:** Em vez de apenas uma *Wake Word*, usar o `openwakeword` para detectar comandos curtos específicos ou integrar com um modelo de STT (Speech-to-Text) leve como o `faster-whisper` para entender frases como "Jarvis, abra o projeto Alpha".
- **Integração com LLMs (Gemini/GPT):** Enviar comandos complexos para uma LLM processar e retornar um script de automação em tempo real.

### 🔹 Visão Computacional
- **Validação de Estado:** Usar o `OpenCV` ou `PyAutoGUI` para tirar screenshots rápidas e confirmar se o terminal realmente abriu ou se há uma mensagem de erro na tela antes de tentar digitar comandos.

---

## 📦 5. Distribuição e Empacotamento
*Facilitar a instalação e o uso por usuários que não possuem ambiente Python/UV configurado.*

### 🔹 Compilação para Executável (.exe)
- **Nuitka / PyInstaller:** Pesquisar e implementar a compilação do projeto para um único arquivo executável (binário estático). Preferência pelo `Nuitka` pela performance superior e proteção de código.
- **Modo "Windowed" (No Console):** Configurar o binário para rodar como um aplicativo de janela nativo do Windows, eliminando a necessidade de uma janela de terminal visível por padrão.
- **Resource Embedding:** Utilizar técnicas de inclusão de arquivos (Data Files) para embutir os modelos `.onnx` do OpenWakeWord, o ícone `icon.ico` e possíveis arquivos de áudio de resposta diretamente no `.exe`.

### 🔹 Instalador e Autostart Nativo
- **Setup Profissional (Inno Setup / Wix):** Criar um instalador que gerencie a pasta de instalação em `AppData` ou `Program Files`.
- **Configuração de Registro:** Automatizar a criação da chave de `Run` no registro do Windows para garantir que o Autostart funcione mesmo se o usuário deletar o atalho manual.
- **Auto-Update:** Pesquisar mecanismos simples para o Jarvis verificar se há uma nova versão disponível no GitHub e sugerir a atualização.

---
*Este roadmap é um documento vivo e deve ser atualizado conforme novas necessidades e tecnologias surjam.*
