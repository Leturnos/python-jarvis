# Design Specification: Hybrid Media Integration (Spotify Focus)

## 1. Objective
Implement a "Plug and Play" native media control and playback system for Jarvis, with an initial focus on Spotify desktop integration on Windows. The architecture must abstract media operations so the LLM focuses only on semantic intent while the system resolves this into technical execution steps.

## 2. Architecture & Components

### 2.1 Media Models (`core.media.models`)
*   **MediaAction (Enum):** `PLAY`, `PAUSE`, `NEXT`, `PREV`, `PLAY_QUERY`.
*   **AutoplayStrategy (Enum):** 
    *   `MEDIA_KEY`: Sends `VK_MEDIA_PLAY_PAUSE`.
    *   `TAB_ENTER`: Sends `Tab` then `Enter` (useful for search results).
    *   `NONE`: No action after opening URI.
*   **MediaIntent (Dataclass):**
    ```python
    @dataclass
    class MediaIntent:
        action: MediaAction
        query: Optional[str] = None
        provider_hint: Optional[str] = None
    ```
*   **ResolvedMediaPlan (Dataclass):**
    ```python
    @dataclass
    class ResolvedMediaPlan:
        steps: List[ExecutionStep]
        strategy: AutoplayStrategy
    ```

### 2.2 Provider Abstraction (`core.media.providers`)
*   **`MediaProvider` (Interface):** Defines the contract for resolving `MediaIntent`.
*   **`OSMediaController`:** Handles global hardware events (Volume, Play/Pause via system keys).
*   **`SpotifyProvider`:** Implements the resolution of `PLAY_QUERY`.
    *   Consults `data/media/playlists.json`.
    *   Decides the `AutoplayStrategy` based on whether it found a direct URI or a search query.

### 2.3 Semantic Resolver & State
*   **`MediaResolver`:** Transforms `MediaIntent` into a `ResolvedMediaPlan`.
*   **`MediaSessionState`:** Tracks active provider, current track/playlist (if detectable), and session history.

### 2.4 ActionDispatcher
The `ActionDispatcher` will execute the `steps` from the `ResolvedMediaPlan` and then apply the logic dictated by the `AutoplayStrategy`.

## 3. Data Flow
1. **LLM Output:** `{ "type": "media", "action": "PLAY_QUERY", "query": "música alegre" }`.
2. **MediaResolver:** Creates a `MediaIntent` and passes it to the `SpotifyProvider`.
3. **SpotifyProvider:** Returns a `ResolvedMediaPlan` (e.g., steps to open search URI + `strategy=TAB_ENTER`).
4. **Dispatcher:** Executes steps and applies the strategy (e.g., hits Tab and Enter after a wait).
