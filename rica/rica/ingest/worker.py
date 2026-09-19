"""rica-ingest: pulls the knowledge repo and keeps Qdrant in sync (§7.2).

Every sync_interval_s: git fetch → if origin moved, reset --hard to it → index().
cleanup="full" makes Qdrant match the repo: edited notes are replaced, deleted ones removed.
"""

import hashlib
import json
import logging
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from langchain_classic.indexes import SQLRecordManager
from langchain_core.documents import Document
from langchain_core.indexing import index
from qdrant_client import QdrantClient

from rica.ingest.loader import load
from rica.retrieval.store import ensure_collection, vector_store
from rica.settings import Settings

log = logging.getLogger("rica.ingest")


def doc_key(doc: Document) -> str:
    """Content + metadata hash, as a UUID because Qdrant point IDs must be UUIDs or integers."""
    payload = json.dumps([doc.page_content, doc.metadata], sort_keys=True, default=str)
    return str(uuid.UUID(bytes=hashlib.sha256(payload.encode()).digest()[:16]))


class Worker:
    def __init__(self, settings: Settings):
        self.s = settings
        self.root = settings.knowledge_dir
        self.state_file = settings.data_dir / "ingest_state.json"
        client = QdrantClient(url=settings.qdrant_url)
        created = ensure_collection(client, settings.qdrant_collection)
        self.store = vector_store(settings, client)
        self.records = SQLRecordManager(
            namespace=f"qdrant/{settings.qdrant_collection}",
            db_url=f"sqlite:///{settings.data_dir / 'record_manager.db'}",
        )
        self.records.create_schema()
        if created:
            # A fresh collection with an old record DB would skip every "already indexed" chunk
            self.records.delete_keys(self.records.list_keys())
            self._save_state({})
        self._env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_SSH_COMMAND": (
                f"ssh -i {settings.deploy_key} -o IdentitiesOnly=yes "
                f"-o UserKnownHostsFile={settings.known_hosts} -o StrictHostKeyChecking=yes"
            ),
        }

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, env=self._env, check=True, capture_output=True, text=True
        ).stdout.strip()

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except FileNotFoundError:
            return {}

    def _save_state(self, state: dict) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self.state_file)

    def ensure_repo(self) -> None:
        if not (self.root / ".git").exists():
            self.git("init", "-q", "-b", self.s.knowledge_branch)
            self.git("remote", "add", "origin", self.s.knowledge_repo)
        else:
            self.git("remote", "set-url", "origin", self.s.knowledge_repo)

    def sync_once(self) -> dict | None:
        """Returns the index() result when a new commit was indexed, else None."""
        branch = self.s.knowledge_branch
        self.git("fetch", "-q", "--prune", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        sha = self.git("rev-parse", f"origin/{branch}")
        state = self._load_state()
        if sha == state.get("last_indexed_sha"):
            return None
        # reset, not pull: survives force-pushes and rewritten history
        self.git("reset", "-q", "--hard", sha)
        self.git("clean", "-q", "-ffdx")
        t0 = time.monotonic()
        docs = load(self.root)  # raises on any unreadable file → nothing is deleted
        result = index(
            docs, self.records, self.store, cleanup="full", source_id_key="source",
            key_encoder=doc_key, batch_size=64,
        )
        log.info(json.dumps({
            "event": "indexed", "sha": sha[:12], "chunks": len(docs), **result,
            "seconds": round(time.monotonic() - t0, 1),
        }))
        self._save_state({
            "last_indexed_sha": sha,
            "indexed_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "chunks": len(docs),
            "last_result": result,
        })
        return result

    def run_forever(self) -> None:
        self.ensure_repo()
        while True:
            try:
                self.sync_once()
            except subprocess.CalledProcessError as e:
                log.error("git %s failed: %s", e.cmd[1:3], (e.stderr or "").strip()[:500])
            except Exception:
                log.exception("sync failed; will retry")
            time.sleep(self.s.sync_interval_s)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    if not settings.knowledge_repo:
        raise SystemExit("KNOWLEDGE_REPO is not set")
    Worker(settings).run_forever()


if __name__ == "__main__":
    main()
