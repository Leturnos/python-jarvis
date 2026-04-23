from .base import LLMCacheBase
from .sqlite_cache import SQLiteLLMCache

# Initialize a default global cache instance
llm_cache = SQLiteLLMCache()
