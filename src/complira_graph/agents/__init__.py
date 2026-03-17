"""
Complira Graph Ingestion Agents.

This package contains all data ingestion agents for various data sources:
- Regulatory frameworks (CRA, NIST SSDF, etc.)
- Vulnerability databases (NVD, GHSA, OSV, etc.)
- Threat intelligence (MITRE ATT&CK, CAPEC, etc.)
- Security controls (D3FEND, CWE, etc.)
- Platform enumerations (CPE, etc.)
- VulnCheck intelligence (KEV, exploits, ransomware, botnets, threat actors, exploit chains, EOL)
"""

from complira_graph.agents.cpe import CPEAgent
from complira_graph.agents.cra import CRAAgent
from complira_graph.agents.nist_ssdf import NISTSSDFAgent

# Phase 3A: VulnCheck Integration (8 agents)
from complira_graph.agents.vulncheck_kev_agent import VulnCheckKEVAgent
from complira_graph.agents.vulncheck_nvd2_agent import VulnCheckNVD2Agent
from complira_graph.agents.vulncheck_exploits_agent import VulnCheckExploitsAgent
from complira_graph.agents.vulncheck_ransomware_agent import VulnCheckRansomwareAgent
from complira_graph.agents.vulncheck_botnets_agent import VulnCheckBotnetsAgent
from complira_graph.agents.vulncheck_threat_actors_agent import VulnCheckThreatActorsAgent
from complira_graph.agents.vulncheck_exploit_chains_agent import VulnCheckExploitChainsAgent
from complira_graph.agents.vulncheck_eol_agent import VulnCheckEOLAgent

__all__ = [
    "CPEAgent",
    "CRAAgent",
    "NISTSSDFAgent",
    # Phase 3A: VulnCheck agents (8 agents)
    "VulnCheckKEVAgent",
    "VulnCheckNVD2Agent",
    "VulnCheckExploitsAgent",
    "VulnCheckRansomwareAgent",
    "VulnCheckBotnetsAgent",
    "VulnCheckThreatActorsAgent",
    "VulnCheckExploitChainsAgent",
    "VulnCheckEOLAgent",
]
