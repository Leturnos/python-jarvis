import json
import google.generativeai as genai
from core.logger_config import logger
from core.config import config

class LLMAgent:
    def __init__(self):
        api_key = config.get("gemini_api_key", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set.")
        genai.configure(api_key=api_key)
        # Using gemini-2.5-flash as it's the fast standard now
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        
    def process_instruction(self, text):
        prompt = f"""
        Você é o Jarvis, um assistente de terminal no Windows.
        O usuário falou: "{text}"
        Retorne um JSON estrito contendo a ação a ser executada.
        O formato deve ser OBRIGATORIAMENTE este:
        {{
            "action_type": "warp" ou "system",
            "commands": ["comando 1", "comando 2"],
            "warp_path": "C:\\Users\\Leandro\\AppData\\Local\\Programs\\Warp\\Warp.exe" (apenas se action_type for warp)
        }}
        Se a ação for de terminal (Warp), use comandos bash/powershell adequados (ex: npm start, cd path).
        Se a ação for de sistema, use comandos válidos de Windows CMD.
        Retorne APENAS o JSON, sem crases markdown (```json).
        """
        
        try:
            logger.info("Sending to Gemini...")
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            # Clean up markdown if Gemini ignores instructions
            if result.startswith("```json"):
                result = result[7:-3].strip()
            if result.startswith("```"):
                result = result[3:-3].strip()
                
            json_data = json.loads(result)
            logger.info(f"LLM Response: {json_data}")
            return json_data
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None

llm_agent = LLMAgent()