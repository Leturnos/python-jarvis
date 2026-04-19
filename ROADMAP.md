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

### 🔹 Sistema de Plugins (Extensibilidade)
- **Arquitetura Baseada em Eventos:** Criar uma arquitetura baseada em eventos ou *hooks* que permita a adição de novas automações (ex: "plugin-vscode", "plugin-spotify") sem alterar o núcleo do projeto. *(Aviso: Manter a implementação simples e evitar overengineering. O foco é facilitar a adição de comandos sem criar um framework excessivamente complexo).*

### 🔹 Automação Baseada em DSL
- **Mini DSL Declarativo:** Criar uma mini DSL (Domain Specific Language) em YAML ou JSON para definir intenções de voz e suas respectivas automações de forma simplificada, separando a lógica da configuração de novos comandos.

---

## 🎨 2. Experiência do Usuário (UX/UI)
*Tornar a interação com o assistente fluida, informativa e integrada ao sistema.*

### 🔹 Interface de Comandos
- **Command Palette:** Implementar uma interface tipo VSCode (Ctrl+Shift+P) que misture o processamento de comandos de voz com atalhos de teclado, garantindo uma execução rápida e híbrida.

### 🔹 Feedback Multimodal
- **Síntese de Voz (TTS):** Implementar `pyttsx3` ou `Edge-TTS` para confirmações rápidas ("Ambiente pronto!", "Warp não encontrado").
- **Interface Visual (Rich UI):** Utilizar a biblioteca `rich` para transformar o log do terminal em um painel elegante com status do microfone, nível de confiança da detecção e histórico de comandos.

### 🔹 Integração com Windows
- **System Tray (Bandeja do Sistema):** Implementar `pystray` para que o Jarvis rode silenciosamente em segundo plano, incluindo controles de estado (Mute/Disable temporário).
- **Notificações Toast:** Enviar alertas nativos do Windows 10/11 informando o sucesso ou falha de automações longas, além de confirmações de alteração de estado.

---

## 🛡️ 3. Robustez, Performance e Resiliência
*Garantir que o assistente seja rápido, consuma poucos recursos e não falhe silenciosamente.*

### 🔹 Segurança e Permissões
- **Permission System:** Formalizar o sistema de permissões (Security Ranks já em implementação) exigindo confirmação explícita do usuário para comandos com alto potencial destrutivo.

### 🔹 Monitoramento de Estado
- **Validação de Execução:** Em vez de usar capturas de tela, implementar `Process Monitoring`, verificação de `Window State` e `Timeout Detection` para confirmar de forma confiável se as aplicações de destino (ex: Warp) abriram ou se o terminal travou.

### 🔹 Concorrência e Assincronismo
- **AsyncIO/Threading:** Separar a captura de áudio (Input), o processamento do modelo (IA) e a automação de interface (PyAutoGUI) em threads ou processos distintos. Isso evita que o Jarvis "pare de ouvir" enquanto está abrindo o Warp.
- **Gerenciamento de Recursos:** Otimizar o uso de CPU limitando a taxa de amostragem do microfone quando o sistema estiver sob alta carga (ex: durante jogos).

### 🔹 Telemetria e Erros
- **Logging Estruturado:** Implementar rotação de logs para diagnóstico de falhas de permissão do Windows ou erros de foco de janela.
- **Auto-Recuperação e Self-healing:** Se o fluxo de áudio cair ou o microfone for desconectado, o Jarvis deve tentar re-inicializar o stream automaticamente sem travar o programa. Expandir para reiniciar ativamente o serviço de áudio do sistema operacional ou trocar para um microfone de fallback caso o principal falhe ou seja desconectado silenciosamente.

### 🔹 Otimização de IA
- **Cache Semântico para LLMs:** Implementar um banco local (ex: SQLite, Redis ou Vector DB leve) para armazenar intenções e respostas já resolvidas, reduzindo a latência, custos de API e dependência de internet para comandos repetitivos.

