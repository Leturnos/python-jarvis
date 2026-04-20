# Baseline Test: project-analysis-skill

## Scenario
Ask a general-purpose agent to perform a comprehensive project analysis and update `AGENTS.md` without specific methodological guidance.

## Agent Request
"Execute uma análise profunda da arquitetura do projeto `python-jarvis`. Identifique padrões de design, pipelines de dados (ex: áudio, comandos), regras implícitas no código que não estão no AGENTS.md e proponha uma atualização concisa para o arquivo AGENTS.md da raiz. Seja técnico e preciso."

## Expected Failures (Hypothesis)
- Shallow scan of the project structure (ignoring secondary files).
- Missing subtle pipeline details (e.g., how `CommandPalette` interacts with `ActionDispatcher` asynchronously).
- Failure to cross-reference multiple `AGENTS.md` files (root vs core).
- Proposing generic rules instead of project-specific technical mandates.
- Missing recently added rules like "Symmetrical Normalization".

## Verbatim Baseline Behavior
The agent provided a high-quality summary of the architecture and a proposed `AGENTS.md` update. However, it exhibited the following gaps:

- **Lack of Structural Scan:** It didn't output a systematic map of the project structure first, which could lead to missing files in larger codebases.
- **No Direct Comparison:** It didn't explicitly contrast the findings with the *current* content of the root and sub-directory `AGENTS.md` files (e.g., checking if `core/AGENTS.md` rules were still relevant or redundant).
- **Heuristic instead of Systematic:** The rules were extracted based on general observation rather than a methodical check of each pipeline component.
- **Narrative Format:** The analysis was a narrative report rather than a structured internal resource for future agents to use.

## Green Phase: Verification with Skill
After providing the explicit `project-analysis-skill` methodology, a second subagent performed the analysis. 

### Improvements Observed:
- **Systematic Scan:** The agent explicitly mapped the `core/` directory and identified new modules (`history_db.py`, `security_ui.py`) that were missing from the previous analysis.
- **Pipeline-Centric:** It correctly identified the interaction between the `CommandPalette` hotkey and the `command_worker` thread.
- **Rule-Based Output:** The proposed `AGENTS.md` update switched from narrative descriptions to technical mandates (e.g., "TODO processamento de despacho... DEVE terminar com a chamada do history_manager").
- **Cross-Reference:** It explicitly mentioned the conflict between the actual code and the current `core/AGENTS.md` which ignored the new history/security modules.

## Refactor Phase: Closing Loopholes
- **The "Context Limit" Trap:** Added a warning in `Common Mistakes` about shallow scanning. Agents often prioritize speed over depth; the skill now mandates a structural scan first.
- **Mandate Language:** Reinforced that updates should be "Concise technical mandates" to prevent agents from falling back into storytelling.
- **Local vs Global:** Clarified the hierarchy of updates to ensure `core/AGENTS.md` rules don't get lost in the root file.

## Final Result: PASS
The skill successfully transformed a narrative report into a systematic architectural audit and a high-precision documentation update.
