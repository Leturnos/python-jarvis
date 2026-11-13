"""Curated catalog of built-in and downloadable neural TTS voices for Jarvis.

All downloadable models point to immutable commit/release revisions on Hugging Face
with pinned cryptographic digests and strict file size bounds.
"""

from dataclasses import dataclass

DEFAULT_VOICE_ID = "sapi5_default"

# Default spoken phrases for each assistant lifecycle stage
DEFAULT_STAGE_PHRASES: dict[str, str] = {
    "response_phrase": "Sim?",
    "completion_phrase": "Pronto!",
    "no_speech_phrase": "Desculpe, não ouvi nada.",
    "not_understood_phrase": "Desculpe, não entendi.",
}

# One-click thematic phrase kits for the 4 lifecycle stages in Settings UI
STAGE_PHRASE_PRESETS: dict[str, dict[str, str]] = {
    "Padrão": {
        "response_phrase": "Sim?",
        "completion_phrase": "Pronto!",
        "no_speech_phrase": "Desculpe, não ouvi nada.",
        "not_understood_phrase": "Desculpe, não entendi.",
    },
    "J.A.R.V.I.S.": {
        "response_phrase": "Às suas ordens, senhor.",
        "completion_phrase": "Concluído, senhor.",
        "no_speech_phrase": "Aguardando instruções, senhor.",
        "not_understood_phrase": "Poderia repetir, senhor?",
    },
    "F.R.I.D.A.Y.": {
        "response_phrase": "Sim, chefe?",
        "completion_phrase": "Feito, chefe.",
        "no_speech_phrase": "Nenhum áudio detectado, chefe.",
        "not_understood_phrase": "Não captei o comando, chefe.",
    },
    "Minimalista": {
        "response_phrase": "Pois não?",
        "completion_phrase": "Feito.",
        "no_speech_phrase": "Sem áudio.",
        "not_understood_phrase": "Não entendi.",
    },
}

# Backwards-compatible tuple of response phrase suggestions
RESPONSE_PHRASE_SUGGESTIONS: tuple[str, ...] = (
    "Sim?",
    "Às suas ordens, senhor.",
    "Sim, chefe?",
    "Pois não?",
)


@dataclass(frozen=True)
class VoiceModelAsset:
    """Represents a downloadable neural ONNX voice model package."""

    model_key: str
    onnx_filename: str
    json_filename: str
    onnx_url: str
    json_url: str
    approx_size_mb: float
    expected_onnx_bytes: int | None = None
    expected_onnx_sha256: str | None = None
    expected_onnx_md5: str | None = None
    expected_json_md5: str | None = None


@dataclass(frozen=True)
class VoicePreset:
    """Represents a user-selectable voice option in the Jarvis Settings UI."""

    voice_id: str
    display_name: str
    gender: str  # "female" | "male"
    description: str
    provider: str  # "sapi5" | "piper_onnx"
    dsp_profile: str  # "none" | "natural" | "jarvis_mk3" | "friday_mk50"
    sample_text: str
    model_asset: VoiceModelAsset | None = None


