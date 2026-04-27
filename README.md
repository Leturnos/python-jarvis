# 🎙️ Python Jarvis

Um assistente virtual leve e eficiente para Windows, focado em automatizar suas tarefas do dia a dia. Com ele, você prepara seu ambiente de trabalho ou roda scripts apenas usando a voz ou o teclado.

Chega de clicar dezenas de vezes para começar a trabalhar. Diga "Hey Jarvis", peça o que precisa, e ele faz por você.

## ✨ O que ele faz?

- **Ouve de verdade (Offline):** Fica sempre a postos esperando você dizer "Hey Jarvis" de forma rápida e sem depender de internet para a ativação inicial.
- **Entende seu jeito de falar (IA):** Não precisa decorar comandos rígidos. Após ativar o assistente, fale de forma natural e ele usará IA (Google Gemini) para entender sua intenção.
- **Paleta de Comandos (Novo! ⌨️):** Falar alto nem sempre é o ideal. Aperte `Ctrl + Alt + P` a qualquer momento para abrir uma barra de pesquisa rápida na tela e execute suas automações silenciosamente.
- **Aprende Novas Habilidades (Plugins YAML):** Ensinar algo novo para o Jarvis é tão fácil quanto escrever uma receita de bolo em um arquivo de texto.
- **Invisível e Seguro:** Roda silenciosamente na bandeja do Windows (System Tray) e possui um sistema de segurança que bloqueia ou pede confirmação antes de executar ações perigosas.
- **Memória de Curto e Longo Prazo:** Repita rapidamente a última ação ou peça para o Jarvis salvar uma sequência de comandos como uma nova macro (plugin) inteligente.

### 🧠 Comandos de Sistema
Exemplos de como usar as novas capacidades de memória:
- **Repetir último comando**: "Repetir último comando", "Faz de novo", "De novo". (Executa a última ação de sucesso).
- **Salvar como macro**: "Salvar como macro", "Gravar sequência", "Salve isso". (Consolida as últimas ações em um novo plugin usando IA).

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
   Aqui você coloca sua chave de IA (`GEMINI_API_KEY`) e onde estão instalados seus programas.

2. **Arquivo `config.yaml` (Ajustes de Motor):**
   Aqui você mexe na "mecânica" do Jarvis.
   - `threshold`: Quão sensível é o ouvido dele (padrão `0.35`).
   - `volume_multiplier`: Se o seu microfone for baixo, aumente esse número.
   - `cooldown_seconds`: Quanto tempo o Jarvis "descansa" após executar um comando.

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
