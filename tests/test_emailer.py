"""tests/test_emailer.py — Unit tests for hackradar.emailer.

smtplib.SMTP is mocked so no real email is sent. We inspect the MIME
message captured by mock_smtp.sendmail to verify HTML content.
"""

from __future__ import annotations

import re
import smtplib
from datetime import datetime
from email import message_from_string
from unittest.mock import MagicMock, patch, call

import pytest

from hackradar.models import Item, ScoredItem
from hackradar import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    title: str = "Test Tech",
    source: str = "meta_blog",
    github_url: str | None = "https://github.com/example/repo",
    huggingface_url: str | None = "https://huggingface.co/example/model",
    paper_url: str | None = "https://arxiv.org/abs/0000.00000",
    demo_url: str | None = "https://demo.example.com",
    stars: int | None = 1200,
    downloads: int | None = 45000,
    model_size: str | None = "7.0B params",
    license: str | None = "MIT",
) -> Item:
    item = Item(
        title=title,
        description="An impressive new open-source model.",
        date=datetime(2026, 3, 27),
        source=source,
        source_url=f"https://example.com/{title.replace(' ', '-').lower()}",
        category="ai_research",
        github_url=github_url,
        huggingface_url=huggingface_url,
        paper_url=paper_url,
        demo_url=demo_url,
    )
    item.stars = stars
    item.downloads = downloads
    item.model_size = model_size
    item.license = license
    return item


def _make_scored_item(
    title: str = "Test Tech",
    total_score: float = 9.0,
    open_score: float = 9.0,
    novelty_score: float = 9.0,
    wow_score: float = 9.0,
    build_score: float = 9.0,
    include_idea: bool = True,
    **item_kwargs,
) -> ScoredItem:
    item = _make_item(title=title, **item_kwargs)
    return ScoredItem(
        item=item,
        open_score=open_score,
        novelty_score=novelty_score,
        wow_score=wow_score,
        build_score=build_score,
        total_score=total_score,
        summary="A groundbreaking cross-disciplinary model that lets you predict brain activity from images.",
        hackathon_idea="Build an interactive 3D brain visualization app" if include_idea else None,
        tech_stack="React Three Fiber, Python, HuggingFace" if include_idea else None,
        why_now="Released yesterday — zero products built on it yet" if include_idea else None,
        effort_estimate="2 days prep + 24h hackathon" if include_idea else None,
    )


def _capture_html(mock_smtp_instance: MagicMock) -> str:
    """Extract the HTML part from the raw MIME message passed to sendmail.

    emailer.py calls sendmail with keyword args (from_addr=..., to_addrs=...,
    msg=...), so we read from call_args.kwargs rather than positional args.
    """
    assert mock_smtp_instance.sendmail.called, "sendmail was never called"
    call_args = mock_smtp_instance.sendmail.call_args
    # Prefer kwargs, fall back to positional if present
    if call_args.kwargs and "msg" in call_args.kwargs:
        raw_msg = call_args.kwargs["msg"]
    elif call_args.args:
        raw_msg = call_args.args[2]
    else:
        raise AssertionError(f"Cannot find msg in sendmail call: {call_args}")

    parsed = message_from_string(raw_msg)
    html_part = None
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/html":
                html_part = part.get_payload(decode=True).decode("utf-8")
                break
    else:
        if parsed.get_content_type() == "text/html":
            html_part = parsed.get_payload(decode=True).decode("utf-8")
    assert html_part is not None, "No text/html part found in MIME message"
    return html_part


# ---------------------------------------------------------------------------
# Shared SMTP mock context manager factory
# ---------------------------------------------------------------------------

def _mock_smtp():
    """Return a context-manager-compatible Mock for smtplib.SMTP."""
    mock_instance = MagicMock()
    mock_class = MagicMock()
    mock_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
    mock_class.return_value.__exit__ = MagicMock(return_value=False)
    return mock_class, mock_instance


# ---------------------------------------------------------------------------
# Test 1: 15 scored items → valid HTML with all expected fields
# ---------------------------------------------------------------------------