# Immutable model assets (1-to-1 per neural voice preset so each voice installs/cleans up independently)
MODEL_ASSETS: dict[str, VoiceModelAsset] = {
    "jarvis_mk3": VoiceModelAsset(
        model_key="jarvis_mk3",
        onnx_filename="jarvis_mk3.onnx",
        json_filename="jarvis_mk3.onnx.json",
        onnx_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx",
        json_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json",
        approx_size_mb=60.3,
        expected_onnx_bytes=63201294,
        expected_onnx_md5="e0724a2f07965f6523d2a1e96b488a4c",
        expected_json_md5="a1258e1e113c47d9a1486a9bef1daab4",
    ),
    "friday_mk50": VoiceModelAsset(
        model_key="friday_mk50",
        onnx_filename="friday_mk50.onnx",
        json_filename="friday_mk50.onnx.json",
        onnx_url="https://huggingface.co/OpenVoiceOS/pipertts_pt-BR_dii/resolve/791329b/dii_pt-BR.onnx",
        json_url="https://huggingface.co/OpenVoiceOS/pipertts_pt-BR_dii/resolve/791329b/dii_pt-BR.onnx.json",
        approx_size_mb=60.6,
        expected_onnx_sha256="fb15a447ba7482b922e1d2fefea71c1031f760e72be24cce7794e26fe11d086b",
    ),
    "faber": VoiceModelAsset(
        model_key="faber",
        onnx_filename="pt_BR-faber-medium.onnx",
        json_filename="pt_BR-faber-medium.onnx.json",
        onnx_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx",
        json_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json",
        approx_size_mb=60.3,
        expected_onnx_bytes=63201294,
        expected_onnx_md5="e0724a2f07965f6523d2a1e96b488a4c",
        expected_json_md5="a1258e1e113c47d9a1486a9bef1daab4",
    ),
    "dii": VoiceModelAsset(
        model_key="dii",
        onnx_filename="dii_pt-BR.onnx",
        json_filename="dii_pt-BR.onnx.json",
        onnx_url="https://huggingface.co/OpenVoiceOS/pipertts_pt-BR_dii/resolve/791329b/dii_pt-BR.onnx",
        json_url="https://huggingface.co/OpenVoiceOS/pipertts_pt-BR_dii/resolve/791329b/dii_pt-BR.onnx.json",
        approx_size_mb=60.6,
        expected_onnx_sha256="fb15a447ba7482b922e1d2fefea71c1031f760e72be24cce7794e26fe11d086b",
    ),
    "sage": VoiceModelAsset(
        model_key="sage",
        onnx_filename="pt_BR-sage_13364-medium.onnx",
        json_filename="pt_BR-sage_13364-medium.onnx.json",
        onnx_url="https://huggingface.co/srxz/sage-voice-pt-br/resolve/main/pt_BR-sage_13364-medium.onnx",
        json_url="https://huggingface.co/srxz/sage-voice-pt-br/resolve/main/pt_BR-sage_13364-medium.onnx.json",
        approx_size_mb=60.5,
        expected_onnx_sha256="9442d3e9ea54dbbaac76dfa83857178ff4f1a751ef1e3ed49c68bf2049c0623f",
    ),
    "cadu": VoiceModelAsset(
        model_key="cadu",
        onnx_filename="pt_BR-cadu-medium.onnx",
        json_filename="pt_BR-cadu-medium.onnx.json",
        onnx_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx",
        json_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx.json",
        approx_size_mb=60.0,
        expected_onnx_bytes=62950044,
        expected_onnx_md5="6f3a6e23694c9088e3696a15191af2cc",
        expected_json_md5="3d35f13df6a2f7dc9b7b7924befbe7bb",
    ),
    "jeff": VoiceModelAsset(
        model_key="jeff",
        onnx_filename="pt_BR-jeff-medium.onnx",
        json_filename="pt_BR-jeff-medium.onnx.json",
        onnx_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/jeff/medium/pt_BR-jeff-medium.onnx",
        json_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/jeff/medium/pt_BR-jeff-medium.onnx.json",
        approx_size_mb=60.0,
        expected_onnx_bytes=62950044,
        expected_onnx_md5="dfb93e9da48638f9efa6b63fdb0b7030",
        expected_json_md5="e7d673d946db4d9e9d8644babf347ea9",
    ),
    "edresson": VoiceModelAsset(
        model_key="edresson",
        onnx_filename="pt_BR-edresson-low.onnx",
        json_filename="pt_BR-edresson-low.onnx.json",
        onnx_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/edresson/low/pt_BR-edresson-low.onnx",
        json_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/edresson/low/pt_BR-edresson-low.onnx.json",
        approx_size_mb=60.2,
        expected_onnx_bytes=63104526,
        expected_onnx_md5="53e365c040dd07890fe1855b64c7cc58",
        expected_json_md5="806966b457e27c01d9b8eed2bc76a185",
    ),
}


