import yaml
import os
import json
from core.logger_config import logger
from core.plugin_manager import plugin_manager
from core.llm_agent import llm_agent
from core.execution_plan import ExecutionPlan, ExecutionStep

class MacroManager:
    def __init__(self, macros_path="plugins/macros.yaml"):
        self.macros_path = macros_path

    def create_macro_from_recent(self, recent_jsons):
        """
        Takes a list of JSON strings representing recent actions and 
        uses LLM to generate a single unified ExecutionPlan with smart naming.
        """
        if not recent_jsons:
            return None

        # Prepare the context for the LLM
        history_summary = []
        for i, js in enumerate(reversed(recent_jsons)):
            try:
                data = json.loads(js)
                intent = data.get("intent", "unknown")
                explanation = data.get("explanation", "")
                history_summary.append(f"Action {i+1}: {intent} - {explanation}")
            except:
                continue

        history_text = "\n".join(history_summary)
        
        prompt = f"""
        Você é o Jarvis. O usuário acabou de executar a seguinte sequência de ações:
        {history_text}
        
        Sua tarefa é criar uma MACRO que consolide essas ações em um único plano de execução.
        1. Escolha um nome de 'intent' curto e inteligente em português (ex: 'deploy_mvp', 'preparar_ambiente').
        2. Escreva uma 'explanation' clara explicando o que essa macro faz.
        3. Consolide todos os 'steps' das ações originais em uma lista única e lógica.
        
        Retorne um JSON estrito no formato ExecutionPlan:
        {{
            "schema_version": "1.0",
            "type": "action",
            "intent": "nome_da_macro",
            "explanation": "Descrição humana",
            "global_risk": "medium",
            "steps": [ ... ]
        }}
        """
        
        try:
            # We bypass the normal process_instruction because we want a specific macro generation
            response = llm_agent.client.models.generate_content(
                model=llm_agent.model_id,
                contents=prompt
            )
            result = response.text.strip()
            
            if result.startswith("```json"):
                result = result[7:-3].strip()
            elif result.startswith("```"):
                result = result[3:-3].strip()
                
            action_json = json.loads(result)
            return ExecutionPlan.from_dict(action_json)
        except Exception as e:
            logger.error(f"Error generating macro with LLM: {e}")
            return None

    def save_macro_as_plugin(self, plan: ExecutionPlan):
        """Converts an ExecutionPlan into a plugin YAML and saves it."""
        try:
            # Convert ExecutionPlan to Plugin-like dictionary
            plugin_data = {
                "intent": plan.intent,
                "description": plan.explanation,
                "phrases": [plan.intent.replace("_", " "), f"executar {plan.intent.replace('_', ' ')}"],
                "risk_level": plan.global_risk.value,
                "actions": []
            }
            
            # Map ExecutionSteps back to legacy Plugin actions for the DSL
            for step in plan.steps:
                action = {"type": step.type.value}
                action.update(step.payload)
                plugin_data["actions"].append(action)

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.macros_path), exist_ok=True)
            
            # Load existing macros
            existing_macros = []
            if os.path.exists(self.macros_path):
                with open(self.macros_path, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    if isinstance(content, list):
                        existing_macros = content
            
            # Append new macro
            existing_macros.append(plugin_data)
            
            with open(self.macros_path, "w", encoding="utf-8") as f:
                yaml.dump(existing_macros, f, allow_unicode=True, sort_keys=False)
            
            logger.info(f"Macro '{plan.intent}' saved to {self.macros_path}")
            
            # Reload plugins
            plugin_manager.load_plugins()
            return True
        except Exception as e:
            logger.error(f"Error saving macro plugin: {e}")
            return False

macro_manager = MacroManager()
