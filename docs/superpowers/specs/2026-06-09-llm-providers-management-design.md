# Design Spec: LLM Providers Management and Error Handling Speech

## Context & Objectives
Jarvis currently supports Gemini, OpenAI, and Anthropic as LLM providers. Changing providers requires modifying `config.yaml` manually. If an LLM call fails due to exhausted credits (HTTP 429) or authentication issues, Jarvis logs the error to the console but remains silent, which degrades the user experience.

This specification outlines the addition of **DeepSeek** and **OpenRouter** providers, the implementation of a **System Tray** submenu to switch active providers at runtime with active validation (using a 1-token background test call), and introducing **spoken voice feedback** for LLM rate limit and authentication errors.

---

## Requirements

### 1. New Providers
* Integrate **DeepSeek** (`deepseek/deepseek-chat`) and **OpenRouter** (fully configurable model, e.g., `openrouter/google/gemini-2.5-flash` or `openrouter/meta-llama/llama-3-8b-instruct:free`) into `LiteLLMProvider`.
* Dynamically retrieve/verify `DEEPSEEK_API_KEY` and `OPENROUTER_API_KEY` from the system Keyring or `.env`.

### 2. Runtime Provider Switching (System Tray)
* Add an **"LLM Provider"** submenu to the PySide6 system tray menu.
* List all five providers (*Gemini*, *OpenAI*, *Anthropic*, *DeepSeek*, *OpenRouter*) as checkable options.
* On provider selection:
  1. Validate if the respective API key exists in Keyring or `.env`.
  2. Spawn a background thread to run a minimal test call (1-token completion) to ensure the API key is valid and active.
  3. If missing or invalid, show a tray warning message and revert the selection.
  4. If present and valid, update `config["llm"]["active_provider"]` in memory, update `config.yaml` persistently (without wiping comments), and dynamically rebuild the `llm_agent`'s provider instance under a concurrency lock.

### 3. Concurrency Protection
* Protect the `self.provider` instance access in `LLMAgent` with a `threading.Lock` to avoid race conditions when switching providers while a voice command is active.

### 4. Thread-Safe UI Updates (Qt Signals)
* To prevent cross-thread UI violations (Qt UI access from non-main threads), define a Qt custom Signal `provider_switch_done = Signal(bool, str)`. When the background validation thread completes, it emits this signal. A slot connected in the main thread handles UI visual state synchronization and alerts.

### 5. Error Voice Feedback & Bypass
* Intercept `LLMRateLimitError` and `LLMAuthenticationError` in the `command_worker` queue loop.
* First check structured properties (e.g. `status_code == 429`), falling back to string matching (e.g. `quota`, `credit`, `balance`) to identify quota exhaustion.
* Speak friendly error messages instead of failing silently:
  * **Quota/Credits (429):** *"Desculpe, estou sem cota ou créditos no provedor de IA no momento."*
  * **Auth/Key Missing:** *"Chave de API inválida ou não configurada."*
  * **General Failures:** *"Desculpe, ocorreu um erro de conexão com o provedor de IA."*
* Bypasses retries for permanent errors (like invalid authentication or exhausted quota).

---

## Detailed Design

### 1. Configuration & Capability Mapping

#### `config.yaml`
Add default configurations:
```yaml
llm:
  active_provider: "gemini"
  providers:
    gemini:
      model: "gemini-2.5-flash"
    openai:
      model: "gpt-4.1-mini"
    anthropic:
      model: "claude-3-5-haiku-latest"
    deepseek:
      model: "deepseek-chat"
    openrouter:
      model: "google/gemini-2.5-flash" # Fully configurable model name
```

#### `core/infra/keyring_manager.py`
Add capacities for `deepseek` and `openrouter`:
```python
capabilities = {
    "gemini": ["json_mode", "system_instructions"],
    "openai": ["json_mode", "system_instructions", "tool_use"],
    "anthropic": ["system_instructions", "tool_use"],
    "deepseek": ["json_mode", "system_instructions"],
    "openrouter": ["json_mode", "system_instructions"],
}
```

---

### 2. Active Validation & Concurrency Protection

#### Concurrency Lock in `core/ai/llm_agent.py`
Add a lock and reinit method:
```python
import threading

class LLMAgent:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._init_provider()

    def _init_provider(self) -> None:
        llm_config = config.get("llm", {})
        active_provider = llm_config.get("active_provider", "gemini")
        model_name = (
            llm_config.get("providers", {})
            .get(active_provider, {})
            .get("model", "gemini-2.0-flash")
        )
        self.provider = LiteLLMProvider(provider=active_provider, model=model_name)

    def reinit_provider(self) -> None:
        """Reinitializes the LLM provider instance dynamically when settings change."""
        with self._lock:
            self._init_provider()

    def process_instruction(self, text: str, context_commands: list[Any] | None = None) -> dict[str, Any]:
        # ... validation and prep ...
        with self._lock:
            # Wrap the actual LLM call
            response = self.provider.generate_content(prompt=prompt)
        # ... parse and return ...
```

#### Connection Testing in `core/llm/litellm_provider.py`
We will add a helper to test the provider connectivity using a 1-token request:
```python
    def test_connection(self) -> bool:
        """Verifies if the API key and provider connection are valid using a 1-token request."""
        messages = [{"role": "user", "content": "ping"}]
        try:
            litellm.completion(
                model=self.full_model_name,
                messages=messages,
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.error(f"Active connection test failed for {self.provider}: {e}")
            return False
```

