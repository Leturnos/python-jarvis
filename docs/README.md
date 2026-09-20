# 📚 Central de Documentação - Jarvis AI

Bem-vindo ao portal unificado de documentação do **Jarvis AI Assistant** (`python-jarvis`).

Esta central organiza todos os recursos técnicos, guias operacionais, especificações arquiteturais e o histórico de desenvolvimento do assistente em um único ponto de navegação.

---

## 🧭 Navegação Rápida

```
docs/
├── README.md                             <- Você está aqui (Hub Geral)
├── architecture/                         <- Arquitetura viva e subsistemas do sistema
│   ├── README.md                         <- Índice de arquitetura
│   ├── jarvis_architecture_and_flow.md   <- [MESTRE] Visão Consolidada Ponta a Ponta
│   ├── command-routing.md                <- Deep-dive: CommandResolver & Roteamento
│   ├── ui-architecture.md                <- Deep-dive: PySide6, Signals & Fluent Design
│   └── llm-cache.md                      <- Deep-dive: Cache SQLite & Futuro Semântico
├── skills/                               <- Skills e ferramentas de IA do repositório
│   └── project-analysis-skill/           <- Metodologia de auditoria arquitetural
└── superpowers/                          <- Histórico de engenharia assistida por IA
    ├── specs/                            <- Especificações de design técnico (RFCs/Designs)
    └── plans/                            <- Planos de implementação executados
```

---

## 🏛️ 1. Arquitetura e Engenharia

Documentação técnica viva sobre o funcionamento interno do Jarvis:

- 🧠 **[Visão Consolidada e Grafo de Funcionamento](./architecture/jarvis_architecture_and_flow.md)**  
  *Documento mestre de arquitetura.* Contém o grafo ponta a ponta (do áudio ao OS), a máquina de estados global (`JarvisState`), o diagrama de classes das camadas e a tabela detalhada de todos os módulos.
- 🧭 **[Roteamento de Comandos e Resolução de Intenções](./architecture/command-routing.md)**  
  Explica o pipeline escalonado de 3 estágios (`CommandResolver`), a regra de normalização simétrica, match difuso com Levenshtein, comandos especiais de sistema (`replay`, `macro`) e fallback de IA.
- 💻 **[Arquitetura de Interface Gráfica (UI)](./architecture/ui-architecture.md)**  
  Detalhes sobre a implementação em PySide6 e PyQt-Fluent-Widgets, desacoplamento por Qt Signals e controle de ciclo de vida em background.
- ⚡ **[Cache de Respostas LLM](./architecture/llm-cache.md)**  
  Estratégia de persistência SQLite, hash SHA-256 de instruções, TTL e planos de evolução para cache semântico vetorial.
- 📂 **[Índice Completo da Pasta de Arquitetura](./architecture/README.md)**

---

## 📖 2. Guias Práticos e Operação

Documentos para instalação, configuração e uso do assistente:

- 🚀 **[README Principal](../README.md)**: Instalação rápida com `uv`, configuração de microfone, `.env`, `config.yaml`, onboarding gráfico e plugins.
- 📦 **[Empacotamento Executável (`scripts/build_exe.py`)](../scripts/build_exe.py)**: Script automatizado para compilação PyInstaller em One-Folder bundle portátil (`dist/Jarvis/Jarvis.exe`), sem terminal console e com carregamento instantâneo.
- 🎵 **[Guia de Mídia e Automação do Spotify](../data/media/README.md)**: Como cadastrar templates de imagem e configurar playlists personalizadas.
- 🛠️ **[Utilitários e Ferramentas](../tools/README.md)**: Scripts auxiliares (ex: `detect_mouse.py` para mapear coordenadas da tela).

---

## 🧪 3. Qualidade e Testes

- 📋 **[Checklist de Testes Manuais](../tests/manual/MANUAL_TEST_CHECKLIST.md)**: Roteiro passo a passo para validação manual dos recursos no Windows (instância única, system tray, auto-suspend em jogos, paleta de comandos, caixa de confirmação de segurança e macros).
- ⚙️ **Testes Automatizados**: A suíte de testes unitários e de integração pode ser executada via terminal:
  ```powershell
  uv run pytest
  ```

---

## 🤖 4. Diretrizes para Agentes de IA

Regras técnicas e convenções que orientam o desenvolvimento assistido por IA:

- 📋 **[Diretrizes Globais do Projeto (AGENTS.md)](../AGENTS.md)**: Convenções de código, idioma (código em inglês, comunicação em pt-BR), regras de commits e segurança.
- 🧠 **[Diretrizes do Módulo Core (core/AGENTS.md)](../core/AGENTS.md)**: Padrões de arquitetura específicos do diretório `core/`, regras de concorrência Win32 (`CoInitialize`) e isolamento de UI.
- 🎯 **[Project Analysis Skill](./skills/project-analysis-skill/SKILL.md)**: Metodologia padronizada para sincronizar a realidade do código com a documentação.

---

## 📜 5. Histórico e Evolução do Projeto

- 🗺️ **[ROADMAP.md](../ROADMAP.md)**: Direcionamento estratégico de longo prazo do Jarvis (arquitetura, distribuição `.exe`, streaming STT, etc.).
- ✅ **[TODO.md](../TODO.md)**: Checklist detalhado do progresso das fases de desenvolvimento.
- 📁 **[Superpowers Specs](./superpowers/specs/)**: Especificações técnicas formais de cada funcionalidade desenvolvida.
- 📁 **[Superpowers Plans](./superpowers/plans/)**: Planos atômicos de implementação executados ao longo do ciclo de vida do projeto.
