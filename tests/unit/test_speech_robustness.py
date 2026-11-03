from unittest.mock import MagicMock, patch

import pytest

from core.audio.stt_engine import DEFAULT_SPEECH_KEYWORDS, STTEngine
from core.shared.utils import post_process_stt_text


class TestSpeechRobustnessHomophones:
    """Tests phonetic homophone corrections for Brazilian Portuguese accents and developer jargon."""

    @pytest.mark.parametrize(
        ("raw_input", "expected_output"),
        [
            ("marca um taimer de dez minutos", "marca um timer de dez minutos"),
            ("iniciar taymer agora", "iniciar timer agora"),
            ("ativar o pomodóro", "ativar o pomodoro"),
            ("o que tem no clipe borde?", "o que tem no clipboard?"),
            ("ver o clipbord", "ver o clipboard"),
            ("copiar para o clip board", "copiar para o clipboard"),
            ("abrir o obsidiam hoje", "abrir o Obsidian hoje"),
            ("abrir obsidien", "abrir Obsidian"),
            ("tocar lofi no youtubi", "tocar lofi no YouTube"),
            ("pesquisar musica no iuque", "pesquisar musica no YouTube"),
            ("abrir video no utube", "abrir video no YouTube"),
            ("ver o status do guite", "ver o status do git"),
            ("abrir o guithãbi", "abrir o GitHub"),
            ("entrar no guihabi", "entrar no GitHub"),
            ("criar um pê-érre novo", "criar um pull request novo"),
            ("abrir o pe erre", "abrir o pull request"),
            ("revisar o pull requéste", "revisar o pull request"),
            ("subir o container no dóquer", "subir o container no docker"),
            ("iniciar servidor nóde djéss", "iniciar servidor Node.js"),
            ("rodar na porta no localhoste", "rodar na porta no localhost"),
            (
                "verificar se tem algo em local roste",
                "verificar se tem algo em localhost",
            ),
        ],
    )
    def test_homophone_replacements_match_expected(
        self, raw_input: str, expected_output: str
    ) -> None:
        result = post_process_stt_text(raw_input)
        assert result == expected_output

    @pytest.mark.parametrize(
        ("spoken_port_text", "expected_normalized"),
        [
            ("matar processo na porta três mil", "matar processo na porta 3000"),
            ("liberar porta 3 mil", "liberar porta 3000"),
            ("ver quem usa a porta quatro mil", "ver quem usa a porta 4000"),
            ("derrubar porta 4 mil", "derrubar porta 4000"),
            ("serviço na porta cinco mil", "serviço na porta 5000"),
            ("fechar porta oito mil", "fechar porta 8000"),
            (
                "qual app roda na porta oito mil e oitenta?",
                "qual app roda na porta 8080?",
            ),
            ("porta oito zero oito zero travada", "porta 8080 travada"),
            ("encerrar porta nove mil", "encerrar porta 9000"),
            ("liberar porta 3.000 urgente", "liberar porta 3000 urgente"),
            ("porta 8.000 ocupada", "porta 8000 ocupada"),
        ],
    )
    def test_spoken_network_port_normalization(
        self, spoken_port_text: str, expected_normalized: str
    ) -> None:
        result = post_process_stt_text(spoken_port_text)
        assert result == expected_normalized

    def test_legacy_homophones_remain_supported(self) -> None:
        assert post_process_stt_text("abrir vies code") == "abrir VS Code"
        assert post_process_stt_text("tocar espotifai") == "tocar Spotify"
        assert post_process_stt_text("iniciar warpe") == "iniciar Warp"
        assert post_process_stt_text("jarvis ir dormir") == "Jarvis, ir dormir"


class TestContextualInitialPrompt:
    """Tests the contextual initial prompt assembly for Faster-Whisper."""

    def test_default_speech_keywords_contains_essential_tools(self) -> None:
        assert "timer" in DEFAULT_SPEECH_KEYWORDS
        assert "pomodoro" in DEFAULT_SPEECH_KEYWORDS
        assert "YouTube" in DEFAULT_SPEECH_KEYWORDS
        assert "GitHub" in DEFAULT_SPEECH_KEYWORDS
        assert "clipboard" in DEFAULT_SPEECH_KEYWORDS
        assert "Obsidian" in DEFAULT_SPEECH_KEYWORDS
        assert "Spotify" in DEFAULT_SPEECH_KEYWORDS
        assert "porta" in DEFAULT_SPEECH_KEYWORDS
        assert "Docker" in DEFAULT_SPEECH_KEYWORDS

    def test_build_contextual_prompt_respects_max_chars(self) -> None:
        engine = STTEngine(
            config_dict={"stt": {"max_prompt_chars": 60, "lazy_load": True}}
        )
        prompt = engine.build_contextual_prompt()
        assert len(prompt) <= 60
        assert "Jarvis" in prompt

    def test_build_contextual_prompt_with_extra_keywords(self) -> None:
        engine = STTEngine(
            config_dict={"stt": {"max_prompt_chars": 200, "lazy_load": True}}
        )
        extra = ["sim", "confirma", "executa"]
        prompt = engine.build_contextual_prompt(extra_keywords=extra)
        assert "sim" in prompt
        assert "confirma" in prompt
        assert "Jarvis" in prompt

    def test_transcribe_uses_contextual_prompt_when_none_provided(self) -> None:
        engine = STTEngine(config_dict={"stt": {"lazy_load": True}})
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "teste de transcricao"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        engine.model = mock_model

        fake_audio = b"\x00" * 3200
        result = engine.transcribe(fake_audio)

        assert result == "teste de transcricao"
        mock_model.transcribe.assert_called_once()
        _, kwargs = mock_model.transcribe.call_args
        assert "initial_prompt" in kwargs
        assert "Jarvis" in kwargs["initial_prompt"]


class TestLLMAgentSpeechRobustnessPrompt:
    """Tests that the LLMAgent system prompt incorporates speech robustness and anti-hallucination guidelines."""

    @patch("core.ai.llm_agent.history_manager.log_metric")
    @patch("core.ai.llm_agent.rate_limiter.check_quotas", return_value=True)
    @patch("core.ai.llm_agent.llm_cache.get", return_value=None)
    @patch("core.ai.llm_agent.LLMAgent._execute_with_fallback")
    def test_system_prompt_includes_phonetic_tolerance_and_hallucination_guard(
        self,
        mock_fallback: MagicMock,
        mock_cache_get: MagicMock,
        mock_quota: MagicMock,
        mock_log_metric: MagicMock,
    ) -> None:
        from core.ai.llm_agent import llm_agent

        mock_response = MagicMock()
        mock_response.content = '{"type": "chat", "message": "Como posso ajudar?"}'
        mock_response.usage = {"total_tokens": 10}
        mock_fallback.return_value = mock_response

        llm_agent.process_instruction("abrir o vies code")

        mock_fallback.assert_called_once()
        prompt_sent = mock_fallback.call_args[1]["prompt"]

        assert "Tolerância a Fala e STT" in prompt_sent
        assert "Anti-Alucinação e Discernimento" in prompt_sent
        assert "grafias fonéticas aportuguesadas" in prompt_sent