---

## 🧠 4. Inteligência e Expansão de Capacidades
*Onde o Jarvis deixa de ser um "disparador de macros" e passa a ser um assistente inteligente.*

### 🔹 Intenções Baseadas em Contexto (NLU)
- **Comandos Dinâmicos:** Em vez de apenas uma *Wake Word*, usar o `openwakeword` para detectar comandos curtos específicos ou integrar com um modelo de STT leve como o `faster-whisper` para entender frases como "Jarvis, abra o projeto Alpha".
- **Integração com LLMs (Gemini/GPT):** Enviar comandos complexos para uma LLM processar e retornar um script de automação em tempo real.
- **Memória e Histórico de Comandos:** Desenvolver um sistema de persistência que aprenda as preferências do usuário, permitindo comandos como "Jarvis, repita a rotina de ontem" e facilitando auditoria de segurança.

### 🔹 Segurança de IA
- **Prompt Injection Guard:** Como o Jarvis automatizará comandos de terminal com base em LLMs, adicionar uma camada de sanitização e moderação (ex: via *guardrails* ou um LLM menor de auditoria) para impedir que o sistema execute scripts maliciosos injetados na voz.

---

## 📊 5. Observability e Monitoramento
*Garantir a previsibilidade e diagnosticar gargalos de forma eficiente.*

### 🔹 Métricas e Performance
- **Performance Profiling:** Adicionar rastreamento de tempo de execução, latência de chamadas do LLM e do STT para localizar gargalos do sistema.
- **Memory Usage:** Monitoramento contínuo da memória, especialmente para as threads da IA (OpenWakeWord/JarvisEngine), evitando leaks em longas sessões de background.

---

## 📦 6. Distribuição e Empacotamento
*Facilitar a instalação e o uso por usuários que não possuem ambiente Python/UV configurado.*

### 🔹 Compilação para Executável (.exe)
- **Nuitka / PyInstaller:** Pesquisar e implementar a compilação do projeto para um único arquivo executável (binário estático). Preferência pelo `Nuitka` pela performance superior e proteção de código.
- **Modo "Windowed" (No Console):** Configurar o binário para rodar como um aplicativo de janela nativo do Windows, eliminando a necessidade de uma janela de terminal visível por padrão.
- **Resource Embedding:** Utilizar técnicas de inclusão de arquivos (Data Files) para embutir os modelos `.onnx` do OpenWakeWord, o ícone `icon.ico` e possíveis arquivos de áudio de resposta diretamente no `.exe`.

### 🔹 Instalação e Modos de Execução
- **Setup Profissional (Inno Setup / Wix):** Criar um instalador que gerencie a pasta de instalação em `AppData` ou `Program Files`.
- **Portable Mode:** Fornecer uma versão autossuficiente (como um pacote ZIP) permitindo rodar a aplicação sem instalador ou privilégios de administrador.
- **Configuração de Registro:** Automatizar a criação da chave de `Run` no registro do Windows para garantir que o Autostart funcione mesmo se o usuário deletar o atalho manual.

### 🔹 Updates
- **Auto-Update OTA (Over-The-Air):** Implementar um mecanismo silencioso (via GitHub Releases ou AWS S3) que baixe atualizações em segundo plano e reinicie a aplicação transparentemente.

---

## 🔬 7. Experimental Features
*Inovações a serem testadas e avaliadas para viabilidade técnica.*

### 🔹 Pesquisa de Tecnologias
- **Streaming STT (Reconhecimento Contínuo):** Transição de um modelo de "grava e depois processa" para *Streaming Speech-to-Text* (ex: Deepgram, Google Cloud STT ou Whisper em streaming local), permitindo a execução do comando enquanto o usuário ainda está falando.

---
*Este roadmap é um documento vivo e deve ser atualizado conforme novas necessidades e tecnologias surjam.*