def test_15_items_produce_valid_html_with_all_fields():
    """send_email with 15 items must produce HTML containing titles, scores, links."""
    scored_items = [
        _make_scored_item(title=f"Project {i}", total_score=9.0 - i * 0.1)
        for i in range(15)
    ]

    mock_class, mock_instance = _mock_smtp()

    with patch("smtplib.SMTP", mock_class), \
         patch.object(config, "EMAIL_ADDRESS", "from@example.com"), \
         patch.object(config, "EMAIL_PASSWORD", "secret"), \
         patch.object(config, "EMAIL_TO", "to@example.com"), \
         patch.object(config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(config, "SMTP_PORT", 587):
        from hackradar.emailer import send_email
        send_email(scored_items, failed_sources=[])

    html = _capture_html(mock_instance)

    # All 15 titles should appear
    for i in range(15):
        assert f"Project {i}" in html, f"Missing 'Project {i}' in HTML"

    # Score badges should appear
    assert "badge-open" in html
    assert "badge-novel" in html
    assert "badge-wow" in html
    assert "badge-build" in html

    # Link pills should appear (at least some)
    assert "link-pill" in html
    assert "Paper" in html
    assert "Code" in html
    assert "Model" in html
    assert "Demo" in html

    # HackRadar header
    assert "HackRadar" in html

    # Hackathon idea block
    assert "Hackathon Idea" in html
    assert "3D brain visualization" in html

    # SMTP calls
    mock_instance.ehlo.assert_called()
    mock_instance.starttls.assert_called()
    mock_instance.login.assert_called_once_with("from@example.com", "secret")
    mock_instance.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: item with no hackathon_idea (score < 6.5) renders without crash
# ---------------------------------------------------------------------------

def test_item_without_hackathon_idea_renders_cleanly():
    """A low-score ScoredItem with hackathon_idea=None must not cause a render error."""
    low_score_item = _make_scored_item(
        title="Boring Increment",
        total_score=5.0,
        open_score=4.0,
        novelty_score=5.0,
        wow_score=5.0,
        build_score=6.0,
        include_idea=False,
    )

    mock_class, mock_instance = _mock_smtp()

    with patch("smtplib.SMTP", mock_class), \
         patch.object(config, "EMAIL_ADDRESS", "from@example.com"), \
         patch.object(config, "EMAIL_PASSWORD", "secret"), \
         patch.object(config, "EMAIL_TO", "to@example.com"), \
         patch.object(config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(config, "SMTP_PORT", 587):
        from hackradar.emailer import send_email
        send_email([low_score_item], failed_sources=[])  # must not raise

    html = _capture_html(mock_instance)
    assert "Boring Increment" in html
    # The idea block should NOT appear for this item
    assert "3D brain" not in html


# ---------------------------------------------------------------------------
# Test 3: empty items list → send_email doesn't crash
# ---------------------------------------------------------------------------

def test_empty_items_list_does_not_crash():
    """Passing an empty list to send_email should not raise any exception."""
    mock_class, mock_instance = _mock_smtp()

    with patch("smtplib.SMTP", mock_class), \
         patch.object(config, "EMAIL_ADDRESS", "from@example.com"), \
         patch.object(config, "EMAIL_PASSWORD", "secret"), \
         patch.object(config, "EMAIL_TO", "to@example.com"), \
         patch.object(config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(config, "SMTP_PORT", 587):
        from hackradar.emailer import send_email
        send_email([], failed_sources=[])  # must not raise

    html = _capture_html(mock_instance)
    # Subject line count should say "0 high-signal finds"
    # The Subject may be MIME-encoded (=?utf-8?b?...?=) — decode it first.
    call_args = mock_instance.sendmail.call_args
    raw_msg = call_args.kwargs.get("msg") or call_args.args[2]
    parsed = message_from_string(raw_msg)
    from email.header import decode_header, make_header
    subject = str(make_header(decode_header(parsed["Subject"])))
    assert "0 high-signal finds" in subject


# ---------------------------------------------------------------------------
# Test 4: failed sources list appears in email footer
# ---------------------------------------------------------------------------

def test_failed_sources_appear_in_footer():
    """Failed source names must appear in the HTML email footer."""
    scored_item = _make_scored_item(title="One Good Item")
    failed = ["meta_blog", "arxiv", "hacker_news"]

    mock_class, mock_instance = _mock_smtp()

    with patch("smtplib.SMTP", mock_class), \
         patch.object(config, "EMAIL_ADDRESS", "from@example.com"), \
         patch.object(config, "EMAIL_PASSWORD", "secret"), \
         patch.object(config, "EMAIL_TO", "to@example.com"), \
         patch.object(config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(config, "SMTP_PORT", 587):
        from hackradar.emailer import send_email
        send_email([scored_item], failed_sources=failed)

    html = _capture_html(mock_instance)

    # Footer section with CSS class "failed" should exist
    assert "failed" in html
    for source in failed:
        assert source in html, f"Failed source '{source}' not found in email HTML"


# ---------------------------------------------------------------------------
# Test 5: SMTP auth failure → exception propagates to caller
# ---------------------------------------------------------------------------

def test_smtp_auth_failure_propagates_exception():
    """An SMTPAuthenticationError must not be swallowed — it must propagate."""
    scored_item = _make_scored_item(title="Any Item")

    mock_class, mock_instance = _mock_smtp()
    mock_instance.login.side_effect = smtplib.SMTPAuthenticationError(
        535, b"Authentication failed"
    )

    with patch("smtplib.SMTP", mock_class), \
         patch.object(config, "EMAIL_ADDRESS", "from@example.com"), \
         patch.object(config, "EMAIL_PASSWORD", "wrong-password"), \
         patch.object(config, "EMAIL_TO", "to@example.com"), \
         patch.object(config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(config, "SMTP_PORT", 587):
        from hackradar.emailer import send_email
        with pytest.raises(smtplib.SMTPAuthenticationError):
            send_email([scored_item], failed_sources=[])
