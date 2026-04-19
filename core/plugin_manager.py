import os
import yaml
import glob
from core.logger_config import logger
from core.config import config

class PluginManager:
    def __init__(self, plugins_dir="plugins"):
        self.plugins_dir = plugins_dir
        self.intents = {}  # Map of intent_name -> { description, risk_level, actions, phrases, plugin_name }
        self.load_plugins()

    def _expand_vars(self, data):
        """Recursively expand environment variables in a dictionary or list."""
        if isinstance(data, dict):
            return {k: self._expand_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_vars(i) for i in data]
        elif isinstance(data, str):
            return os.path.expandvars(data)
        else:
            return data

    def _resolve_actions(self, actions, shared_actions, plugin_name):
        """Resolves 'include' actions by replacing them with shared actions."""
        resolved = []
        for action in actions:
            if action.get("type") == "include":
                ref_name = action.get("name")
                if ref_name in shared_actions:
                    resolved.extend(shared_actions[ref_name])
                else:
                    logger.error(f"Plugin '{plugin_name}': Shared action '{ref_name}' not found.")
            else:
                resolved.append(action)
        return resolved

    def load_plugins(self):
        """Loads all YAML/JSON plugin files from the plugins directory."""
        if not os.path.exists(self.plugins_dir):
            logger.warning(f"Plugins directory '{self.plugins_dir}' not found. Creating it.")
            os.makedirs(self.plugins_dir, exist_ok=True)
            return

        plugin_files = glob.glob(os.path.join(self.plugins_dir, "*.yaml")) + \
                       glob.glob(os.path.join(self.plugins_dir, "*.yml")) + \
                       glob.glob(os.path.join(self.plugins_dir, "*.json"))

        for file_path in plugin_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    plugin_data = yaml.safe_load(f)
                    
                if not plugin_data or "commands" not in plugin_data:
                    logger.warning(f"Invalid or empty plugin file: {file_path}")
                    continue

                plugin_name = plugin_data.get("name", os.path.basename(file_path))
                raw_shared_actions = plugin_data.get("shared_actions", {})
                shared_actions = self._expand_vars(raw_shared_actions)
                commands = self._expand_vars(plugin_data["commands"])

                for cmd in commands:
                    intent = cmd.get("intent")
                    if not intent:
                        logger.warning(f"Command without intent found in {plugin_name}")
                        continue
                    
                    if intent in self.intents:
                        logger.warning(f"Intent '{intent}' is being overwritten by plugin '{plugin_name}'")

                    resolved_actions = self._resolve_actions(cmd.get("actions", []), shared_actions, plugin_name)

                    self.intents[intent] = {
                        "description": cmd.get("description", ""),
                        "risk_level": cmd.get("risk_level", "safe"),
                        "phrases": cmd.get("phrases", []),
                        "actions": resolved_actions,
                        "plugin_name": plugin_name
                    }
                logger.info(f"Loaded plugin '{plugin_name}' with {len(commands)} intents.")
                
            except Exception as e:
                logger.error(f"Failed to load plugin {file_path}: {e}")

        logger.info(f"PluginManager initialization complete. Loaded {len(self.intents)} intents total.")

    def get_intents(self):
        """Returns a list of all loaded intent names, descriptions and phrases."""
        return [{"intent": k, "description": v["description"], "phrases": v.get("phrases", []), "risk_level": v["risk_level"]} 
                for k, v in self.intents.items()]

    def get_actions_for_intent(self, intent_name):
        """Returns the list of actions for a specific intent."""
        if intent_name in self.intents:
            return self.intents[intent_name]["actions"]
        return None

# Singleton instance
plugin_manager = PluginManager()
