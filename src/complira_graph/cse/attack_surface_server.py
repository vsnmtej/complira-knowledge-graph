"""
complira_graph.cse.attack_surface_server
=========================================
In-process attack surface state for CSE simulation.

Owns all mutable state describing the current cybersecurity posture of the
simulated tenant during a run. Both the attacker and defender loops read/write
this state — all access happens within the subprocess, single event loop.

No I/O, no logging, no LLM calls. Pure state transitions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Action type constants
# ---------------------------------------------------------------------------

SCAN_SURFACE          = "SCAN_SURFACE"
EXPLOIT_CVE           = "EXPLOIT_CVE"
LATERAL_MOVE          = "LATERAL_MOVE"
ESCALATE_PRIVILEGES   = "ESCALATE_PRIVILEGES"
PIVOT_TARGET          = "PIVOT_TARGET"
MONITOR               = "MONITOR"
DETECT                = "DETECT"
INVESTIGATE           = "INVESTIGATE"
ESCALATE_TO_CISO      = "ESCALATE_TO_CISO"
PATCH                 = "PATCH"
DEPLOY_CONTROL        = "DEPLOY_CONTROL"
ROTATE_CREDENTIAL     = "ROTATE_CREDENTIAL"
FILE_CRA_NOTIFICATION    = "FILE_CRA_NOTIFICATION"
NOTIFY_BOARD             = "NOTIFY_BOARD"
ACKNOWLEDGE              = "ACKNOWLEDGE"

# Regulator actions
AUDIT_VULNERABILITY      = "AUDIT_VULNERABILITY"
ISSUE_COMPLIANCE_FINDING = "ISSUE_COMPLIANCE_FINDING"
FILE_INCIDENT_REPORT     = "FILE_INCIDENT_REPORT"
NOTIFY_REGULATOR         = "NOTIFY_REGULATOR"
APPROVE_EXCEPTION        = "APPROVE_EXCEPTION"

ALL_ACTIONS: frozenset[str] = frozenset({
    SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET,
    MONITOR, DETECT, INVESTIGATE, ESCALATE_TO_CISO, PATCH, DEPLOY_CONTROL,
    ROTATE_CREDENTIAL, FILE_CRA_NOTIFICATION, NOTIFY_BOARD, ACKNOWLEDGE,
    AUDIT_VULNERABILITY, ISSUE_COMPLIANCE_FINDING, FILE_INCIDENT_REPORT,
    NOTIFY_REGULATOR, APPROVE_EXCEPTION,
})


class AttackerPhase(str, Enum):
    RECON        = "recon"          # Must SCAN before exploiting
    EXPLOITATION = "exploitation"   # First successful scan unlocks this
    LATERAL      = "lateral"        # First exploit unlocks this
    ESCALATION   = "escalation"     # First lateral move unlocks this
    PIVOT        = "pivot"          # First privilege escalation unlocks this


@dataclass
class ChainStep:
    cve_id: str
    technique: str
    attacker_id: str
    round_no: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ActionResult:
    action_type: str
    outcome: str
    state_delta: dict[str, Any]
    significance: float = 0.5


class AttackSurfaceServer:
    """
    Shared in-process state server for the CSE simulation.

    Initialized from entity list in simulation_config.json.
    All state mutations happen through apply_action().
    """

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        # Derived from entities
        self.exploitable_cves: set[str] = {
            e["entity_id"]
            for e in entities
            if e.get("entity_type") == "cve"
        }
        self.all_components: set[str] = {
            e["entity_id"]
            for e in entities
            if e.get("entity_type") == "component"
        }
        self.regulatory_obligations: list[str] = [
            e["entity_id"]
            for e in entities
            if e.get("entity_type") == "regulatory_obligation"
        ]
        self.kev_cves: set[str] = {
            e["entity_id"]
            for e in entities
            if e.get("entity_type") == "cve" and e.get("is_kev")
        }

        # Mutable state
        self.chain_steps: list[ChainStep] = []
        self.patched_cves: set[str] = set()
        self.acknowledged_cves: set[str] = set()
        self.reached_components: set[str] = set()
        self.controls_deployed: list[str] = []
        self.current_target: str | None = None
        self.privilege_level: int = 0         # 0=user, 1=admin, 2=root
        self.monitoring_active: bool = False
        self.detection_events: list[dict[str, Any]] = []
        self.investigations: set[str] = set()  # cve_ids under investigation
        self.ciso_alerted: bool = False
        self.board_notified: bool = False
        self.cra_notified: bool = False
        self.cra_notification_round: int | None = None
        self.credential_rotated: bool = False

        # Attacker phase state machine (C-04)
        self.attacker_phase: AttackerPhase = AttackerPhase.RECON
        self.exploit_attempts: dict[str, int] = {}   # cve_id → attempt count (C-03)

        # LLM health tracking (C-05)
        self.llm_failure_count: int = 0
        self.simulation_degraded: bool = False

        # Regulator state
        self.compliance_gaps: list[dict[str, Any]] = []
        self.incident_report_filed: bool = False
        self.regulator_notified: bool = False
        self.exceptions_approved: list[str] = []  # cve_ids with approved exception

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_action(self, action_type: str, payload: dict[str, Any], round_no: int = 0) -> ActionResult:
        handler = _ACTION_HANDLERS.get(action_type)
        if handler is None:
            return ActionResult(action_type, "unknown_action", {}, significance=0.0)
        return handler(self, payload, round_no)

    def get_exploitable_cves(self) -> list[str]:
        return [c for c in self.exploitable_cves if c not in self.patched_cves]

    def get_chain_steps(self) -> list[ChainStep]:
        return list(self.chain_steps)

    def get_available_attacker_actions(self) -> list[str]:
        """Return actions available given the current attacker phase (C-04)."""
        phase = self.attacker_phase
        if phase == AttackerPhase.RECON:
            return [SCAN_SURFACE]
        if phase == AttackerPhase.EXPLOITATION:
            return [SCAN_SURFACE, EXPLOIT_CVE]
        if phase == AttackerPhase.LATERAL:
            return [SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE]
        if phase == AttackerPhase.ESCALATION:
            return [SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES]
        return [SCAN_SURFACE, EXPLOIT_CVE, LATERAL_MOVE, ESCALATE_PRIVILEGES, PIVOT_TARGET]

    def get_state_snapshot(self) -> dict[str, Any]:
        detected_cve_ids = [e["cve_id"] for e in self.detection_events if e.get("cve_id")]
        return {
            "exploitable_cves":    list(self.exploitable_cves - self.patched_cves),
            "patched_cves":        list(self.patched_cves),
            "detected_cves":       detected_cve_ids,                     # C-11
            "undetected_exploitable": [
                c for c in self.get_exploitable_cves()
                if c not in detected_cve_ids
            ],
            "chain_step_count":    len(self.chain_steps),
            "reached_components":  list(self.reached_components),
            "controls_deployed":   list(self.controls_deployed),
            "privilege_level":     self.privilege_level,
            "monitoring_active":   self.monitoring_active,
            "ciso_alerted":        self.ciso_alerted,
            "board_notified":      self.board_notified,
            "cra_notified":        self.cra_notified,
            "credential_rotated":  self.credential_rotated,
            "compliance_gap_count": len(self.compliance_gaps),
            "incident_report_filed": self.incident_report_filed,
            "regulator_notified":  self.regulator_notified,
            "exceptions_approved": list(self.exceptions_approved),
            "attacker_phase":      self.attacker_phase.value,            # C-04
            "llm_failure_count":   self.llm_failure_count,
            "simulation_degraded": self.simulation_degraded,
        }


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _action_scan_surface(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    visible = server.get_exploitable_cves()
    # C-04: RECON → EXPLOITATION after round 2 and at least 1 CVE found (F-003 fix)
    if (
        server.attacker_phase == AttackerPhase.RECON
        and round_no >= 2
        and len(visible) > 0
    ):
        server.attacker_phase = AttackerPhase.EXPLOITATION
    return ActionResult(
        SCAN_SURFACE,
        f"scan_complete: {len(visible)} exploitable CVEs visible",
        {"visible_cve_count": len(visible)},
        significance=0.3,
    )


def _compute_exploit_probability(
    server: AttackSurfaceServer,
    cve_id: str,
) -> tuple[float, list[str]]:
    """
    Probabilistic exploit success model (C-02).
    Returns (probability, modifier_reasons).
    """
    is_kev = cve_id in server.kev_cves
    base = 0.85 if is_kev else 0.60
    reasons = [f"base={'0.85 (KEV)' if is_kev else '0.60 (non-KEV)'}"]
    modifiers = 0.0

    if server.monitoring_active:
        modifiers -= 0.15
        reasons.append("monitoring_active: -0.15")

    detected_ids = {e["cve_id"] for e in server.detection_events if e.get("cve_id")}
    if cve_id in detected_ids:
        modifiers -= 0.20
        reasons.append("detection_event_exists: -0.20")

    if server.controls_deployed:
        modifiers -= 0.10                    # F-002: general deterrent
        reasons.append("controls_deployed_general: -0.10")
        cve_display = cve_id.replace("_", "-").lower()
        if any(cve_display in c.lower() for c in server.controls_deployed):
            modifiers -= 0.20                # F-002: CVE-specific control
            reasons.append("control_targets_cve: -0.20")

    if server.privilege_level == 0:
        modifiers -= 0.10
        reasons.append("no_foothold: -0.10")

    prior = server.exploit_attempts.get(cve_id, 0)
    if prior > 0:
        penalty = min(prior * 0.10, 0.30)
        modifiers -= penalty
        reasons.append(f"repeated_attempt×{prior}: -{penalty:.2f}")

    prob = max(0.05, min(0.95, base + modifiers))
    return prob, reasons


def _action_exploit_cve(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    technique = payload.get("technique", "T1190")
    attacker_id = payload.get("agent_id", "attacker_0")

    if cve_id not in server.get_exploitable_cves():
        return ActionResult(EXPLOIT_CVE, f"cve_not_exploitable: {cve_id}", {}, significance=0.2)

    # Track attempt regardless of outcome (C-03)
    server.exploit_attempts[cve_id] = server.exploit_attempts.get(cve_id, 0) + 1

    # Probabilistic outcome (C-02)
    prob, reasons = _compute_exploit_probability(server, cve_id)
    roll = random.random()

    if roll > prob:
        # Failure — classify reason
        detected_ids = {e["cve_id"] for e in server.detection_events if e.get("cve_id")}
        if cve_id in detected_ids:
            outcome = f"exploit_blocked_by_detection: {cve_id}"
        elif server.controls_deployed:
            outcome = f"exploit_blocked_by_control: {cve_id}"
        else:
            outcome = f"exploit_failed_probabilistic: {cve_id} (p={prob:.2f}, roll={roll:.2f})"
        return ActionResult(
            EXPLOIT_CVE, outcome,
            {"cve_id": cve_id, "exploit_probability": prob, "probability_reasons": reasons},
            significance=0.20,
        )

    # Success
    step = ChainStep(cve_id=cve_id, technique=technique, attacker_id=attacker_id, round_no=round_no)
    server.chain_steps.append(step)

    # C-04: phase transitions on successful exploit
    if server.attacker_phase == AttackerPhase.EXPLOITATION:
        server.attacker_phase = AttackerPhase.LATERAL

    # SOC blind spot: exploit succeeded but defender never detected it
    detected_ids = {e["cve_id"] for e in server.detection_events if e.get("cve_id")}
    is_blind_spot = cve_id not in detected_ids

    sig = 0.9 if cve_id in server.kev_cves else 0.75
    return ActionResult(
        EXPLOIT_CVE,
        f"exploit_success: {cve_id} via {technique}",
        {
            "chain_step_added": True,
            "cve_id": cve_id,
            "soc_blind_spot": is_blind_spot,
            "exploit_probability": prob,
            "probability_reasons": reasons,
        },
        significance=sig,
    )


def _action_lateral_move(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    target_component = payload.get("target_component", "")
    if server.credential_rotated:
        return ActionResult(LATERAL_MOVE, "lateral_blocked_credential_rotated", {}, significance=0.4)
    if target_component:
        server.reached_components.add(target_component)
    # C-04: LATERAL → ESCALATION phase transition
    if server.attacker_phase == AttackerPhase.LATERAL:
        server.attacker_phase = AttackerPhase.ESCALATION
    return ActionResult(
        LATERAL_MOVE,
        f"lateral_move: reached {target_component}",
        {"reached": target_component},
        significance=0.7,
    )


def _action_escalate_privileges(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.privilege_level = min(server.privilege_level + 1, 2)
    # C-04: ESCALATION → PIVOT phase transition
    if server.attacker_phase == AttackerPhase.ESCALATION:
        server.attacker_phase = AttackerPhase.PIVOT
    return ActionResult(
        ESCALATE_PRIVILEGES,
        f"privilege_level_now: {server.privilege_level}",
        {"privilege_level": server.privilege_level},
        significance=0.8,
    )


def _action_pivot_target(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.current_target = payload.get("target", server.current_target)
    return ActionResult(
        PIVOT_TARGET,
        f"new_target: {server.current_target}",
        {"current_target": server.current_target},
        significance=0.5,
    )


def _action_monitor(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.monitoring_active = True
    return ActionResult(MONITOR, "monitoring_activated", {"monitoring_active": True}, significance=0.4)


def _action_detect(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    event = {"cve_id": cve_id, "round_no": round_no, "detected_at": datetime.now(timezone.utc).isoformat()}
    server.detection_events.append(event)
    sig = 0.85 if server.monitoring_active else 0.5
    return ActionResult(DETECT, f"detected: {cve_id}", {"detection_event": event}, significance=sig)


def _action_investigate(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    server.investigations.add(cve_id)
    return ActionResult(INVESTIGATE, f"investigating: {cve_id}", {"under_investigation": cve_id}, significance=0.5)


def _action_escalate_to_ciso(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.ciso_alerted = True
    return ActionResult(ESCALATE_TO_CISO, "ciso_alerted", {"ciso_alerted": True}, significance=0.9)


def _action_patch(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    if cve_id not in server.exploitable_cves:
        return ActionResult(PATCH, f"cve_not_found: {cve_id}", {}, significance=0.2)
    server.patched_cves.add(cve_id)
    server.exploitable_cves.discard(cve_id)
    return ActionResult(
        PATCH,
        f"patched: {cve_id}",
        {"patched_cve": cve_id, "exploitable_removed": True},
        significance=0.8,
    )


def _action_deploy_control(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    control = payload.get("control_id", "")
    server.controls_deployed.append(control)
    return ActionResult(DEPLOY_CONTROL, f"control_deployed: {control}", {"control": control}, significance=0.6)


def _action_rotate_credential(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.credential_rotated = True
    return ActionResult(ROTATE_CREDENTIAL, "credential_rotated", {"credential_rotated": True}, significance=0.7)


def _action_file_cra(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.cra_notified = True
    server.cra_notification_round = round_no
    return ActionResult(
        FILE_CRA_NOTIFICATION,
        f"cra_notification_filed: round {round_no}",
        {"cra_notified": True, "round_no": round_no},
        significance=0.9,
    )


def _action_notify_board(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.board_notified = True
    return ActionResult(NOTIFY_BOARD, "board_notified", {"board_notified": True}, significance=0.9)


def _action_acknowledge(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    server.acknowledged_cves.add(cve_id)
    return ActionResult(ACKNOWLEDGE, f"acknowledged: {cve_id}", {"acknowledged_cve": cve_id}, significance=0.4)


def _action_audit_vulnerability(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    exploited_cves = {step.cve_id for step in server.chain_steps}
    is_exploited = cve_id in exploited_cves
    outcome = f"audit_complete: {cve_id} {'exploited_in_chain' if is_exploited else 'clean'}"
    return ActionResult(AUDIT_VULNERABILITY, outcome, {"cve_id": cve_id, "exploited": is_exploited}, significance=0.6)


def _action_issue_compliance_finding(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    # C-12 / F-006: validate required fields
    from complira_graph.cse.constants import VALID_FRAMEWORKS, VALID_SEVERITIES
    cve_id = payload.get("cve_id", "")
    if not cve_id:
        raise ValueError("ISSUE_COMPLIANCE_FINDING requires non-empty cve_id")
    framework = payload.get("framework", "CRA")
    if framework not in VALID_FRAMEWORKS:
        raise ValueError(f"ISSUE_COMPLIANCE_FINDING unknown framework: {framework!r}")
    severity = payload.get("severity", "medium")
    if severity not in VALID_SEVERITIES:
        severity = "medium"

    gap: dict[str, Any] = {
        "requirement_key": payload.get("requirement_key", "unknown"),
        "framework": framework,
        "description": payload.get("description", ""),
        "severity": severity,
        "round_no": round_no,
        "cve_id": cve_id,
    }
    server.compliance_gaps.append(gap)
    outcome = f"gap_recorded: {gap['framework']} {gap['requirement_key']}"
    return ActionResult(ISSUE_COMPLIANCE_FINDING, outcome, {"gap": gap}, significance=0.8)


def _action_file_incident_report(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.incident_report_filed = True
    return ActionResult(FILE_INCIDENT_REPORT, "incident_report_filed", {"incident_report_filed": True}, significance=0.9)


def _action_notify_regulator(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    server.regulator_notified = True
    return ActionResult(NOTIFY_REGULATOR, "regulator_notified", {"regulator_notified": True}, significance=0.9)


def _action_approve_exception(server: AttackSurfaceServer, payload: dict, round_no: int) -> ActionResult:
    cve_id = payload.get("cve_id", "")
    server.exceptions_approved.append(cve_id)
    return ActionResult(APPROVE_EXCEPTION, f"exception_approved: {cve_id}", {"cve_id": cve_id}, significance=0.5)


_ACTION_HANDLERS: dict[str, Any] = {
    SCAN_SURFACE:             _action_scan_surface,
    EXPLOIT_CVE:              _action_exploit_cve,
    LATERAL_MOVE:             _action_lateral_move,
    ESCALATE_PRIVILEGES:      _action_escalate_privileges,
    PIVOT_TARGET:             _action_pivot_target,
    MONITOR:                  _action_monitor,
    DETECT:                   _action_detect,
    INVESTIGATE:              _action_investigate,
    ESCALATE_TO_CISO:         _action_escalate_to_ciso,
    PATCH:                    _action_patch,
    DEPLOY_CONTROL:           _action_deploy_control,
    ROTATE_CREDENTIAL:        _action_rotate_credential,
    FILE_CRA_NOTIFICATION:    _action_file_cra,
    NOTIFY_BOARD:             _action_notify_board,
    ACKNOWLEDGE:              _action_acknowledge,
    AUDIT_VULNERABILITY:      _action_audit_vulnerability,
    ISSUE_COMPLIANCE_FINDING: _action_issue_compliance_finding,
    FILE_INCIDENT_REPORT:     _action_file_incident_report,
    NOTIFY_REGULATOR:         _action_notify_regulator,
    APPROVE_EXCEPTION:        _action_approve_exception,
}
