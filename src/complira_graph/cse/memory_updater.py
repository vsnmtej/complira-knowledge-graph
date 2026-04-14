"""
complira_graph.cse.memory_updater
===================================
Agent working memory for CSE — per-run SQLite + ArangoDB flush.

Architecture:
  - Simulation loops call record() to enqueue CyberAgentActivity objects.
  - A background thread drains the queue and writes batches to SQLite.
  - Every time a batch of batch_size activities accumulates, it's also
    flushed to ArangoDB agent_action_logs.
  - flush_remaining() is called at simulation end to flush any partial batch.

SQLite uses check_same_thread=False because the background thread writes
while the main asyncio loop enqueues.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arango.database import StandardDatabase

log = logging.getLogger(__name__)

BATCH_SIZE = 5
_ARANGO_COLLECTION = "agent_action_logs"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cyber_agent_activities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id       TEXT NOT NULL,
    agent_id     TEXT NOT NULL,
    agent_type   TEXT NOT NULL,
    round_no     INTEGER NOT NULL,
    action_type  TEXT NOT NULL,
    target       TEXT,
    outcome      TEXT,
    episode_text TEXT NOT NULL,
    timestamp    TEXT NOT NULL
)
"""


@dataclass
class CyberAgentActivity:
    sim_id: str
    agent_id: str
    agent_type: str
    round_no: int
    action_type: str
    target: str
    outcome: str
    episode_text: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class CyberMemoryUpdater:
    """Queue-backed SQLite writer with periodic ArangoDB flush."""

    def __init__(self, sim_dir: str | Path, batch_size: int = BATCH_SIZE) -> None:
        self._db_path   = Path(sim_dir) / "cyber_agent_memory.db"
        self._batch_size = batch_size
        self._queue: queue.Queue[CyberAgentActivity | None] = queue.Queue()
        self._pending_for_arango: list[CyberAgentActivity] = []

        # SQLite: check_same_thread=False — background thread writes, main thread enqueues
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

        self._worker = threading.Thread(target=self._batch_write_worker, daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, activity: CyberAgentActivity) -> None:
        """Enqueue an activity for async SQLite write. Non-blocking."""
        self._queue.put(activity)

    def flush_remaining(self, db: "StandardDatabase | None" = None) -> None:
        """Drain queue and flush all remaining activities. Call at sim end."""
        self._queue.put(None)  # sentinel — signals worker to stop
        self._worker.join(timeout=30)

        # Flush pending ArangoDB batch (may be partial)
        if self._pending_for_arango and db is not None:
            self._flush_to_arango(db, self._pending_for_arango)
            self._pending_for_arango.clear()

        try:
            self._conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _batch_write_worker(self) -> None:
        while True:
            try:
                activity = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if activity is None:
                # Drain remaining items
                batch: list[CyberAgentActivity] = []
                while not self._queue.empty():
                    item = self._queue.get_nowait()
                    if item is not None:
                        batch.append(item)
                if batch:
                    self._write_batch_to_sqlite(batch)
                    self._pending_for_arango.extend(batch)
                break

            batch = [activity]
            while len(batch) < self._batch_size:
                try:
                    item = self._queue.get_nowait()
                    if item is None:
                        break
                    batch.append(item)
                except queue.Empty:
                    break

            if batch:
                self._write_batch_to_sqlite(batch)
                self._pending_for_arango.extend(batch)
                log.debug("cse_memory_batch_written", batch_size=len(batch))

    def _write_batch_to_sqlite(self, activities: list[CyberAgentActivity]) -> None:
        rows = [
            (a.sim_id, a.agent_id, a.agent_type, a.round_no,
             a.action_type, a.target, a.outcome, a.episode_text, a.timestamp)
            for a in activities
        ]
        try:
            self._conn.executemany(
                """INSERT INTO cyber_agent_activities
                   (sim_id, agent_id, agent_type, round_no, action_type,
                    target, outcome, episode_text, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self._conn.commit()
        except Exception as exc:
            log.error("cse_memory_sqlite_write_error", error=str(exc))

    def _flush_to_arango(self, db: "StandardDatabase", activities: list[CyberAgentActivity]) -> None:
        docs = [
            {
                "sim_id":       a.sim_id,
                "agent_id":     a.agent_id,
                "agent_type":   a.agent_type,
                "round_no":     a.round_no,
                "action_type":  a.action_type,
                "target":       a.target,
                "outcome":      a.outcome,
                "episode_text": a.episode_text,
                "timestamp":    a.timestamp,
            }
            for a in activities
        ]
        try:
            db.collection(_ARANGO_COLLECTION).insert_many(docs, silent=True)
            log.info("cse_memory_batch_flushed", count=len(docs), agent_id=activities[0].agent_id if docs else "")
        except Exception as exc:
            log.error("cse_memory_arango_flush_error", error=str(exc), count=len(docs))
