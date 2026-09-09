from unittest.mock import MagicMock, patch

import email_provider


@patch("email_provider.requests.post")
def test_send_invite_email_skips_when_no_api_key(mock_post, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    result = email_provider.send_invite_email("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=abc")

    assert result is False
    mock_post.assert_not_called()


@patch("email_provider.requests.post")
def test_send_invite_email_posts_to_resend_when_configured(mock_post, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)

    result = email_provider.send_invite_email("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=abc")

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["json"]["to"] == ["client@customer.com"]
    assert "http://localhost:3000/accept-invite?token=abc" in call_kwargs["json"]["html"]


@patch("email_provider.requests.post", side_effect=RuntimeError("network blip"))
def test_send_invite_email_returns_false_on_request_failure(mock_post, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")

    result = email_provider.send_invite_email("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=abc")

    assert result is False
