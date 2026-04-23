# Arquitetura do Cache de Respostas LLM

## 1. O Problema
O **Python Jarvis** depende do Gemini (LLM) para interpretar comandos de voz em texto livre e traduzi-los para ações estruturadas (JSON). No entanto, o envio de cada instrução para a API apresenta os seguintes problemas:
- **Latência:** Chamadas de rede e inferência de LLM adicionam um atraso significativo (frequentemente >1s) na execução de comandos simples e repetitivos.
- **Custo e Limites de API:** Comandos muito frequentes ("abrir vscode", "fechar janela") consomem a cota da API desnecessariamente.
- **Dependência de Conexão:** Ações estritamente locais não deveriam falhar apenas por instabilidades momentâneas na internet, caso já sejam conhecidas pelo sistema.

## 2. A Solução: Cache de Respostas (LLM Cache)
Foi implementada uma camada de cache local para armazenar e reutilizar as saídas estruturadas (JSON) do LLM para instruções previamente conhecidas.

### Princípios do Design:
1. **Hash da Instrução:** Em vez de buscar por strings longas e complexas, a instrução em texto natural passa por uma normalização (lowercase, remoção de pontuação extra) e um Hash (SHA-256) é gerado para servir como índice (O(1) na busca).
2. **TTL (Time-To-Live):** Entradas no cache possuem um tempo de expiração configurável. Isso evita que intenções obsoletas (ex: após mudança no comportamento de um plugin) fiquem presas no sistema para sempre.
3. **Cache Seletivo:** O cache aplica-se **apenas a Intenções e Ações técnicas** (ex: `action`). Respostas do tipo `chat` (conversação livre) não são cacheadas, garantindo que o assistente mantenha respostas variadas e naturais no dia a dia.
4. **Estatísticas (Observability):** O sistema contabiliza *hits* e *misses* para medir a efetividade do cache e ajudar em futuras otimizações de performance.
5. **Interface Abstrata (Dependency Inversion):** O sistema de cache não está acoplado a um banco específico no LLMAgent. Ele obedece a uma interface, permitindo a substituição transparente do motor de armazenamento.

## 3. Alternativas Consideradas
- **Dicionário em Memória (Dict Python):** Rápido, mas volátil. Perderia os dados sempre que o assistente fosse reiniciado, não resolvendo o problema a longo prazo.
- **Redis / Memcached:** Soluções robustas, mas exigem a instalação de um servidor de banco de dados em background, o que quebra o princípio de manter o Jarvis leve e portátil para Windows.
- **SQLite (Escolhido):** Nativo no Python, persistente em disco (em um simples arquivo `.db`), suporta concorrência razoável e não exige instalação externa. É a solução ideal para o cenário atual.

## 4. Evolução Futura (Cache Semântico)
A implementação baseada em texto normalizado + Hash resolve o problema de comandos *exatos* ou com pequenas variações de espaço/capitalização. No entanto, ela falha em variações semânticas (ex: "abra o vscode" vs "inicie o vscode").

O próximo passo planejado é a evolução para um **Cache Semântico**:
- **Embeddings Locais:** Utilizar um modelo de embeddings leve (ex: `all-MiniLM-L6-v2` via `sentence-transformers` ou exportado em ONNX) para gerar vetores locais das instruções.
- **Busca por Similaridade (Vector DB):** Substituir a busca por Hash exato por uma busca de similaridade (Cosine Similarity) usando bancos como ChromaDB, FAISS ou a extensão SQLite-VSS.
- Se a similaridade for superior a um limiar (ex: 95%), o cache retorna a resposta imediatamente, cobrindo milhares de variações sintáticas para a mesma ação sem tocar no LLM.