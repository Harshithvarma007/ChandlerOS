"""Provider registry — the one place that knows which adapter module
backs a given provider name from router_config.json.

Adding a provider: write app/providers/<name>.py satisfying base.py's
contract, add one line here, add it to router_config.json. No other file
changes (Engineering Principle 11).
"""
from providers import gemini, groq

_ADAPTERS = {
    "gemini": gemini,
    "groq": groq,
}


def get_adapter(provider_name: str):
    try:
        return _ADAPTERS[provider_name]
    except KeyError:
        raise ValueError(f"No adapter registered for provider '{provider_name}'. "
                          f"Known providers: {list(_ADAPTERS)}") from None
