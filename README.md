# 🎙️ Python Jarvis

Um assistente virtual leve e eficiente para Windows, focado em automatizar suas tarefas do dia a dia. Com ele, você prepara seu ambiente de trabalho ou roda scripts apenas usando a voz ou o teclado.

Chega de clicar dezenas de vezes para começar a trabalhar. Diga "Hey Jarvis", peça o que precisa, e ele faz por você.

## ✨ O que ele faz?

- **Ativação Inteligente (Novo! 🎙️):** Você escolhe como o Jarvis deve te ouvir. Ele pode ficar sempre atento à frase "Hey Jarvis", funcionar apenas quando você aperta uma tecla (Push-to-Talk), ou ambos!
- **Controle de Mídia Inteligente (Spotify 🎵 - Novo!):** Diga ao Jarvis para tocar um artista, música ou playlist. Ele trará o Spotify para o primeiro plano e usará inteligência visual (OpenCV) para localizar e clicar nos botões corretos na tela, iniciando a música instantaneamente. Veja o [Guia de Configuração de Mídia](./data/media/README.md) para aprender a cadastrar suas playlists favoritas.
- **Modo Gamer e Reunião (Auto-Suspend):** O Jarvis é educado. Se ele perceber que você está jogando ou em uma apresentação (tela cheia), ele entra em suspensão automaticamente para não te interromper.
- **Entende seu jeito de falar (IA):** Não precisa decorar comandos rígidos. Após ativar o assistente, fale de forma natural e ele usará IA (Google Gemini) para entender sua intenção.
- **Paleta de Comandos (⌨️):** Falar alto nem sempre é o ideal. Aperte `Ctrl + Alt + P` a qualquer momento para abrir uma barra de pesquisa rápida na tela e execute suas automações silenciosamente.
- **Aprende Novas Habilidades (Plugins YAML):** Ensinar algo novo para o Jarvis é tão fácil quanto escrever uma receita de bolo em um arquivo de texto.
- **Invisível e Seguro:** Roda silenciosamente na bandeja do Windows (System Tray) e possui um sistema de segurança que bloqueia ou pede confirmação antes de executar ações perigosas.
- **Controle de Descanso:** Você pode dizer "Jarvis, ir dormir" e ele descarregará os modelos pesados da memória para economizar energia do seu PC, ficando em modo de espera até que você o acorde manualmente.

### 🧠 Comandos de Sistema
Exemplos de como usar as novas capacidades de memória e controle:
- **Descansar/Silenciar**: "Jarvis, ir dormir", "Silenciar", "Parar de ouvir".
- **Repetir último comando**: "Faz de novo", "De novo".
- **Salvar como macro**: "Salvar como macro", "Gravar sequência", "Salve isso".

## 📋 Pré-requisitos

1. **Sistema Operacional:** Windows 10 ou 11.
2. **Terminal (Opcional):** Suporte nativo para o [Warp](https://www.warp.dev/), mas funciona com qualquer aplicação.
3. **Microfone:** Qualquer microfone padrão conectado ao PC.

## 🛠️ Como Instalar e Usar

O projeto utiliza o gerenciador de pacotes rápido `uv`.

1. **Instale o projeto:**
   ```bash
   uv sync
   ```

2. **Dê vida ao assistente:**
   ```bash
   uv run main.py
   ```

O Jarvis vai aparecer na sua bandeja do Windows (perto do relógio) e estará pronto para ouvir você!

## ⚙️ Configurando o Jarvis

Nós separamos as coisas para facilitar sua vida. Existem três arquivos principais que você precisa conhecer:

1. **Arquivo `.env` (Suas Chaves e Caminhos Locais):**
   Faça uma cópia do arquivo `.env.example` e renomeie para `.env`.
   Coloque aqui a chave de API da IA do provedor ativo escolhido (ex: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY` ou `OPENROUTER_API_KEY`) e os caminhos dos seus programas locais.

2. **Arquivo `config.yaml` (Ajustes de Motor):**
   Aqui você mexe na "mecânica" do Jarvis.
   - **Ativação de Voz (`voice_activation`):**
     - `mode`: Escolha entre `hybrid` (Frase + Tecla), `push_to_talk` (Apenas tecla), `always_listening` (Apenas frase) ou `disabled`.
     - `push_to_talk`: Configure a tecla (ex: `ctrl+alt`) e se quer segurar para falar (`hold`) ou apenas um toque (`toggle`).
     - `auto_suspend`: Ative o `fullscreen: true` para o Jarvis silenciar automaticamente em jogos ou vídeos em tela cheia.
   - **Cérebro do Jarvis (`llm`):** Você pode escolher qual IA o Jarvis usa! No campo `active_provider`, você pode colocar `gemini`, `openai`, `anthropic`, `deepseek` ou `openrouter`. 
     - *Segurança e Migração Automatizada:* Coloque a chave correspondente ao provedor configurado no seu `.env` ao iniciar o Jarvis pela primeira vez. Ele detectará a chave do provedor ativo, fará a migração automática para o Keyring seguro do Windows (Gerenciador de Credenciais) e você poderá remover a chave do arquivo `.env` por segurança.
   - **Voz do Jarvis (`tts`):** Quer que o Jarvis tenha uma voz diferente? No campo `voice_keyword`, coloque parte do nome da voz que você tem instalada no Windows (ex: "maria", "zira", "david"). Se ele não encontrar a que você pediu, ele tentará usar uma voz em Português automaticamente.

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

## 🗺️ Para onde vamos?

O Jarvis é um projeto vivo e construído para escalar. 

Quer saber o que vem por aí ou o que já fizemos? Dá uma olhada no **[ROADMAP.md](./ROADMAP.md)** (Plano de voo) e no **[TODO.md](./TODO.md)** (Nossas tarefas técnicas).

---
*Desenvolvido para facilitar a rotina de quem busca produtividade máxima.*
