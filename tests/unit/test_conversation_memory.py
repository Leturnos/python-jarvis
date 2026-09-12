from core.ai.conversation_memory import ConversationMemory


def test_conversation_memory_empty():
    mem = ConversationMemory(max_turns=3)
    assert mem.get_context_prompt() == "Nenhuma conversa anterior recente."
    assert mem.get_last_turn() is None


def test_conversation_memory_record_and_get():
    mem = ConversationMemory(max_turns=3)
    mem.record_turn(
        "vai chover hoje?", "Provavelmente sim, o tempo está fechando.", "weather"
    )

    last = mem.get_last_turn()
    assert last is not None
    assert last.user_query == "vai chover hoje?"
    assert last.assistant_response == "Provavelmente sim, o tempo está fechando."
    assert last.intent == "weather"

    prompt = mem.get_context_prompt()
    assert 'Usuário: "vai chover hoje?"' in prompt
    assert 'Jarvis: "Provavelmente sim, o tempo está fechando."' in prompt


def test_conversation_memory_max_turns_eviction():
    mem = ConversationMemory(max_turns=2)
    mem.record_turn("q1", "r1")
    mem.record_turn("q2", "r2")
    mem.record_turn("q3", "r3")

    prompt = mem.get_context_prompt()
    assert "q1" not in prompt
    assert "q2" in prompt
    assert "q3" in prompt
    assert len(mem) == 2


def test_conversation_memory_clear():
    mem = ConversationMemory(max_turns=5)
    mem.record_turn("ola", "ola senhor")
    mem.clear()
    assert mem.get_context_prompt() == "Nenhuma conversa anterior recente."
    assert mem.get_last_turn() is None


def test_conversation_memory_ignore_empty():
    mem = ConversationMemory(max_turns=5)
    mem.record_turn("", "resposta")
    mem.record_turn("pergunta", "")
    mem.record_turn("   ", "   ")
    assert len(mem) == 0


def test_conversation_memory_ttl_expiration():
    mem = ConversationMemory(max_turns=5)
    mem.record_turn("antigo", "resposta antiga")
    # artificially age the turn
    mem._history[0].timestamp -= 3600.0
    mem.record_turn("recente", "resposta recente")

    prompt = mem.get_context_prompt(ttl_seconds=1800.0)
    assert "antigo" not in prompt
    assert "recente" in prompt
