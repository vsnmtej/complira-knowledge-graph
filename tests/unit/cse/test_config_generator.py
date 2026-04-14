"""
S-CSE-05 — Config synthesis.

AC-CSE-08: simulation_config.json has cra_deadline_round=24, hours_per_round=1,
           total_rounds=48 for KEV trigger.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from complira_graph.cse.config_generator import CyberSimConfigGenerator
from complira_graph.cse.graph_reader import CyberEntityNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_entities(n: int = 3) -> list[CyberEntityNode]:
    return [
        CyberEntityNode(
            entity_id=f"CVE-2021-{i:04d}",
            entity_type="cve",
            severity=7.5,
            is_kev=(i == 0),
            regulatory_refs=["FDA_524B"],
            component_name=f"comp_{i}",
        )
        for i in range(n)
    ]


def _make_profiles() -> list[dict]:
    return [
        {"agent_type": t, "role": t, "objectives": [], "constraints": []}
        for t in ("Attacker", "SOCAnalyst", "DevSecOps", "CISO", "Regulator")
    ]


# ---------------------------------------------------------------------------
# S-CSE-05 / AC-CSE-08
# ---------------------------------------------------------------------------

class TestConfigGenerator:
    def test_kev_triggered_total_rounds_48(self, tmp_path: Path) -> None:
        """AC-CSE-08: total_rounds must be 48 for kev_triggered."""
        gen = CyberSimConfigGenerator()
        config = gen.generate(
            sim_id="sim-001",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        assert config["total_rounds"] == 48

    def test_kev_triggered_cra_deadline_round_24(self, tmp_path: Path) -> None:
        """AC-CSE-08: cra_deadline_round must be 24."""
        gen = CyberSimConfigGenerator()
        config = gen.generate(
            sim_id="sim-001",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        assert config["cra_deadline_round"] == 24

    def test_kev_triggered_hours_per_round_1(self, tmp_path: Path) -> None:
        """AC-CSE-08: hours_per_round must be 1."""
        gen = CyberSimConfigGenerator()
        config = gen.generate(
            sim_id="sim-001",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        assert config["hours_per_round"] == 1

    def test_monthly_posture_sim_total_rounds_720(self, tmp_path: Path) -> None:
        """monthly_posture_sim must produce total_rounds=720."""
        gen = CyberSimConfigGenerator()
        config = gen.generate(
            sim_id="sim-002",
            tenant_id="tenant-abc",
            trigger_type="monthly_posture_sim",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        assert config["total_rounds"] == 720

    def test_config_file_written_to_sim_dir(self, tmp_path: Path) -> None:
        """generate() must write simulation_config.json to sim_dir."""
        gen = CyberSimConfigGenerator()
        gen.generate(
            sim_id="sim-003",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        config_path = tmp_path / "simulation_config.json"
        assert config_path.exists(), "simulation_config.json must be written to sim_dir"
        config = json.loads(config_path.read_text())
        assert config["sim_id"] == "sim-003"

    def test_agent_profiles_included(self, tmp_path: Path) -> None:
        """agent_profiles list must be present in config."""
        gen = CyberSimConfigGenerator()
        config = gen.generate(
            sim_id="sim-004",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        assert "agent_profiles" in config
        assert len(config["agent_profiles"]) == 5

    def test_entities_included_in_config(self, tmp_path: Path) -> None:
        """entities list (for attack surface server) must be in config."""
        gen = CyberSimConfigGenerator()
        entities = _make_entities(3)
        config = gen.generate(
            sim_id="sim-005",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=entities,
            sim_dir=tmp_path,
        )
        assert "entities" in config
        assert len(config["entities"]) == 3

    def test_kev_scheduled_events_generated(self, tmp_path: Path) -> None:
        """KEV CVEs must appear in scheduled_events for early rounds."""
        gen = CyberSimConfigGenerator()
        entities = _make_entities(3)  # entity 0 has is_kev=True
        config = gen.generate(
            sim_id="sim-006",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=entities,
            sim_dir=tmp_path,
        )
        events = config.get("scheduled_events", [])
        assert any(e.get("round", e.get("round_no", 999)) <= 5 for e in events), (
            "KEV CVE must produce a scheduled event in rounds 1-5"
        )

    def test_config_contains_required_top_level_keys(self, tmp_path: Path) -> None:
        """Config dict must contain all schema-required top-level keys."""
        required = {"sim_id", "tenant_id", "trigger_type", "total_rounds",
                    "hours_per_round", "cra_deadline_round", "agent_profiles",
                    "entities", "narrative_provider"}
        gen = CyberSimConfigGenerator()
        config = gen.generate(
            sim_id="sim-007",
            tenant_id="tenant-abc",
            trigger_type="kev_triggered",
            profiles=_make_profiles(),
            entities=_make_entities(),
            sim_dir=tmp_path,
        )
        missing = required - set(config.keys())
        assert not missing, f"Config missing required keys: {missing}"
