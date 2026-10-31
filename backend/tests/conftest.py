"""Use synthetic settings in tests, never application dotenv files."""
from app.core.config import Settings, get_settings

# This executes before collecting modules that initialize settings at import time.
Settings.model_config["env_file"] = None
get_settings.cache_clear()
