"""
complira_graph.cse.config_generator
=======================================
simulation_config.json synthesis for CSE simulation.

Pure data assembly — no LLM calls, no I/O except writing the config file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from complira_graph.cse.graph_reader import CyberEntityNode

# Round counts per trigger type
ROUND_COUNT = {
    "kev_triggered":       48,
    "monthly_posture_sim": 720,
}
HOURS_PER_ROUND = 1
CRA_DEADLINE_ROUND = 24


class CyberSimConfigGenerator:
    """Assembles and writes simulation_config.json."""

    def generate(
        self,
        sim_id: str,
        tenant_id: str,
        trigger_type: str,
        profiles: list[dict[str, Any]],
        entities: list[CyberEntityNode],
        sim_dir: str | Path,
        narrative_provider: str = "claude",
    ) -> dict[str, Any]:
        """
        Build simulation_config.json and write it to sim_dir.
        Returns the config dict.
        """
        total_rounds = ROUND_COUNT.get(trigger_type, ROUND_COUNT["kev_triggered"])
        scheduled_events = _build_scheduled_events(entities, total_rounds)

        config: dict[str, Any] = {
            "sim_id": sim_id,
            "tenant_id": tenant_id,
            "trigger_type": trigger_type,
            "total_rounds": total_rounds,
            "hours_per_round": HOURS_PER_ROUND,
            "cra_deadline_round": CRA_DEADLINE_ROUND,
            "narrative_provider": narrative_provider,
            "agent_profiles": profiles,
            "scheduled_events": scheduled_events,
            "entities": [_entity_to_dict(e) for e in entities],
        }

        config_path = Path(sim_dir) / "simulation_config.json"
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        return config


def _build_scheduled_events(entities: list[CyberEntityNode], total_rounds: int) -> list[dict[str, Any]]:
    """Map KEV CVEs to early-round scheduled exploit events."""
    events = []
    kev_cves = [e for e in entities if e.entity_type == "cve" and e.is_kev]
    for i, cve in enumerate(kev_cves[:5]):
        events.append({
            "round": max(1, i * 3 + 1),
            "event_type": "kev_exploit_attempt",
            "cve_id": cve.entity_id,
            "description": f"Scheduled KEV exploit attempt: {cve.entity_id}",
        })
    return events


def _entity_to_dict(e: CyberEntityNode) -> dict[str, Any]:
    return {
        "entity_id": e.entity_id,
        "entity_type": e.entity_type,
        "severity": e.severity,
        "is_kev": e.is_kev,
        "regulatory_refs": e.regulatory_refs,
        "component_name": e.component_name,
    }
