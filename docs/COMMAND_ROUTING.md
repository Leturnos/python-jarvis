# Roteamento Inteligente de Comandos (Arquitetura)

O Jarvis utiliza um pipeline de processamento em múltiplas etapas para garantir que os comandos sejam executados da forma mais rápida e precisa possível, priorizando o processamento local antes de recorrer à nuvem.

## Fluxo de Execução

Ao detectar a palavra de ativação principal (**"Hey Jarvis"**), o sistema segue este fluxo:

1.  **Ativação e Resposta:** O Jarvis responde "Sim?" e inicia a gravação ativa do áudio.
2.  **Transcrição (STT):** O áudio é convertido em texto localmente usando o modelo **Whisper (OpenAI)**.
3.  **Normalização:** O texto transcrito é limpo (letras minúsculas, remoção de pontuação e espaços convertidos em `_`).

### O Pipeline de Decisão (Command Worker)

O texto normalizado passa por três camadas de decisão:

#### Camada 1: Match Exato (Local/Instantâneo)
O Jarvis verifica se a frase dita corresponde exatamente a uma chave configurada no `config.yaml` sob a seção `wakewords`.
*   *Exemplo:* Falar "Fechar tudo" -> Match com a chave `fechar_tudo`.

#### Camada 2: Match Difuso / Fuzzy (Local/Rápido)
Se não houver match exato, utiliza-se a biblioteca `difflib` para encontrar o comando mais próximo estatisticamente no `config.yaml`.
*   *Exemplo:* Falar "Fechar tuda" ou "Fecha tudo" -> Match com `fechar_tudo` (limiar de ~70%).

#### Camada 3: Inteligência Artificial (Nuvem/Flexível)
Se nenhuma correspondência local for encontrada, a frase original é enviada ao **Google Gemini**. O Gemini recebe a lista de comandos disponíveis como contexto e decide:
*   **Ação:** Se o usuário pediu algo que pode ser mapeado para um comando novo ou existente (retorna JSON de ação).
*   **Chat:** Se o usuário fez uma pergunta ou saudação (retorna JSON de chat para ser falado via TTS).

## Vantagens
- **Velocidade:** Comandos comuns são detectados localmente em milissegundos.
- **Robustez:** O sistema entende variações da fala sem necessidade de re-treinamento.
- **Versatilidade:** Permite tanto automação de sistema quanto conversa natural.
