"""
complira_graph.cse.constants
=============================
Shared constants for CSE simulation.

Centralised here to avoid circular imports between attack_surface_server,
regulator_simulation, and technique_resolver.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Regulatory frameworks + requirements
# ---------------------------------------------------------------------------

VALID_FRAMEWORKS: frozenset[str] = frozenset({
    "CRA", "FDA_524B", "HIPAA", "NIST_800_53", "NIS2", "IEC_62443",
})

VALID_SEVERITIES: frozenset[str] = frozenset({
    "critical", "high", "medium", "low",
})

REQUIREMENT_KEYS: list[str] = [
    "CRA_art_13", "CRA_art_14", "CRA_art_24",
    "FDA_524B_sec_3", "FDA_524B_sec_4",
    "HIPAA_164_308", "HIPAA_164_312",
    "NIST_SI_2", "NIST_RA_5", "NIST_IR_6",
    "NIS2_art_21", "NIS2_art_23",
    "IEC_62443_3_3", "IEC_62443_4_2",
]

# ---------------------------------------------------------------------------
# ATT&CK technique fallback distribution by CVSS severity bucket
# ---------------------------------------------------------------------------

TECHNIQUE_BUCKETS: dict[str, list[str]] = {
    "critical": ["T1190", "T1133", "T1078"],   # External-facing exploit, VPN/remote, valid accounts
    "high":     ["T1059", "T1047", "T1055"],   # Command execution, WMI, process injection
    "medium":   ["T1203", "T1189", "T1566"],   # Client exploit, drive-by, phishing
    "low":      ["T1189", "T1204", "T1598"],   # Drive-by, user exec, recon
}
