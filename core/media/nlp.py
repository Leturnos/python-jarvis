import json
import re


class NLPProcessor:
    STOPWORDS = {
        "quero",
        "ouvir",
        "tocar",
        "toca",
        "coloca",
        "uma",
        "um",
        "musica",
        "algo",
        "bem",
        "muito",
        "pra",
        "para",
        "de",
        "e",
    }

    def __init__(self, dict_path: str):
        self.keywords: dict[str, list[str]] = {}
        self._load_dict(dict_path)

    def _load_dict(self, path: str):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self.keywords = data.get("keywords", {})
        except Exception:
            pass

    def _clean_tokens(self, query: str) -> list[str]:
        words = re.findall(r"\b\w+\b", query.lower())
        return [w for w in words if w not in self.STOPWORDS]

    def score_query(self, query: str) -> tuple[str | None, float]:
        tokens = self._clean_tokens(query)
        if not tokens:
            return None, 0.0

        best_match = None
        best_score = 0.0

        for intent_name, kws in self.keywords.items():
            current_score = 0.0
            for token in tokens:
                for kw in kws:
                    if token.startswith(kw) or kw.startswith(token):
                        current_score += 0.4
                        break  # count max once per token per intent

            if current_score > best_score:
                best_score = current_score
                best_match = intent_name

        if best_score >= 0.4:
            return best_match, best_score

        return None, best_score
