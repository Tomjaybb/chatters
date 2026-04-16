"""Stage 6: Adult content keyword detection with confidence scoring.

Scans link titles, bio text, and surrounding text for adult content indicators.
Uses word-boundary matching (case-insensitive) to avoid false positives.
Returns per-text matches and a composite confidence score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Keyword registries
# ---------------------------------------------------------------------------

DIRECT_KEYWORDS: list[str] = [
    "exclusive content",
    "spicy content",
    "exclusive page",
    "spicy page",
    "vip content",
    "vip page",
    "private content",
    "premium content",
    "uncensored",
    "uncensored content",
    "nsfw",
    "18+",
    "adults only",
]

SOFT_KEYWORDS: list[str] = [
    "subscribe to me",
    "my exclusive",
    "my private",
    "behind the scenes",
    "bts content",
    "fan page",
    "members only",
]

PLATFORM_ADJACENT_KEYWORDS: list[str] = [
    "OF",       # case-sensitive match handled specially
    "O.F",
    "O.F.",
    "0F",       # zero-F evasion
    "find me elsewhere",
    "all my links",
    "more links below",
    "spicy links",
    "spicy site",
]

# Emojis that signal adult content when paired with action words
INDICATOR_EMOJIS: list[str] = [
    "\U0001F336\uFE0F",  # 🌶️
    "\U0001F51E",         # 🔞
    "\U0001F351",         # 🍑
    "\U0001F48B",         # 💋
    "\U0001F608",         # 😈
    "\U0001F525",         # 🔥
]

EMOJI_COMPANION_WORDS: list[str] = [
    "link",
    "subscribe",
    "click",
    "join",
    "see more",
    "tap",
    "below",
    "bio",
]


def _build_pattern(phrase: str, *, case_sensitive: bool = False) -> re.Pattern[str]:
    """Build a word-boundary regex for *phrase*.

    For short uppercase tokens like ``OF`` we use a case-sensitive pattern to
    avoid matching the English word "of".
    """
    escaped = re.escape(phrase)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<!\w){escaped}(?!\w)", flags)


# Pre-compiled patterns --------------------------------------------------

_DIRECT_PATTERNS = [(_build_pattern(k), k, "direct") for k in DIRECT_KEYWORDS]
_SOFT_PATTERNS = [(_build_pattern(k), k, "soft") for k in SOFT_KEYWORDS]

# Platform-adjacent: "OF", "O.F", "O.F.", "0F" are case-sensitive
_PLATFORM_PATTERNS: list[tuple[re.Pattern[str], str, str]] = []
for k in PLATFORM_ADJACENT_KEYWORDS:
    cs = k in {"OF", "O.F", "O.F.", "0F"}
    _PLATFORM_PATTERNS.append((_build_pattern(k, case_sensitive=cs), k, "platform_adjacent"))

_ALL_PATTERNS = _DIRECT_PATTERNS + _SOFT_PATTERNS + _PLATFORM_PATTERNS

_EMOJI_RE = re.compile("|".join(re.escape(e) for e in INDICATOR_EMOJIS))
_COMPANION_RE = re.compile(
    "|".join(rf"(?<!\w){re.escape(w)}(?!\w)" for w in EMOJI_COMPANION_WORDS),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class KeywordMatch:
    keyword: str
    category: str          # "direct" | "soft" | "platform_adjacent" | "emoji"
    context: str = ""      # snippet of surrounding text


@dataclass
class KeywordResult:
    matches: list[KeywordMatch] = field(default_factory=list)
    confidence_score: int = 0

    @property
    def has_direct(self) -> bool:
        return any(m.category == "direct" for m in self.matches)

    @property
    def has_soft(self) -> bool:
        return any(m.category == "soft" for m in self.matches)

    @property
    def has_emoji(self) -> bool:
        return any(m.category == "emoji" for m in self.matches)

    @property
    def has_platform_adjacent(self) -> bool:
        return any(m.category == "platform_adjacent" for m in self.matches)

    @property
    def status(self) -> str:
        if self.confidence_score >= 80:
            return "likely_paid_creator"
        if self.confidence_score >= 50:
            return "likely_paid_creator"
        if self.confidence_score >= 40:
            return "review_queue"
        return "unlikely"

    @property
    def matched_keywords(self) -> list[str]:
        return [m.keyword for m in self.matches]


# ---------------------------------------------------------------------------
# Core scanning
# ---------------------------------------------------------------------------

def _extract_context(text: str, match: re.Match[str], window: int = 40) -> str:
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return text[start:end].strip()


def scan_text(text: str) -> list[KeywordMatch]:
    """Scan a single text blob and return all keyword matches."""
    if not text:
        return []

    matches: list[KeywordMatch] = []
    seen: set[str] = set()

    # Standard keyword categories
    for pattern, keyword, category in _ALL_PATTERNS:
        m = pattern.search(text)
        if m and keyword not in seen:
            seen.add(keyword)
            matches.append(KeywordMatch(
                keyword=keyword,
                category=category,
                context=_extract_context(text, m),
            ))

    # Emoji detection: emoji + companion word in same text
    emoji_hits = _EMOJI_RE.findall(text)
    companion_hit = _COMPANION_RE.search(text)
    if emoji_hits and companion_hit:
        for emoji in set(emoji_hits):
            key = f"emoji:{emoji}"
            if key not in seen:
                seen.add(key)
                matches.append(KeywordMatch(
                    keyword=emoji,
                    category="emoji",
                    context=text[:80].strip(),
                ))

    return matches


def calculate_confidence(
    matches: list[KeywordMatch],
    *,
    has_subscription_link: bool = False,
) -> int:
    """Compute a 0-100 confidence score from keyword matches.

    Scoring rules (highest applicable wins, but categories can stack):
    - Confirmed subscription link present  → 100
    - Multiple direct keywords              → 80
    - Single direct keyword                 → 70
    - Platform-adjacent keyword             → 65
    - Soft keywords + emoji                 → 60
    - Multiple soft keywords                → 50
    - Single soft keyword                   → 30
    - Emoji indicators alone                → 20
    """
    if has_subscription_link:
        return 100

    if not matches:
        return 0

    direct_count = sum(1 for m in matches if m.category == "direct")
    soft_count = sum(1 for m in matches if m.category == "soft")
    emoji_count = sum(1 for m in matches if m.category == "emoji")
    platform_count = sum(1 for m in matches if m.category == "platform_adjacent")

    score = 0

    if direct_count >= 2:
        score = max(score, 80)
    elif direct_count == 1:
        score = max(score, 70)

    if platform_count >= 1:
        score = max(score, 65)

    if soft_count >= 1 and emoji_count >= 1:
        score = max(score, 60)

    if soft_count >= 2:
        score = max(score, 50)
    elif soft_count == 1:
        score = max(score, 30)

    if emoji_count >= 1 and score < 30:
        score = max(score, 20)

    # Small additive bumps for stacking (capped at 95 — only a real link gets 100)
    bonus = 0
    if direct_count >= 1 and platform_count >= 1:
        bonus += 5
    if direct_count >= 1 and emoji_count >= 1:
        bonus += 3
    if soft_count >= 1 and platform_count >= 1:
        bonus += 3

    return min(score + bonus, 95)


def detect_keywords(
    texts: list[str],
    *,
    has_subscription_link: bool = False,
) -> KeywordResult:
    """Run the full keyword detection pipeline across multiple text blobs.

    Parameters
    ----------
    texts:
        List of text snippets (bio text, link titles, descriptions, etc.)
    has_subscription_link:
        If True, the account already has a confirmed subscription platform link
        and the confidence is automatically 100.

    Returns
    -------
    KeywordResult with all matches and the composite confidence score.
    """
    all_matches: list[KeywordMatch] = []
    seen_keys: set[str] = set()

    for text in texts:
        for m in scan_text(text):
            key = (m.keyword, m.category)
            if key not in seen_keys:
                seen_keys.add(key)
                all_matches.append(m)

    confidence = calculate_confidence(
        all_matches,
        has_subscription_link=has_subscription_link,
    )

    return KeywordResult(matches=all_matches, confidence_score=confidence)
