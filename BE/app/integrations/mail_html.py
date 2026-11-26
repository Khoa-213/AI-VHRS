"""The HTML part of every e-mail (owner request 2026-11-26): the AI-VHRS logo on top, then the plain text laid out.

Callers keep writing plain text (it stays the text/plain part, for clients that show no HTML). The layout is derived from it:
* paragraphs are separated by an empty line; a single line break stays a line break;
* a line that is only a link becomes a button (the address is printed small under it, for clients that block buttons);
* a line ending in ": <4 to 8 digits>" (a one-time code) shows the code large, letter-spaced, in a box;
* any other link in the text is clickable.
The logo is attached inline (Content-ID), so it shows without "load remote images" and needs no public URL.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "email_logo.png"   # 320x130, from report_logo.png
LOGO_CID = "ai-vhrs-logo"
BUTTON_LABEL = "Mở liên kết"

_URL = re.compile(r"https?://[^\s<>\"']+")
_ONLY_URL = re.compile(r"^\s*(https?://\S+)\s*$")
_CODE = re.compile(r"^(.*?:)\s*(\d{4,8})\s*$")

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


@lru_cache(maxsize=1)
def logo_bytes() -> bytes | None:
    try:
        return LOGO_PATH.read_bytes()
    except OSError:                                    # a missing asset never stops a mail
        return None


def _inline(text: str) -> str:
    """Escape a piece of text and make its links clickable."""
    out, last = [], 0
    for m in _URL.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        url = html.escape(m.group(0), quote=True)
        out.append(f'<a href="{url}" style="color:#1d4ed8;word-break:break-all">{url}</a>')
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def _line(line: str) -> str:
    m = _ONLY_URL.match(line)
    if m:
        url = html.escape(m.group(1), quote=True)
        return (f'<div style="margin:14px 0 6px"><a href="{url}" style="display:inline-block;background:#111827;color:#ffffff;'
                f'text-decoration:none;font-weight:600;padding:12px 22px;border-radius:8px">{BUTTON_LABEL}</a></div>'
                f'<div style="font-size:12px;color:#6b7280;word-break:break-all">{url}</div>')
    m = _CODE.match(line)
    if m:
        return (f'{_inline(m.group(1))}<div style="margin:12px 0 4px;font-size:30px;font-weight:700;letter-spacing:8px;'
                f'font-family:Menlo,Consolas,monospace;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:8px;'
                f'padding:12px 16px;text-align:center;color:#111827">{m.group(2)}</div>')
    return _inline(line)


def render(body: str, subject: str, *, with_logo: bool) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", body.replace("\r\n", "\n").strip()) if p.strip()]
    parts = []
    for p in paragraphs:
        parts.append('<p style="margin:0 0 14px">' + "<br>".join(_line(x) for x in p.split("\n")) + "</p>")
    logo = (f'<tr><td style="padding:24px 28px 8px;text-align:center"><img src="cid:{LOGO_CID}" width="160" height="65" '
            f'alt="AI-VHRS" style="display:inline-block;border:0;width:160px;height:auto"></td></tr>') if with_logo else ""
    return (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{html.escape(subject)}</title></head>'
            f'<body style="margin:0;padding:0;background:#f4f5f7">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 12px">'
            f'<tr><td align="center">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;'
            f'border:1px solid #e5e7eb;border-radius:12px">'
            f'{logo}'
            f'<tr><td style="padding:12px 28px 20px;font-family:{FONT};font-size:15px;line-height:1.6;color:#1f2937">'
            f'{"".join(parts)}</td></tr>'
            f'<tr><td style="padding:14px 28px 22px;border-top:1px solid #f0f0f0;font-family:{FONT};font-size:12px;color:#9ca3af;'
            f'text-align:center">AI-VHRS · Xưởng Nét Việt</td></tr>'
            f'</table></td></tr></table></body></html>')
