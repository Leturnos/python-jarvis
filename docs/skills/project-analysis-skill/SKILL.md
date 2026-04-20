---
name: project-analysis-skill
description: Use when starting work in a new repository, identifying outdated agent instructions, or ensuring project-wide architectural consistency.
---

# Project Analysis Skill

## Overview
A systematic methodology to synchronize the technical reality of a codebase with documented AI agent instructions. This ensures that agents operate under correct architectural assumptions and maintain project-specific engineering standards.

## When to Use
- **Onboarding:** First time entering a project or a complex sub-module.
- **Rule Drift:** When observed code patterns contradict existing `AGENTS.md` or `README.md` files.
- **Architectural Cleanup:** After major refactoring where pipelines or interfaces have changed.
- **Pre-Implementation:** Before starting a multi-step feature to identify relevant constraints.

## Core Methodology

### 1. Structure Scan
Map the physical layout. Identify entry points, core logic directories, and documentation locations.
- **Tools:** `list_directory`, `glob` (look for `*.py`, `*.ts`, `AGENTS.md`, `README.md`).

### 2. Pipeline Identification
Identify data flow and state management. Look for:
- **Inputs:** How data enters (API, CLI, Voice, GUI).
- **Processing:** Chain of responsibility, middlewares, dispatchers.
- **Outputs:** Database writes, file edits, system commands.
- **Concurrency:** Threading models, async loops, event emitters.

### 3. Rule Extraction
Find implicit mandates in the code. Look for:
- **Constants & Enums:** Permitted values.
- **Error Handling:** Standardized `try-except` patterns.
- **Library Preferences:** Which tools are reused (e.g., `uv`, `rich`, `pydantic`).
- **Naming Conventions:** Class/function casing and verb styles.

### 4. Doc Comparison
Contrast findings with existing documents (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`).
- **Missing:** New patterns not documented.
- **Conflicting:** Documents describing deprecated behavior.
- **Redundant:** Rules that are now enforced by types or linters.

### 5. Concise Update
Propose or apply surgical updates to documentation.
- **Format:** Focus on technical mandates over narrative descriptions.
- **Hierarchy:** Update local `AGENTS.md` for specific modules; root for global rules.

## Quick Reference: Pipeline Patterns

| Pattern | Evidence to Look For | Relevant Rule Example |
| :--- | :--- | :--- |
| **Command Chain** | Nested if/else, list of intent handlers. | "New intents must be added to `dispatcher.py` AND `plugins/`." |
| **Safe Execution** | `subprocess.run(check=True)`, risk-level checks. | "Always use `risk_level: dangerous` for file deletion." |
| **State Sync** | Event events, shared queues, global Singletons. | "Always use `CoInitialize()` in COM threads." |
| **Input Normalization** | Regex cleaners, `.lower().strip()` calls. | "Apply `normalize_text` to all voice inputs." |

## Common Mistakes
- **Shallow Scanning:** Only reading `main.py` and ignoring utility helpers.
- **Ignoring Sub-Docs:** Missing rules defined in sub-directory `AGENTS.md` files.
- **Narrative Over Technical:** Writing descriptions ("The code does X") instead of rules ("Agents MUST do X").
