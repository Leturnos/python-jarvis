import json
import os
from google import genai
from core.logger_config import logger
from core.config import config

class LLMAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"
        
    def process_instruction(self, text):
        prompt = f"""
        Você é o Jarvis, um assistente de terminal no Windows.
        O usuário falou: "{text}"
        O usuário está controlando um computador por voz.
        Se a transcrição estiver estranha, tente inferir a intenção mais provável.
        Retorne um JSON estrito contendo a ação a ser executada.
        O formato deve ser OBRIGATORIAMENTE este:
        {{
            "action": "warp" ou "system",
            "commands": ["comando 1", "comando 2"],
            "warp_path": "caminho/para/warp.exe" (apenas se action for warp)
        }}
        Se a ação for de terminal (Warp), use comandos bash/powershell adequados (ex: npm start, cd path).
        Se a ação for de sistema, use comandos válidos de Windows CMD.
        Retorne APENAS o JSON, sem crases markdown (```json).
        """
        
        try:
            logger.info("Sending to Gemini...")
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            result = response.text.strip()
            
            # Clean up markdown if Gemini ignores instructions
            if result.startswith("```json"):
                result = result[7:-3].strip()
            elif result.startswith("```"):
                result = result[3:-3].strip()
                
            json_data = json.loads(result)
            logger.info(f"LLM Response: {json_data}")
            return json_data
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None

llm_agent = LLMAgent()
