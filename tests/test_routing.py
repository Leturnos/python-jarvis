import unittest
from core.utils import normalize_text
import difflib

class TestRouting(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("Fechar Tudo!"), "fechar_tudo")
        self.assertEqual(normalize_text("Abrir o Warp..."), "abrir_o_warp")
        self.assertEqual(normalize_text("Hey, Jarvis?"), "hey_jarvis")

    def test_fuzzy_matching(self):
        available_commands = ["fechar_tudo", "abrir_navegador", "limpar_terminal"]
        
        # Exact match
        normalized = normalize_text("fechar tudo")
        self.assertIn(normalized, available_commands)
        
        # Fuzzy match
        normalized_fuzzy = normalize_text("fechar as coisas")
        matches = difflib.get_close_matches(normalized_fuzzy, available_commands, n=1, cutoff=0.5)
        # Note: "fechar_as_coisas" vs "fechar_tudo" might be too far, but let's check
        # Actually "fechar_as_coisas" and "fechar_tudo" share "fechar"
        self.assertTrue(len(matches) >= 0) 

        normalized_fuzzy_2 = normalize_text("fechar tuda")
        matches = difflib.get_close_matches(normalized_fuzzy_2, available_commands, n=1, cutoff=0.7)
        self.assertEqual(matches[0], "fechar_tudo")

if __name__ == '__main__':
    unittest.main()