---

### 3. System Tray & Thread-Safe Signal Integration
Modifications in `core/ui/app_controller.py`:

* **Signal Definition:**
  Define the Qt Signal on `QtAppController`:
  ```python
  provider_switch_done = Signal(bool, str) # (success_status, provider_name)
  ```
  In `__init__`, connect the signal:
  ```python
  self.provider_switch_done.connect(self._on_provider_switch_done)
  ```

* **Active Validation Initiator (`_switch_provider`):**
  Validate key presence using `KeyringManager.validate_provider_key(provider)`.
  If present, run the test call in a background thread to prevent UI freezing:
  ```python
  def _switch_provider(self, provider: str) -> None:
      # Pre-check existence
      if not KeyringManager.validate_provider_key(provider):
          self.tray_icon.showMessage("Jarvis", f"API Key for {provider} not configured.", QSystemTrayIcon.MessageIcon.Warning, 3000)
          self._update_menu_states()
          return
          
      # Run 1-token completion test in background
      def run_test():
          # Temporary provider instance to test connection
          llm_config = config.get("llm", {})
          model_name = llm_config.get("providers", {}).get(provider, {}).get("model", "")
          test_provider = LiteLLMProvider(provider=provider, model=model_name)
          
          success = test_provider.test_connection()
          self.provider_switch_done.emit(success, provider)

      threading.Thread(target=run_test, daemon=True).start()
  ```

* **Slot Callback on Main Thread (`_on_provider_switch_done`):**
  This handles the safe UI visual transitions and file writes:
  ```python
  def _on_provider_switch_done(self, success: bool, provider: str) -> None:
      if success:
          config["llm"]["active_provider"] = provider
          update_yaml_active_provider(provider)
          llm_agent.reinit_provider()
          self.tray_icon.showMessage("Jarvis", f"IA alterada para {provider}.", QSystemTrayIcon.MessageIcon.Information, 3000)
      else:
          self.tray_icon.showMessage("Jarvis", f"Falha na conexão ou chave inválida para {provider}.", QSystemTrayIcon.MessageIcon.Warning, 3000)
      
      self._update_menu_states()
  ```

---

## 4. Voice Feedback & Structured Error Handling
In `core/execution/worker.py`, modify the `except TechnicalError` block:

```python
except TechnicalError as te:
    cause = te.__cause__
    is_auth_error = isinstance(cause, LLMAuthenticationError)
    is_rate_limit = isinstance(cause, LLMRateLimitError)
    
    # Check structured status code (429) before falling back to string checks
    status_code = getattr(cause, "status_code", None)
    is_quota_exhausted = (status_code == 429)
    
    if not is_quota_exhausted and is_rate_limit:
        err_msg = str(cause).lower()
        if any(k in err_msg for k in ["quota", "credit", "balance", "exhausted", "limit"]):
            is_quota_exhausted = True

    # Check for permanent API errors to speak and stop immediately
    if is_auth_error or is_quota_exhausted:
        job.status = JobStatus.FAILED
        job.finished_at = time.time()
        job.error = str(te)
        
        if is_auth_error:
            dispatcher.automator.speak("Chave de API inválida ou não configurada.")
        else:
            dispatcher.automator.speak("Desculpe, estou sem cota ou créditos no provedor de IA no momento.")
        break

    # Standard retry loop for transient technical errors
    job.retries += 1
    logger.error(
        f"Technical error in job {job.id} (Attempt {job.retries}): {te}"
    )
    if job.retries < job.max_retries:
        job.status = JobStatus.RETRYING
        backoff = 2**job.retries
        time.sleep(backoff)
    else:
        job.status = JobStatus.FAILED
        job.finished_at = time.time()
        job.error = str(te)
        
        # Speak fallback on final failure
        if is_rate_limit:
            dispatcher.automator.speak("Desculpe, estou sem cota ou créditos no provedor de IA no momento.")
        else:
            dispatcher.automator.speak("Desculpe, ocorreu um erro de conexão com o provedor de IA.")
```

---

## Testing Plan

### 1. Manual Testing
* **New Providers:** Set mock `DEEPSEEK_API_KEY` and run a query to confirm V3/R1 completion formats.
* **Tray Switching:**
  * Try switching to a provider with no API key (e.g. OpenRouter). Verify tray warning is shown and checkmark reverts.
  * Try switching to a provider with an invalid key (e.g. key is "invalid-key"). Confirm the background thread 1-token test fails, tray displays connection error, and checkmark reverts.
  * Try switching to a provider with a valid key. Verify `config.yaml` is updated correctly (retains comments) and the next voice command uses the new provider.
* **Error Voice Feedback:**
  * Simulate API failure with `litellm.exceptions.RateLimitError` or `AuthenticationError`. Verify Jarvis speaks the correct phrase and does not run redundant retries.
* **Concurrency Switching Test:**
  * Trigger a long voice query (or mock a slow LLM call) and click to switch providers in the tray menu *during* the call. Verify that `threading.Lock` protects the active execution from race conditions, ensuring the active command finishes executing with the original provider and the new provider becomes active for the subsequent command.
