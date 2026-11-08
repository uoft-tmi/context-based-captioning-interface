"""Use synthetic settings in tests, never application dotenv files."""
from app.core.config import Settings, get_settings

# This executes before collecting modules that initialize settings at import time.
Settings.model_config["env_file"] = None
get_settings.cache_clear()
# General tests exercise the full paid/free product. Demo policy has dedicated tests.
get_settings().DEMO_MODE = False