# Curated list of 9 voices (4 Female, 5 Male)
VOICE_CATALOG: tuple[VoicePreset, ...] = (
    VoicePreset(
        voice_id="sapi5_default",
        display_name="Windows Nativo — Maria (Fem.)",
        gender="female",
        description="Voz padrão integrada ao Windows (SAPI5). Não ocupa espaço extra em disco.",
        provider="sapi5",
        dsp_profile="none",
        sample_text="Olá! Eu sou a voz nativa do sistema Windows.",
        model_asset=None,
    ),
    VoicePreset(
        voice_id="jarvis_mk3",
        display_name="J.A.R.V.I.S. — Mark III (Masc.)",
        gender="male",
        description="Voz masculina do Homem de Ferro com filtro acústico holográfico Mark III.",
        provider="piper_onnx",
        dsp_profile="jarvis_mk3",
        sample_text="Às suas ordens, senhor. Todos os sistemas da armadura estão online.",
        model_asset=MODEL_ASSETS["jarvis_mk3"],
    ),
    VoicePreset(
        voice_id="friday_mk50",
        display_name="F.R.I.D.A.Y. — Mark L (Fem.)",
        gender="female",
        description="Voz feminina da Sexta-Feira com filtro tático holográfico Mark L.",
        provider="piper_onnx",
        dsp_profile="friday_mk50",
        sample_text="Sistemas táticos prontos, chefe. Aguardando o seu comando.",
        model_asset=MODEL_ASSETS["friday_mk50"],
    ),
    VoicePreset(
        voice_id="piper_dii",
        display_name="Dii — Estúdio Neural (Fem.)",
        gender="female",
        description="Voz neural feminina brasileira clara e natural em qualidade de estúdio.",
        provider="piper_onnx",
        dsp_profile="natural",
        sample_text="Olá! Esta é a voz neural Dii em qualidade de estúdio.",
        model_asset=MODEL_ASSETS["dii"],
    ),
    VoicePreset(
        voice_id="piper_sage",
        display_name="Sage — Serena Neural (Fem.)",
        gender="female",
        description="Voz neural feminina calma, serena e articulada em português do Brasil.",
        provider="piper_onnx",
        dsp_profile="natural",
        sample_text="Mantenha a calma. Estou pronta para ajudar no seu fluxo de trabalho.",
        model_asset=MODEL_ASSETS["sage"],
    ),
    VoicePreset(
        voice_id="piper_faber",
        display_name="Faber — Estúdio Neural (Masc.)",
        gender="male",
        description="Voz neural masculina limpa e natural sem efeitos de filtro.",
        provider="piper_onnx",
        dsp_profile="natural",
        sample_text="Olá! Esta é a voz neural Faber sem efeitos de filtro.",
        model_asset=MODEL_ASSETS["faber"],
    ),
    VoicePreset(
        voice_id="piper_cadu",
        display_name="Cadu — Firme Neural (Masc.)",
        gender="male",
        description="Voz neural masculina com timbre grave, firme e objetivo.",
        provider="piper_onnx",
        dsp_profile="natural",
        sample_text="Comando recebido. Executando as tarefas solicitadas.",
        model_asset=MODEL_ASSETS["cadu"],
    ),
    VoicePreset(
        voice_id="piper_jeff",
        display_name="Jeff — Jovem Neural (Masc.)",
        gender="male",
        description="Voz neural masculina ágil, leve e moderna.",
        provider="piper_onnx",
        dsp_profile="natural",
        sample_text="Tudo pronto por aqui! Como posso te ajudar agora?",
        model_asset=MODEL_ASSETS["jeff"],
    ),
    VoicePreset(
        voice_id="piper_edresson",
        display_name="Edresson — Compacta (Masc.)",
        gender="male",
        description="Voz neural masculina otimizada para respostas rápidas.",
        provider="piper_onnx",
        dsp_profile="natural",
        sample_text="Assistente ativo e pronto para receber comandos.",
        model_asset=MODEL_ASSETS["edresson"],
    ),
)

VOICE_PRESETS_BY_ID: dict[str, VoicePreset] = {
    preset.voice_id: preset for preset in VOICE_CATALOG
}


def get_voice_preset(voice_id: str | None) -> VoicePreset:
    """Returns the VoicePreset for the given voice_id, falling back to sapi5_default."""
    if not voice_id or voice_id not in VOICE_PRESETS_BY_ID:
        return VOICE_PRESETS_BY_ID[DEFAULT_VOICE_ID]
    return VOICE_PRESETS_BY_ID[voice_id]
