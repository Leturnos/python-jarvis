from core.ai.sentence_buffer import SentenceStreamBuffer


def test_sentence_buffer_splits_streaming_sentences_incrementally():
    buf = SentenceStreamBuffer()

    assert buf.push("Sim, é bem provável") == []
    assert buf.push(" que chova hoje em Itamonte.") == []
    assert buf.push(" Há 59% de chance") == [
        "Sim, é bem provável que chova hoje em Itamonte."
    ]
    assert buf.push(" de garoa leve! ") == ["Há 59% de chance de garoa leve!"]
    assert buf.push("Precisa de guarda-chuva?") == []
    assert buf.flush() == ["Precisa de guarda-chuva?"]
    assert buf.flush() == []


def test_sentence_buffer_preserves_decimals_and_numbers():
    buf = SentenceStreamBuffer()
    text = "A precipitação esperada é de 0.4 milímetros e o dólar está em 5.80 reais. "
    emitted = buf.push(text)
    assert emitted == [
        "A precipitação esperada é de 0.4 milímetros e o dólar está em 5.80 reais."
    ]


def test_sentence_buffer_preserves_abbreviations_initials_and_list_markers():
    buf = SentenceStreamBuffer()
    assert buf.push("Dr. Silva chegou às 10h. ") == ["Dr. Silva chegou às 10h."]

    buf2 = SentenceStreamBuffer()
    assert buf2.push("1. Primeiro passo concluído. ") == [
        "1. Primeiro passo concluído."
    ]

    buf3 = SentenceStreamBuffer()
    assert buf3.push("Sr. Stark, tudo pronto! ") == ["Sr. Stark, tudo pronto!"]


def test_sentence_buffer_handles_char_by_char_and_newlines():
    buf = SentenceStreamBuffer()
    streamed = "Primeira linha.\nSegunda frase? Terceira"
    collected: list[str] = []
    for ch in streamed:
        collected.extend(buf.push(ch))
    collected.extend(buf.flush())

    assert collected == ["Primeira linha.", "Segunda frase?", "Terceira"]
