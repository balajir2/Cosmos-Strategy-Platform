import html
import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "Cosmos Strategic Capability Platform <onboarding@cosmos-strategy.example>"


def send_invite_email(to_email: str, full_name: str, setup_link: str) -> bool:
    """Sends the client-invite email via Resend. Returns True if the email
    was actually sent, False if RESEND_API_KEY isn't configured (local dev/
    CI - the caller falls back to returning setup_link directly, mirroring
    this codebase's existing graceful-degradation philosophy for LLM
    providers and audio transcription) or if the Resend API call itself
    failed for any reason. Never raises past this boundary."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print(f"RESEND_API_KEY is not set. Skipping invite email to {to_email}.")
        return False

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": FROM_ADDRESS,
                "to": [to_email],
                "subject": "You've been invited to Cosmos Strategic Capability Platform",
                "html": (
                    f"<p>Hi {html.escape(full_name)},</p>"
                    f"<p>Your Cosmos consultant has set up an engagement for you. "
                    f'<a href="{setup_link}">Click here to set your password and get started</a>.</p>'
                    f"<p>This link expires in 7 days.</p>"
                ),
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending invite email via Resend to {to_email}: {e}")
        return False
