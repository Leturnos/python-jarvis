# Design Specification: Spotify Semantic Refinement

## 1. Objective
Refine the Spotify media integration to ensure emotional or abstract queries ("moods") never trigger a fragile Spotify Search fallback. Implement a local NLP engine for fuzzy matching, a scoring system for intent resolution, guaranteed fallback playlists, and session context tracking.

## 2. Architecture Updates

### 2.1 Media Models (`core.media.models`)
Expand the existing models to handle classification and session context.
*   **QueryType (Enum):** `MOOD`, `ENTITY`, `MIXED`
*   **MediaIntent (Update):**
    ```python
    @dataclass
    class MediaIntent:
        action: MediaAction
        query: Optional[str] = None
        query_type: Optional[QueryType] = None
        provider_hint: Optional[str] = None
    ```
*   **LastMediaContext (New):**
    ```python
    @dataclass
    class LastMediaContext:
        provider: str
        resolved_strategy: str
        playlist_key: Optional[str] = None
        raw_query: Optional[str] = None
    ```
*   **MediaSessionState (Update):**
    ```python
    @dataclass
    class MediaSessionState:
        active_provider: Optional[str] = None
        last_context: Optional[LastMediaContext] = None
    ```

### 2.2 Local NLP Engine (`core.media.nlp`)
A lightweight, deterministic text processor.
*   **Stopword Removal:** Strips common words (e.g., "toca", "musica", "algo", "quero").
*   **Scoring System:** Iterates through remaining tokens and compares them against `INTENT_KEYWORDS`. Adds `0.4` to the score of a playlist for each token match (exact or prefix).
*   **Threshold:** A score `>= 0.4` is considered a confident match.

### 2.3 Curated Playlists Format (`data/media/playlists.json`)
Restructured to separate the URIs from the keywords and include a fallback.
```json
{
  "intents": {
    "happy_hits": "spotify:playlist:37i9dQZF1DXdPec7aLTmlC",
    "focus": "spotify:playlist:37i9dQZF1DWZeKzbUnE3Yv",
    "fallback_playlist": "spotify:playlist:37i9dQZF1E36uuQzQ"
  },
  "keywords": {
    "happy_hits": ["alegre", "feliz", "animad", "festa", "pra cima"],
    "focus": ["focar", "concentrar", "estudar", "trabalhar", "foco"]
  }
}
```

### 2.4 SpotifyProvider (`core.media.providers.spotify`)
The resolution logic is heavily refined:
1. Receives `MediaIntent`.
2. If `action == PLAY_QUERY`:
   - If `query_type == ENTITY`: Bypasses NLP, returns search fallback (`AutoplayStrategy.TAB_ENTER`).
   - If `query_type in [MOOD, MIXED]`: Passes the query to the NLP engine.
     - If `score >= 0.4`: Returns the matched playlist URI (`AutoplayStrategy.MEDIA_KEY`).
     - If `score < 0.4`: Returns the `fallback_playlist` URI (`AutoplayStrategy.MEDIA_KEY`). NUNCA faz search.

### 2.5 LLM Prompt (`core.ai.llm_agent`)
Update the prompt to instruct the LLM to output `"query_type": "mood" | "entity" | "mixed"` alongside the `"query"` for media intents.

## 3. Data Flow Example
- **Input:** "toca um rock bem animado"
- **LLM:** `{"type": "media", "action": "PLAY_QUERY", "query": "um rock bem animado", "query_type": "mixed"}`
- **NLP:** Removes "um", "bem". Tokens: `["rock", "animado"]`.
- **Scoring:** "animado" matches `happy_hits` (+0.4). Best score is `happy_hits` (0.4).
- **Result:** Resolves to the `happy_hits` URI.
