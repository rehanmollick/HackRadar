"""emailer.py — Render and send the HackRadar daily digest email.

Builds a clean, scannable HTML email via Jinja2, then sends it through
SMTP (Gmail by default, but any STARTTLS server works).

The HTML template is defined as a string constant in this file — no
separate template file needed.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment

from hackradar import config
from hackradar.models import ScoredItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 HTML template
# ---------------------------------------------------------------------------

_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HackRadar</title>
<style>
  /* Reset */
  body { margin: 0; padding: 0; background: #0f0f13; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif; color: #e2e8f0; }
  a { color: #7dd3fc; text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* Layout */
  .wrapper { max-width: 680px; margin: 0 auto; padding: 32px 16px; }

  /* Header */
  .header { text-align: center; margin-bottom: 32px; }
  .header-title { font-size: 26px; font-weight: 700; color: #f8fafc; letter-spacing: -0.5px; margin: 0 0 4px; }
  .header-sub { font-size: 13px; color: #64748b; margin: 0; }

  /* Item card */
  .item { background: #1e1e2a; border: 1px solid #2d2d3f; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; }
  .item-rank { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
  .item-title { font-size: 18px; font-weight: 700; color: #f8fafc; margin: 0 0 10px; line-height: 1.3; }
  .item-title a { color: #f8fafc; }
  .item-title a:hover { color: #7dd3fc; text-decoration: none; }

  /* Score row */
  .score-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; align-items: center; }
  .score-total { font-size: 22px; font-weight: 800; color: #f8fafc; margin-right: 4px; }
  .score-label { font-size: 11px; color: #64748b; margin-right: 12px; align-self: flex-end; padding-bottom: 3px; }
  .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .badge-open  { background: #1e3a5f; color: #7dd3fc; }
  .badge-novel { background: #3b1f5e; color: #c084fc; }
  .badge-wow   { background: #1f3a2f; color: #4ade80; }
  .badge-build { background: #3a2a1a; color: #fb923c; }

  /* Sources */
  .sources-line { font-size: 12px; color: #475569; margin-bottom: 12px; }
  .sources-line strong { color: #7dd3fc; }

  /* Summary */
  .summary { font-size: 14px; line-height: 1.6; color: #cbd5e1; margin-bottom: 14px; }

  /* Idea block */
  .idea-block { background: #111827; border-left: 3px solid #7dd3fc; border-radius: 0 8px 8px 0; padding: 12px 16px; margin-bottom: 14px; }
  .idea-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: #7dd3fc; margin-bottom: 6px; }
  .idea-text { font-size: 13px; line-height: 1.55; color: #e2e8f0; }

  /* Meta rows */
  .meta-row { font-size: 12px; color: #64748b; margin-bottom: 6px; }
  .meta-row strong { color: #94a3b8; }

  /* Link pills */
  .link-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .link-pill { display: inline-block; padding: 4px 12px; background: #1a1a2a; border: 1px solid #2d2d3f; border-radius: 6px; font-size: 12px; color: #94a3b8; }
  .link-pill:hover { border-color: #7dd3fc; color: #7dd3fc; }

  /* Divider */
  .divider { border: none; border-top: 1px solid #1e293b; margin: 8px 0 20px; }

  /* Footer */
  .footer { text-align: center; margin-top: 32px; font-size: 12px; color: #334155; }
  .footer .failed { color: #f87171; margin-top: 8px; }

  /* Score colour helpers */
  .score-hi  { color: #4ade80; }
  .score-mid { color: #facc15; }
  .score-lo  { color: #f87171; }
</style>
</head>
<body>
<div class="wrapper">

  <!-- Header -->
  <div class="header">
    <div class="header-title">&#128302; HackRadar</div>
    <div class="header-sub">{{ date }} &nbsp;|&nbsp; {{ count }} high-signal finds</div>
  </div>

  <!-- Items -->
  {% for s in items %}
  <div class="item">
    <div class="item-rank">#{{ loop.index }}</div>
    <div class="item-title">
      {% if s.item.source_url %}
        <a href="{{ s.item.source_url }}">{{ s.item.title }}</a>
      {% else %}
        {{ s.item.title }}
      {% endif %}
    </div>

    <!-- Score row -->
    <div class="score-row">
      <span class="score-total {{ 'score-hi' if s.total_score >= 7.5 else ('score-mid' if s.total_score >= 6.0 else 'score-lo') }}">
        {{ s.total_score | round(1) }}
      </span>
      <span class="score-label">/ 10</span>
      <span class="badge badge-open">Open {{ s.open_score | round | int }}</span>
      <span class="badge badge-novel">Novel {{ s.novelty_score | round | int }}</span>
      <span class="badge badge-wow">Wow {{ s.wow_score | round | int }}</span>
      <span class="badge badge-build">Build {{ s.build_score | round | int }}</span>
    </div>

    <!-- Source count -->
    <div class="sources-line">
      Found on <strong>{{ s.item.source_count }} source{% if s.item.source_count != 1 %}s{% endif %}</strong>
      &nbsp;·&nbsp;
      {{ s.item.all_sources | join(', ') }}
      {% if s.item.stars is not none %}
      &nbsp;·&nbsp; &#11088; {{ s.item.stars | int }} stars
      {% endif %}
      {% if s.item.downloads is not none %}
      &nbsp;·&nbsp; &#8659; {{ s.item.downloads | int }} DLs
      {% endif %}
      {% if s.item.model_size %}
      &nbsp;·&nbsp; {{ s.item.model_size }}
      {% endif %}
      {% if s.item.license %}
      &nbsp;·&nbsp; {{ s.item.license }}
      {% endif %}
    </div>

    <hr class="divider">

    <!-- Summary -->
    <div class="summary">{{ s.summary }}</div>

    <!-- Hackathon idea (high-score items only) -->
    {% if s.hackathon_idea %}
    <div class="idea-block">
      <div class="idea-label">&#128161; Hackathon Idea</div>
      <div class="idea-text">{{ s.hackathon_idea }}</div>
    </div>
    {% endif %}

    <!-- Tech stack -->
    {% if s.tech_stack %}
    <div class="meta-row"><strong>Stack:</strong> {{ s.tech_stack }}</div>
    {% endif %}

    <!-- Why now -->
    {% if s.why_now %}
    <div class="meta-row"><strong>Why now:</strong> {{ s.why_now }}</div>
    {% endif %}

    <!-- Effort estimate -->
    {% if s.effort_estimate %}
    <div class="meta-row"><strong>Effort:</strong> {{ s.effort_estimate }}</div>
    {% endif %}

    <!-- Link pills -->
    <div class="link-row">
      {% if s.item.paper_url %}
        <a class="link-pill" href="{{ s.item.paper_url }}" target="_blank" rel="noopener">Paper</a>
      {% endif %}
      {% if s.item.github_url %}
        <a class="link-pill" href="{{ s.item.github_url }}" target="_blank" rel="noopener">Code</a>
      {% endif %}
      {% if s.item.huggingface_url %}
        <a class="link-pill" href="{{ s.item.huggingface_url }}" target="_blank" rel="noopener">Model</a>
      {% endif %}
      {% if s.item.demo_url %}
        <a class="link-pill" href="{{ s.item.demo_url }}" target="_blank" rel="noopener">Demo</a>
      {% endif %}
      {% if s.item.source_url %}
        <a class="link-pill" href="{{ s.item.source_url }}" target="_blank" rel="noopener">Source</a>
      {% endif %}
    </div>
  </div>
  {% endfor %}

  <!-- Footer -->
  <div class="footer">
    <div>Generated by HackRadar &mdash; your daily hackathon tech scout</div>
    {% if failed_sources %}
    <div class="failed">
      &#9888; Failed sources: {{ failed_sources | join(', ') }}
    </div>
    {% endif %}
  </div>

</div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_email(scored_items: list[ScoredItem], failed_sources: list[str]) -> None:
    """
    Render the HTML digest and send it via SMTP.

    Parameters
    ----------
    scored_items:
        Top-N ScoredItem objects, already sorted by score descending.
    failed_sources:
        List of source names that errored during scraping (shown in footer).

    Raises
    ------
    smtplib.SMTPException
        Re-raised on any SMTP failure — email failure is considered a
        pipeline failure (caller decides whether to abort or log).
    """
    today = datetime.now(tz=__import__('datetime').timezone.utc).strftime("%B %-d, %Y")
    subject = f"\U0001f52c HackRadar \u2014 {today} ({len(scored_items)} high-signal finds)"

    # Set up Jinja2 environment with a custom getattr so dataclasses work
    env = Environment(
        autoescape=True,
        keep_trailing_newline=True,
    )
    template = env.from_string(_EMAIL_TEMPLATE)
    html_body = template.render(
        date=today,
        count=len(scored_items),
        items=scored_items,
        failed_sources=failed_sources,
    )

    # Build the MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_ADDRESS
    msg["To"] = config.EMAIL_TO

    # Plain-text fallback (minimal)
    text_lines = [f"HackRadar — {today}", f"{len(scored_items)} high-signal finds", ""]
    for i, s in enumerate(scored_items, 1):
        text_lines.append(f"#{i} [{s.total_score:.1f}] {s.item.title}")
        text_lines.append(f"  {s.item.source_url}")
        text_lines.append(f"  {s.summary}")
        if s.hackathon_idea:
            text_lines.append(f"  IDEA: {s.hackathon_idea}")
        text_lines.append("")

    if failed_sources:
        text_lines.append(f"Failed sources: {', '.join(failed_sources)}")

    plain_body = "\n".join(text_lines)

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Send
    logger.info(
        "Sending email to %s via %s:%d",
        config.EMAIL_TO, config.SMTP_HOST, config.SMTP_PORT,
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        smtp.sendmail(
            from_addr=config.EMAIL_ADDRESS,
            to_addrs=[config.EMAIL_TO],
            msg=msg.as_string(),
        )

    logger.info("Email sent successfully: %r", subject)
