import subprocess

import pytest

from rica.ingest.loader import list_files, load, strip_wikilinks


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    files = {
        "_rica/profile.md": "---\npreferred_name: Ana\n---\n",
        "about/people.md": "# People\n\n## Family\n\nMy sister is [[notes/lina|Lina]].\n",
        "notes/trip.md": "---\ntitle: Trip plan\ntags: [travel, 2026]\n---\n## Day 1\n\nVisit the museum.\n",
        "notes/plain.md": "No headings here, see [[Some Page]].\n",
        "private/secret.md": "# Secret\n\nnever index\n",
        "README.md": "# Readme\n",
        ".ricaignore": "private/\nREADME.md\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return tmp_path


def test_list_files_respects_exclusions(repo):
    assert list_files(repo) == ["about/people.md", "notes/plain.md", "notes/trip.md"]


def test_metadata_and_contextual_header(repo):
    docs = {d.metadata["source"]: d for d in load(repo)}
    people = docs["about/people.md"]
    assert people.metadata["kind"] == "about-me" and people.metadata["title"] == "People"
    assert people.metadata["heading_path"] == "People › Family"
    assert people.page_content.startswith("Doc: People › Family\n\n")
    assert "sister is Lina." in people.page_content and "[[" not in people.page_content
    assert people.metadata["updated_at"]

    trip = docs["notes/trip.md"]
    assert trip.metadata["title"] == "Trip plan" and trip.metadata["tags"] == ["travel", "2026"]
    assert trip.metadata["kind"] == "note" and trip.metadata["folder"] == "notes"
    assert "---" not in trip.page_content

    assert docs["notes/plain.md"].metadata["title"] == "plain"


def test_long_doc_splits_with_chunk_index(repo):
    (repo / "notes/long.md").write_text("# Long\n\n" + "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(40)))
    chunks = [d for d in load(repo) if d.metadata["source"] == "notes/long.md"]
    assert len(chunks) > 3
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert len({c.metadata["doc_id"] for c in chunks}) == 1


def test_unreadable_file_aborts(repo):
    (repo / "notes/bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    with pytest.raises(UnicodeDecodeError):
        load(repo)


def test_strip_wikilinks():
    assert strip_wikilinks("see [[a/b|B]] and [[C]]") == "see B and C"
