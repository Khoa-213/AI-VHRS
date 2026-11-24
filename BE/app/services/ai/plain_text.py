"""The text the order assistant puts on an order is what the robot writes on paper: plain text with real line breaks.

Two things a model sends that do not belong on paper (bug report 2026-11-24, order 12514, gemini-3.5-flash-lite):
* a line break written as the two characters backslash + n (sometimes with two backslashes) inside a tool argument, so
  "Thông tin đồ án:\\n- Thành viên..." was stored and drawn with the backslashes. `unescape` turns them back into line
  breaks, but only when the text has no real line break: a model that sends real line breaks does not escape them, so a
  backslash + n left in such a text is meant (and what the customer types in the form never comes through here);
* chat formatting that has no meaning in handwriting: **bold**, # headings, > quotes, `code` and ``` fences. `for_paper`
  removes the markers and keeps the words. The list markers people write by hand (-, +, *, 1.) and blanks to fill in
  (____) stay.
"""
from __future__ import annotations

import re

_BREAK = re.compile(r"\\+(?:r\\+n|n|r)")         # \n, \\n, \r\n written as text
_TAB = re.compile(r"\\+t")
_QUOTE = re.compile(r"\\+([\"'])")              # \" when the whole argument was escaped once more
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_QUOTE_LINE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_FENCE = re.compile(r"^[ \t]*```[^\n]*(?:\n|$)", re.MULTILINE)


def unescape(text: str) -> str:
    """Line breaks (and the tabs / quotes escaped with them) a model wrote as backslash sequences, when the text has no
    real line break."""
    if "\\" not in text or "\n" in text or "\r" in text:
        return text
    text = _BREAK.sub("\n", text)
    text = _TAB.sub(" ", text)
    return _QUOTE.sub(r"\1", text)


def for_paper(text: str) -> str:
    """The text as the robot should write it (see the module text). Running it twice changes nothing more."""
    text = unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    text = _FENCE.sub("", text)
    text = _BOLD.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _QUOTE_LINE.sub("", text)
    return text.replace("`", "")
