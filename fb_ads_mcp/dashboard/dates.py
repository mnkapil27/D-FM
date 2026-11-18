"""Date ranges for the dashboard date picker."""

from __future__ import annotations

from datetime import date, timedelta

from ..insights import date_params

# The presets shown in the date picker (all are real Meta presets).
PRESETS = [
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("last_7d", "Last 7 days"),
    ("last_14d", "Last 14 days"),
    ("last_30d", "Last 30 days"),
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("last_90d", "Last 90 days"),
    ("maximum", "All time"),
]
PRESET_LABELS = dict(PRESETS)
DEFAULT_PRESET = "last_7d"


def resolve_range(preset: str, today: date | None = None) -> tuple[date, date]:
    """Turn a Meta preset into real dates (same rules Meta uses: 'last_7d' ends yesterday)."""
    t = today or date.today()
    y = t - timedelta(days=1)
    if preset == "today":
        return t, t
    if preset == "yesterday":
        return y, y
    if preset.startswith("last_") and preset.endswith("d") and preset[5:-1].isdigit():
        n = int(preset[5:-1])
        return t - timedelta(days=n), y
    if preset == "this_month":
        return t.replace(day=1), t
    if preset == "last_month":
        end = t.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if preset == "maximum":
        return t - timedelta(days=364), t
    raise ValueError(f"Unknown date range '{preset}'")


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Wrong date '{value}'. Use YYYY-MM-DD.") from None


class Period:
    """What the user picked in the date picker."""

    def __init__(self, preset: str | None = None, since: str | None = None,
                 until: str | None = None):
        since = (since or "").strip() or None
        until = (until or "").strip() or None
        if since or until:
            if not (since and until):
                raise ValueError("Pick both a start date and an end date.")
            s, u = parse_day(since), parse_day(until)
            if s > u:
                s, u = u, s
            self.preset = None
            self.since, self.until = s, u
        else:
            self.preset = preset if preset in PRESET_LABELS else DEFAULT_PRESET
            self.since, self.until = resolve_range(self.preset)

    def meta_params(self) -> dict:
        if self.preset:
            return date_params(self.preset, None, None)
        return date_params(None, self.since.isoformat(), self.until.isoformat())

    def days(self) -> int:
        return (self.until - self.since).days + 1

    def time_increment(self):
        """Daily bars for short ranges, monthly bars for long ones."""
        if self.preset == "maximum" or self.days() > 92:
            return "monthly"
        return 1

    def label(self) -> str:
        if self.preset == "maximum":
            return "All time"
        rng = fmt_range(self.since, self.until)
        if self.preset:
            return f"{PRESET_LABELS[self.preset]} ({rng})"
        return rng

    def query(self) -> str:
        if self.preset:
            return f"preset={self.preset}"
        return f"since={self.since.isoformat()}&until={self.until.isoformat()}"

    def cache_key(self) -> str:
        return self.preset or f"{self.since}_{self.until}"


def fmt_day(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def fmt_range(a: date, b: date) -> str:
    if a == b:
        return fmt_day(a)
    if a.year == b.year:
        return f"{a.day} {a.strftime('%b')} – {fmt_day(b)}"
    return f"{fmt_day(a)} – {fmt_day(b)}"
