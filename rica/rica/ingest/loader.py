"""Loads the knowledge repo into chunk Documents (§7.3 steps 1–5)."""

import hashlib
import re
import subprocess
from pathlib import Path

import frontmatter
import pathspec
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

EXCLUDED = ("_rica/", ".git/")
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)
HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]

_header_splitter = MarkdownHeaderTextSplitter(HEADERS, strip_headers=False)
_text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="o200k_base", chunk_size=500, chunk_overlap=50
)


def list_files(root: Path) -> list[str]:
    """Repo-relative paths of Markdown files, minus _rica/ and .ricaignore matches."""
    ignore_file = root / ".ricaignore"
    lines = ignore_file.read_text().splitlines() if ignore_file.exists() else []
    spec = pathspec.GitIgnoreSpec.from_lines(lines)
    files = []
    for p in root.rglob("*.md"):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(EXCLUDED) or spec.match_file(rel) or not p.is_file():
            continue
        files.append(rel)
    return sorted(files)


def git_dates(root: Path) -> dict[str, str]:
    """Last commit date (ISO) per path, from one `git log` pass."""
    out = subprocess.run(
        ["git", "log", "--format=%x00%cI", "--name-only", "--no-renames"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    dates: dict[str, str] = {}
    for block in out.split("\x00")[1:]:
        date, *paths = block.strip().splitlines()
        for path in paths:
            dates.setdefault(path.strip(), date.strip())
    return dates


def strip_wikilinks(text: str) -> str:
    return _WIKILINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)


def _tags(value) -> list[str]:
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, list):
        return [str(t) for t in value]
    return []


def load_file(root: Path, rel: str, updated_at: str | None) -> list[Document]:
    # Raises on unreadable or non-UTF-8 files: the caller must abort the whole run,
    # or cleanup="full" would delete that file's chunks.
    post = frontmatter.loads((root / rel).read_text(encoding="utf-8"))
    body = strip_wikilinks(post.content)
    h1 = _H1.search(body)
    title = str(post.metadata.get("title") or (h1.group(1) if h1 else Path(rel).stem))
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    base = {
        "source": rel,
        "doc_id": hashlib.sha1(rel.encode()).hexdigest()[:16],
        "title": title,
        "kind": "about-me" if rel.startswith("about/") else "note",
        "folder": folder,
        "tags": _tags(post.metadata.get("tags")),
        "updated_at": updated_at,
    }
    chunks = _text_splitter.split_documents(_header_splitter.split_text(body))
    docs = []
    for i, chunk in enumerate(chunks):
        headings = [chunk.metadata[k] for _, k in HEADERS if chunk.metadata.get(k)]
        heading_path = " › ".join(headings)
        locator = " › ".join([title, *[h for h in headings if h != title]])
        docs.append(
            Document(
                page_content=f"Doc: {locator}\n\n{chunk.page_content}",
                metadata={**base, "heading_path": heading_path, "chunk_index": i},
            )
        )
    return docs


def load(root: Path) -> list[Document]:
    dates = git_dates(root)
    docs: list[Document] = []
    for rel in list_files(root):
        docs.extend(load_file(root, rel, dates.get(rel)))
    return docs
