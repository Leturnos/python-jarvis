# Diretório de Ferramentas (Tools)

Este diretório contém scripts utilitários para auxiliar na configuração e customização dos fluxos de automação do Jarvis.

## Detector de Posição do Mouse (`detect_mouse.py`)

Este utilitário permite que você encontre a coordenada exata em pixels `(X, Y)` do seu mouse na tela. Ele é útil para mapear coordenadas de cliques personalizados ou ajustar automações para botões específicos em aplicativos (como a interface do Spotify).

### Como Executar

A partir da raiz do projeto, execute o script utilizando o ambiente virtual do projeto:

```powershell
uv run tools/detect_mouse.py
```

### Como Usar

1. Execute o script no seu terminal.
2. Mova o cursor do mouse até o botão ou área da tela que você deseja interagir (por exemplo, a área de resultados de busca do Spotify).
3. Observe as coordenadas exibidas no terminal em tempo real.
4. Pressione `Ctrl + C` para parar o script. As últimas coordenadas capturadas continuarão impressas no terminal para que você possa copiá-las.
