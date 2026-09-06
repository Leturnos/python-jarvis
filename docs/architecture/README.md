# 🏛️ Arquitetura do Jarvis AI

Bem-vindo ao diretório de documentação arquitetural do **Jarvis AI Assistant** (`python-jarvis`).

Este espaço reúne as especificações técnicas vivas, diagramas conceituais e guias de subsistemas do projeto.

---

## 🗺️ Mapa de Documentos

| Documento | Foco & Escopo | Conteúdo Principal |
| :--- | :--- | :--- |
| 🧠 **[Visão Consolidada & Grafo de Funcionamento](./jarvis_architecture_and_flow.md)** | **Documento Mestre (Ponta a Ponta)** | Grafo de fluxo unificado (do microfone ao OS), máquina de estados finitos (`JarvisState`), diagrama de classes por camada e tabela de todos os módulos do core. |
| 🧭 **[Roteamento de Comandos & Intenções](./command-routing.md)** | **Subsistema de IA & Roteamento** | Pipeline em cascata (*local-first*), normalização simétrica, `CommandResolver` (match exato e fuzzy), comandos do sistema (`replay`/`macro`) e fallback de IA na nuvem. |
| 💻 **[Arquitetura de Interface Gráfica (UI)](./ui-architecture.md)** | **Subsistema de Apresentação** | Interface moderna em PySide6 e Fluent Widgets, isolamento de threads, barramento de eventos via Qt Signals e ciclo de vida do `AppController`. |
| ⚡ **[Cache de Respostas LLM](./llm-cache.md)** | **Subsistema de Dados & Otimização** | Mecanismo de cache SQLite com hash SHA-256 e TTL, redução de latência e consumo de tokens, e roadmap para cache semântico vetorial. |

---

## 📐 Diretrizes para Documentação Arquitetural

1. **Documentação Viva:** Qualquer refatoração estrutural que altere fluxos, classes ou contratos entre módulos deve ser refletida nestes documentos.
2. **Uso de Diagramas:** Prefira diagramas **Mermaid** (`flowchart`, `stateDiagram-v2`, `classDiagram`, `sequenceDiagram`) para representar fluxos complexos.
3. **Padrão de Idioma:** Textos conceituais e explicações em Português Brasileiro; identificadores de código, nomes de métodos e termos técnicos mantidos em Inglês.
4. **Planos vs. Arquitetura:** Checklists de tarefas, planos com caixas de seleção (`- [ ]`) e execuções passo a passo devem residir em `docs/superpowers/plans/`, mantendo esta pasta estritamente para a arquitetura de produção do sistema.
