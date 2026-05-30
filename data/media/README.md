# 🎵 Playlists e Intenções de Mídia (Media Intents)

Este arquivo (`playlists.json`) é o cérebro semântico do Jarvis para músicas. Ele garante que quando você pedir uma música baseada em um **humor** ou **atividade**, o Jarvis tocará exatamente a playlist certa, sem depender da busca falha do Spotify.

## 🛠️ Como adicionar suas próprias playlists?

O arquivo é dividido em dois blocos: `intents` (as playlists em si) e `keywords` (as palavras que ativam essa playlist).

### 1. Pegue a URI da sua Playlist no Spotify
1. Abra o Spotify (Desktop ou Web).
2. Vá até a playlist que você quer adicionar.
3. Clique nos **Três pontinhos (...)** > **Compartilhar** (Share).
4. Segure a tecla `Alt` (no Windows) para a opção mudar para **"Copiar URI do Spotify"** (Copy Spotify URI) e clique nela.
   * *A URI vai parecer com algo assim: `spotify:playlist:37i9dQZF1DXdPec7aLTmlC`*

### 2. Adicione a intenção em "intents"
Abra o arquivo `playlists.json` e adicione um "nome de intenção" inventado por você, colando a URI.
```json
"intents": {
  "meu_rock": "spotify:playlist:SuaUriCopiadaAqui",
  // ... outras
}
```

### 3. Adicione as palavras de ativação em "keywords"
Diga ao Jarvis quais palavras devem ativar a sua playlist recém-criada. Você não precisa colocar a palavra inteira (pode colocar só o começo, como `"animad"` que ele entende "animado" e "animada").
```json
"keywords": {
  "meu_rock": ["rock", "metal", "pesado", "guitarra"],
  // ... outras
}
```

## 🚨 Regra de Ouro (Fallback)
Nunca apague a chave `"fallback_playlist"` do bloco de intents. O Jarvis usa ela como um "plano de segurança" para tocar alguma coisa quando você pedir um humor que ele não entendeu ou não tem mapeado. Sugestão: coloque a URI do seu "Daily Mix" ou músicas "Curtidas".
