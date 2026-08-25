import contextlib

from database import get_db_connection

VALID_PROVIDERS = ("anthropic", "openai", "gemini")


def get_active_provider() -> str:
    """Reads the platform's active LLM provider. Defaults to 'anthropic' if the
    settings row is somehow missing (should not happen once database.py has run)."""
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT active_llm_provider FROM platform_settings WHERE id = 1;")
            row = cursor.fetchone()
    return row[0] if row else "anthropic"


def set_active_provider(provider: str) -> None:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Must be one of {VALID_PROVIDERS}.")

    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE platform_settings SET active_llm_provider = %s, updated_at = now() WHERE id = 1;",
                (provider,),
            )
        conn.commit()
