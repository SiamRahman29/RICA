"""Owner profile from the knowledge repo's _rica/profile.md, hot-reloaded on change (§6.8)."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from rica.context import tokens

log = logging.getLogger(__name__)

PROFILE_TOKEN_WARN = 400
# Template values look like "<what RICA calls you>"
_PLACEHOLDER = re.compile(r"^\s*<[^>]*>\s*$")
_PLACEHOLDER_LINE = re.compile(r"^\s*[-*]?\s*<[^>]*>\s*$")


@dataclass(frozen=True)
class Profile:
    preferred_name: str
    timezone: str
    name: str | None = None
    location: str | None = None
    languages: list[str] = field(default_factory=list)
    body: str = ""


def _value(meta: dict, key: str) -> str | None:
    v = meta.get(key)
    if v is None or not isinstance(v, str) or _PLACEHOLDER.match(v) or not v.strip():
        return None
    return v.strip()


def _clean_body(body: str) -> str:
    """Drop unfilled template lines and headings left with nothing under them."""
    lines = [l for l in body.splitlines() if not _PLACEHOLDER_LINE.match(l)]
    out: list[str] = []
    for line in lines:
        if line.startswith("#"):
            while out and not out[-1].strip():
                out.pop()
            if out and out[-1].startswith("#"):
                out.pop()
            if out:
                out.append("")
        out.append(line)
    while out and (out[-1].startswith("#") or not out[-1].strip()):
        out.pop()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def parse(text: str, fallback_name: str, default_tz: str) -> Profile:
    post = frontmatter.loads(text)
    meta = post.metadata
    langs = meta.get("languages") or []
    return Profile(
        preferred_name=_value(meta, "preferred_name") or _value(meta, "name") or fallback_name,
        timezone=_value(meta, "timezone") or default_tz,
        name=_value(meta, "name"),
        location=_value(meta, "location"),
        languages=[l for l in langs if isinstance(l, str)],
        body=_clean_body(post.content),
    )


class ProfileStore:
    """Re-reads the file when its mtime changes; missing file → defaults."""

    def __init__(self, path: Path, fallback_name: str, default_tz: str):
        self.path = path
        self.fallback_name = fallback_name or "the owner"
        self.default_tz = default_tz
        self._mtime: float | None = None
        self._profile = Profile(preferred_name=self.fallback_name, timezone=default_tz)

    def get(self) -> Profile:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            if self._mtime is not None:
                log.warning("profile %s disappeared; using defaults", self.path)
            self._mtime = None
            self._profile = Profile(preferred_name=self.fallback_name, timezone=self.default_tz)
            return self._profile
        if mtime != self._mtime:
            try:
                profile = parse(self.path.read_text(), self.fallback_name, self.default_tz)
            except Exception:
                log.exception("could not parse %s; keeping the previous profile", self.path)
                return self._profile
            n = tokens.count(profile.body)
            if n > PROFILE_TOKEN_WARN:
                log.warning("profile body is %d tokens (> %d); it is sent on every request", n, PROFILE_TOKEN_WARN)
            self._profile, self._mtime = profile, mtime
            log.info("loaded profile %s (preferred_name=%s)", self.path, profile.preferred_name)
        return self._profile
