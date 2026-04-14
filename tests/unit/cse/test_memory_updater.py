"""
S-CSE-10 — Agent working memory (SQLite).

AC-CSE-14: Batch of 5 CyberAgentActivity objects flushed to SQLite with episode_text present.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from complira_graph.cse.memory_updater import CyberAgentActivity, CyberMemoryUpdater


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sim_dir(tmp_path: Path) -> Path:
    return tmp_path


def _make_activity(sim_id: str, round_no: int, suffix: str = "") -> CyberAgentActivity:
    return CyberAgentActivity(
        sim_id=sim_id,
        agent_id=f"agent_0{suffix}",
        agent_type="Attacker",
        round_no=round_no,
        action_type="EXPLOIT_CVE",
        target="CVE-2021-44228",
        outcome=f"exploited at round {round_no}",
        episode_text=f"Round {round_no}: Attacker exploited CVE-2021-44228. exploit_succeeded",
    )


# ---------------------------------------------------------------------------
# S-CSE-10 / AC-CSE-14
# ---------------------------------------------------------------------------

class TestCyberMemoryUpdater:
    def test_five_activities_flushed_to_sqlite(self, sim_dir: Path) -> None:
        """AC-CSE-14: 5 activities enqueued + flush_remaining() → all in SQLite."""
        updater = CyberMemoryUpdater(sim_dir, batch_size=5)

        for i in range(5):
            updater.record(_make_activity("sim-test", round_no=i + 1))

        updater.flush_remaining()
        time.sleep(0.1)  # allow background thread to write

        db_path = sim_dir / "cyber_agent_memory.db"
        assert db_path.exists(), "cyber_agent_memory.db must be created"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM cyber_agent_activities")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 5, f"Expected 5 activities in SQLite, got {count}"

    def test_episode_text_stored_in_sqlite(self, sim_dir: Path) -> None:
        """AC-CSE-14: episode_text must be readable from SQLite."""
        updater = CyberMemoryUpdater(sim_dir, batch_size=1)
        activity = _make_activity("sim-ep", round_no=1)
        updater.record(activity)
        updater.flush_remaining()
        time.sleep(0.1)

        conn = sqlite3.connect(str(sim_dir / "cyber_agent_memory.db"))
        cursor = conn.execute("SELECT episode_text FROM cyber_agent_activities WHERE sim_id = ?", ("sim-ep",))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert "Round 1" in row[0], "episode_text must be stored and readable"

    def test_batch_triggers_on_batch_size(self, sim_dir: Path) -> None:
        """Exactly batch_size records triggers an automatic flush."""
        updater = CyberMemoryUpdater(sim_dir, batch_size=3)

        for i in range(3):
            updater.record(_make_activity("sim-batch", round_no=i + 1))

        # Give the background flush thread time to write
        deadline = time.monotonic() + 2.0
        db_path = sim_dir / "cyber_agent_memory.db"
        while time.monotonic() < deadline:
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                count = conn.execute("SELECT COUNT(*) FROM cyber_agent_activities").fetchone()[0]
                conn.close()
                if count >= 3:
                    break
            time.sleep(0.05)

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM cyber_agent_activities").fetchone()[0]
        conn.close()
        assert count >= 3

    def test_record_is_nonblocking(self, sim_dir: Path) -> None:
        """record() must return immediately (non-blocking enqueue)."""
        updater = CyberMemoryUpdater(sim_dir, batch_size=100)

        start = time.monotonic()
        for i in range(20):
            updater.record(_make_activity("sim-nb", round_no=i + 1))
        elapsed = time.monotonic() - start

        assert elapsed < 0.5, f"record() blocking: {elapsed:.3f}s for 20 calls"
        updater.flush_remaining()

    def test_multiple_sim_ids_stored_separately(self, sim_dir: Path) -> None:
        """Activities from two different sim_ids are both stored."""
        updater = CyberMemoryUpdater(sim_dir, batch_size=1)
        updater.record(_make_activity("sim-A", round_no=1))
        updater.record(_make_activity("sim-B", round_no=1))
        updater.flush_remaining()
        time.sleep(0.2)

        conn = sqlite3.connect(str(sim_dir / "cyber_agent_memory.db"))
        rows = conn.execute("SELECT DISTINCT sim_id FROM cyber_agent_activities").fetchall()
        conn.close()
        sim_ids = {r[0] for r in rows}
        assert "sim-A" in sim_ids
        assert "sim-B" in sim_ids
