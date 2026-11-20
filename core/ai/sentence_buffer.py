"""Incremental sentence splitter for streaming LLM responses to TTS."""

import re

_NON_SPLITTING_ABBREVIATIONS = frozenset(
    {
        "sr.",
        "sra.",
        "dr.",
        "dra.",
        "prof.",
        "profa.",
        "eng.",
        "etc.",
        "ex.",
        "obs.",
        "min.",
        "máx.",
        "max.",
        "aprox.",
        "pág.",
        "pag.",
        "tel.",
        "av.",
        "vs.",
        "mr.",
        "mrs.",
        "ms.",
        "st.",
    }
)

_NUMBERED_LIST_RE = re.compile(r"^\d+\.$")
_SINGLE_INITIAL_RE = re.compile(r"(?:^|\s)[A-Za-zÀ-ÖØ-öø-ÿ]\.$")


class SentenceStreamBuffer:
    """Buffers streaming text deltas and emits complete sentences for low-latency TTS."""

    def __init__(self) -> None:
        self._buffer: str = ""

    @staticmethod
    def _is_false_period_boundary(candidate: str) -> bool:
        """Returns True when a trailing period is an abbreviation, initial, or list index."""
        trimmed = candidate.rstrip()
        if not trimmed.endswith("."):
            return False

        # Protect numbered list markers like "1." or "2."
        if _NUMBERED_LIST_RE.match(trimmed):
            return True

        # Protect single-letter initials like "J." or "A."
        if _SINGLE_INITIAL_RE.search(trimmed):
            return True

        # Protect common abbreviations (case-insensitive)
        last_token = trimmed.split()[-1].lower()
        cleaned_token = last_token.lstrip("(\"'[")
        return cleaned_token in _NON_SPLITTING_ABBREVIATIONS

    def push(self, delta: str) -> list[str]:
        """Appends a text chunk and returns any newly completed sentences."""
        if not delta:
            return []

        self._buffer += delta
        emitted: list[str] = []

        while True:
            split_idx = self._find_next_boundary(self._buffer)
            if split_idx is None:
                break

            sentence = self._buffer[:split_idx].strip()
            self._buffer = self._buffer[split_idx:].lstrip()
            if sentence:
                emitted.append(sentence)

        return emitted

    def flush(self) -> list[str]:
        """Flushes any remaining buffered text as the final sentence."""
        remaining = self._buffer.strip()
        self._buffer = ""
        return [remaining] if remaining else []

    def _find_next_boundary(self, text: str) -> int | None:
        """Finds the end index of the first complete sentence in text, or None."""
        length = len(text)
        i = 0
        while i < length:
            ch = text[i]

            # Newline is always a safe clause/sentence boundary when followed by content
            if ch == "\n":
                candidate = text[:i].strip()
                if candidate:
                    return i + 1
                i += 1
                continue

            if ch in ".!?":
                # Consume repeated punctuation such as "..." or "?!"
                end = i + 1
                while end < length and text[end] in ".!?":
                    end += 1

                # Include optional closing quotes/parentheses right after punctuation
                while end < length and text[end] in "\"')]»”’":
                    end += 1

                # Require trailing whitespace so decimals (0.4), URLs (a.com), or
                # partial tokens at chunk end are never split prematurely.
                if end < length and text[end].isspace():
                    candidate = text[:end]
                    if (
                        ch == "."
                        and end - i == 1
                        and self._is_false_period_boundary(candidate)
                    ):
                        i = end
                        continue
                    return end

                i = end
                continue

            i += 1

        return None
