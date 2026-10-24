# 🎙️ Python Jarvis

[![GitHub Release](https://img.shields.io/github/v/release/Leturnos/python-jarvis?color=blue&label=Vers%C3%A3o%20Mais%20Recente)](https://github.com/Leturnos/python-jarvis/releases/latest)
[![Windows](https://img.shields.io/badge/Plataforma-Windows%2010%20%7C%2011-0078D6?logo=windows)](https://github.com/Leturnos/python-jarvis)

Um assistente virtual leve e eficiente para Windows, focado em automatizar suas tarefas do dia a dia. Com ele, você prepara seu ambiente de trabalho ou roda scripts apenas usando a voz ou o teclado.

Chega de clicar dezenas de vezes para começar a trabalhar. Diga "Hey Jarvis", peça o que precisa, e ele faz por você.

## ✨ O que ele faz?

- **Interface e Menus em Português (🇧🇷):** Toda a experiência de uso (menu da bandeja, painel de status, histórico e notificações) foi desenhada em português brasileiro fluído e natural.
- **Onboarding Gráfico Sem Atrito (🔑):** Se for sua primeira vez e ainda não houver chave de API configurada, o Jarvis não quebra silenciosamente: ele abre a tela de Configurações com orientações claras para você salvar sua chave direto no Gerenciador de Credenciais do Windows (Keyring).
- **Ativação Inteligente (🎙️):** Você escolhe como o Jarvis deve te ouvir. Ele pode ficar sempre atento à frase "Hey Jarvis", funcionar apenas quando você aperta uma tecla (Push-to-Talk), ou ambos!
- **Reconhecimento de Voz com Filtro VAD (🛡️):** O motor de Speech-to-Text (`faster-whisper`) utiliza filtragem Silero VAD integrada, eliminando alucinações e palavras fantasmas geradas por ruídos de fundo, cliques ou respiração.
- **Resposta por Voz Instantânea e Interrompível (⚡):** O sintetizador de fala (TTS) processa o texto oração por oração em tempo real e interrompe a fala imediatamente se você acionar a palavra de ativação ou o Push-to-Talk.
- **Controle de Mídia Inteligente (Spotify 🎵):** Diga ao Jarvis para tocar um artista, música ou playlist. Ele trará o Spotify para o primeiro plano e usará inteligência visual (OpenCV) para localizar e clicar nos botões corretos na tela, iniciando a música instantaneamente. Veja o [Guia de Configuração de Mídia](./data/media/README.md) para aprender a cadastrar suas playlists favoritas.
- **Respostas Diretas e Ferramentas Dinâmicas (🌦️ 📈):** Pergunte sobre o tempo ("vai chover hoje em Itamonte?") ou sobre ações e mercado ("como está a cotação de PETR4?"). O Jarvis consulta ferramentas especializadas e responde de forma objetiva e inteligente.
- **Modo Gamer e Reunião (Auto-Suspend):** O Jarvis é educado. Se ele perceber que você está jogando ou em uma apresentação (tela cheia), ele entra em suspensão automaticamente para não te interromper.
- **Entende seu jeito de falar (IA Multi-Provedor):** Não precisa decorar comandos rígidos. Fale naturalmente com suporte a Google Gemini, OpenAI, Anthropic, DeepSeek e OpenRouter.
- **Paleta de Comandos (⌨️):** Falar alto nem sempre é o ideal. Aperte `Ctrl + Shift + P` (ou pelo menu da bandeja) a qualquer momento para abrir uma barra de pesquisa rápida na tela e execute suas automações silenciosamente.
- **Aprende Novas Habilidades (Plugins YAML):** Ensinar algo novo para o Jarvis é tão fácil quanto escrever uma receita de bolo em um arquivo de texto.
- **Invisível e Seguro:** Roda silenciosamente na bandeja do Windows (System Tray) e possui um sistema de segurança que bloqueia ou pede confirmação antes de executar ações perigosas.
- **Controle de Descanso:** Você pode dizer "Jarvis, ir dormir" e ele descarregará os modelos pesados da memória para economizar energia do seu PC, ficando em modo de espera até que você o acorde manualmente.

### 🧠 Comandos de Sistema e Conversação
Exemplos de como usar as capacidades de memória, ferramentas e controle:
- **Clima e Previsão**: "Vai chover hoje em Itamonte?", "Como está o tempo em São Paulo?".
- **Cotações e Mercado**: "Qual a cotação da Apple hoje?", "Como está o dólar?".
- **Descansar/Silenciar**: "Jarvis, ir dormir", "Silenciar", "Parar de ouvir".
- **Repetir último comando**: "Faz de novo", "De novo".
- **Salvar como macro**: "Salvar como macro", "Gravar sequência", "Salve isso".

## 📋 Pré-requisitos

1. **Sistema Operacional:** Windows 10 ou 11.
2. **Terminal (Opcional):** Suporte nativo para o [Warp](https://www.warp.dev/), mas funciona com qualquer aplicação.
3. **Microfone:** Qualquer microfone padrão conectado ao PC.

## 🛠️ Como Baixar e Usar

### ⚡ Para Usuários (Download Rápido sem Programar)

Se você quer apenas usar o Jarvis no seu dia a dia sem precisar instalar Python ou configurar código:

1. **Acesse as Releases:** Na barra lateral direita desta página no GitHub, clique na seção **[Releases](https://github.com/Leturnos/python-jarvis/releases/latest)** (ou acesse diretamente a [Última Release](https://github.com/Leturnos/python-jarvis/releases/latest)).
2. **Baixe o Arquivo:** Na seção **Assets** no final da página da release, clique em `Jarvis-windows-x64.zip` para fazer o download.
3. **Extraia o ZIP:** Clique com o botão direito no arquivo baixado e selecione **"Extrair Tudo..."** para a pasta de sua preferência (por exemplo, `C:\Programas\Jarvis\` ou dentro da sua pasta de usuário).
4. **Abra o Jarvis:** Entre na pasta extraída e dê dois cliques no executável `Jarvis.exe`.
5. **Configuração Inicial:** Na primeira execução, o Jarvis abrirá automaticamente a tela de **Configurações** para você escolher seu provedor de IA favorito (como Google Gemini, OpenAI, Anthropic, DeepSeek, etc.) e salvar sua chave de API com segurança no Gerenciador de Credenciais do Windows.
6. **Pronto!** O Jarvis ficará ativo e silencioso na bandeja do Windows (perto do relógio). Você já pode falar "Hey Jarvis" ou pressionar `Ctrl + Shift + P` para usar a paleta de comandos.

> 💡 **Atualizações Automáticas:** Uma vez instalado, o próprio Jarvis avisa quando houver novas versões e atualiza automaticamente pelo painel de Configurações!

---

### 💻 Para Desenvolvedores (Modo Desenvolvimento)

O projeto utiliza o gerenciador de pacotes rápido `uv`.

1. **Instale as dependências:**
   ```bash
   uv sync
   ```

2. **Dê vida ao assistente:**
   ```bash
   uv run main.py
   ```

O Jarvis vai aparecer na sua bandeja do Windows (perto do relógio). Se for a primeira inicialização e você ainda não configurou uma chave de API, o Jarvis abrirá automaticamente a aba de **Configurações** para você salvar a chave do seu provedor favorito (`Gemini`, `OpenAI`, `Anthropic`, `DeepSeek` ou `OpenRouter`) de forma segura com um clique!

### 📦 Gerando o Executável (.exe) Portátil
Você pode empacotar o Jarvis em um executável autônomo do Windows (sem console preta de terminal, inicialização rápida e todos os modelos de áudio embutidos):

```bash
uv run python scripts/build_exe.py
```

O bundle completo será gerado em `dist/Jarvis/Jarvis.exe` e o pacote compactado em `dist/Jarvis-windows-x64.zip`.

#### 💾 Persistência de Dados e Modo Portátil (`portable.flag`)
- **Padrão (%APPDATA%):** Para que você possa atualizar o executável para novas versões sem nunca perder seus dados ou ter que reconfigurar caminhos, o Jarvis armazena seu `config.yaml`, bancos de dados (`history.db`, `llm_cache.db`), preferências e logs em `%APPDATA%\Jarvis`. No primeiro boot, o `config.yaml` de fábrica é semeado automaticamente para o seu perfil.
- **Acesso Rápido:** Você pode abrir o `config.yaml` diretamente no seu editor padrão ou navegar até a pasta de configuração clicando nos botões de documento e pasta no canto superior da aba **Configurações**.
- **Modo Portátil (`portable.flag`):** Se você prefere rodar o Jarvis de forma 100% isolada e autocontida (ex: em um pendrive ou pasta dedicada) sem gravar nada no seu Windows, basta criar um arquivo vazio chamado `portable.flag` na mesma pasta do executável `Jarvis.exe`. O Jarvis identificará a flag no boot e manterá todas as configurações, bancos e logs na própria pasta local.

#### 🔄 Atualizações Automáticas (Auto-Updater)
O Jarvis possui um sistema de atualização integrado com o GitHub Releases:
- **Trava Inteligente no Boot:** Verifica novidades em segundo plano sem lentidão e sem popups repetitivos (intervalo mínimo padrão de 24 horas).
- **Respeito ao Usuário:** As opções *"Lembrar Mais Tarde"* (adiamento por 24h) e *"Ignorar Esta Versão"* garantem que você nunca seja interrompido durante seu fluxo de trabalho.
- **Verificação Manual:** A qualquer momento, acesse a aba **Configurações** no Painel do Jarvis para conferir novidades e atualizar com um clique.

## ⚙️ Configurando o Jarvis

Nós separamos as coisas para facilitar sua vida. Existem três formas principais de personalizar o Jarvis:

1. **Pela Própria Interface Gráfica (Recomendado):**
   Abra o **Painel do Jarvis** clicando com o botão direito no ícone da bandeja e escolhendo **Mostrar Painel** (ou dois cliques no ícone). Na aba **Configurações**:
   - Escolha o provedor de IA ativo (`Gemini`, `OpenAI`, `Anthropic`, `DeepSeek` ou `OpenRouter`).
   - Digite ou cole sua chave de API e clique em **Salvar Chave** (ela será guardada criptografada no Windows Credential Manager / Keyring).
   - Ajuste o perfil de desempenho de acordo com seu hardware.
   - Configure sua **Localização** (cidade padrão para previsão do tempo) com atualização em tempo real.
   - Abra o arquivo `config.yaml` no seu editor ou abra a pasta no Explorer com um clique nos botões do cabeçalho.

2. **Arquivo `.env` (Opcional - Migração Automática):**
   Se preferir variáveis de ambiente, copie `.env.example` para `.env` e defina suas chaves (ex: `GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.). Ao iniciar, o Jarvis detecta a chave e a migra automaticamente para o Keyring seguro do Windows, permitindo que você remova o segredo do arquivo de texto por segurança.

3. **Arquivo `config.yaml` (Ajustes de Motor):**
   Aqui você mexe na "mecânica" do Jarvis.
   - **Ativação de Voz (`voice_activation`):**
     - `mode`: Escolha entre `hybrid` (Frase + Tecla), `push_to_talk` (Apenas tecla), `always_listening` (Apenas frase) ou `disabled`.
     - `push_to_talk`: Configure a tecla (ex: `ctrl+alt`) e se quer segurar para falar (`hold`) ou apenas um toque (`toggle`).
     - `auto_suspend`: Ative o `fullscreen: true` para o Jarvis silenciar automaticamente em jogos ou vídeos em tela cheia.
   - **Paleta de Comandos (`command_palette`):** Configure a tecla de atalho global para a paleta (padrão: `ctrl+shift+p`).
   - **Cérebro do Jarvis (`llm`):**
     - `active_provider`: Escolha entre `gemini`, `openai`, `anthropic`, `deepseek` ou `openrouter`.
     - `proactivity`: Escolha `objective` (padrão: respostas curtas, diretas e naturais) ou `conversational` (respostas mais explicativas).
   - **Localização Padrão (`location`):**
     - Defina sua cidade padrão para consultas de clima (ex: `São Paulo`).
   - **Voz do Jarvis (`tts`):** No campo `voice_keyword`, coloque parte do nome da voz que você tem instalada no Windows (ex: "maria", "zira", "david"). Se ele não encontrar a que você pediu, ele tentará usar uma voz em Português automaticamente.

3. **A pasta `plugins/` (Ensinando novas habilidades):**
   Esqueça código complexo. Para ensinar o Jarvis a abrir seu projeto favorito, crie um arquivo como `devtools.yaml` na pasta `plugins`:

   ```yaml
   commands:
     - intent: "abrir_projeto_frontend"
       description: "Inicia o servidor e abre o VS Code"
       risk_level: "safe"
       actions:
         - type: "system_open"
           target: "${WARP_PATH}"
         - type: "wait"
           duration: 1.0
         - type: "type_and_enter"
           text: "cd ${PROJECT_PATH}"
         - type: "wait"
           duration: 0.5
         - type: "type_and_enter"
           text: "npm run dev"
   ```
   *Salve o arquivo e o Jarvis aprenderá na hora!*

## 🚀 Inicialização Automática (Autostart Invisível)

Quer que o Jarvis acorde junto com você? Clique com o botão direito no ícone dele na bandeja do Windows e ative o **Autostart**. Ele fará tudo sozinho e iniciará oculto em segundo plano, consumindo pouquíssima memória.

## 🏛️ Arquitetura e Documentação

O Jarvis foi desenhado com arquitetura modular desacoplada em domínios de responsabilidade bem delimitados. Para entender seu funcionamento interno e subsistemas:

- 🧠 **[Visão Consolidada & Grafo de Funcionamento](./docs/architecture/jarvis_architecture_and_flow.md)**: Diagramas completos do ciclo de vida, máquina de estados finitos (`JarvisState`) e fluxo de ponta a ponta.
- 📚 **[Central de Documentação (docs/README.md)](./docs/README.md)**: Índice completo navegável com deep-dives de subsistemas (Roteamento de Comandos, UI PySide6, Cache SQLite) e diretrizes técnicas.

## 🗺️ Para onde vamos?

O Jarvis é um projeto vivo e construído para escalar. 

Quer saber o que vem por aí ou o que já fizemos? Dá uma olhada no **[ROADMAP.md](./ROADMAP.md)** (Plano de voo) e no **[TODO.md](./TODO.md)** (Nossas tarefas técnicas).

---
*Desenvolvido para facilitar a rotina de quem busca produtividade máxima.*
