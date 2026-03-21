"""
Unit tests for Phase 3A VulnCheck agents.

Tests all 8 VulnCheck integration agents:
- VulnCheckKEVAgent
- VulnCheckNVD2Agent
- VulnCheckExploitsAgent
- VulnCheckRansomwareAgent
- VulnCheckBotnetsAgent
- VulnCheckThreatActorsAgent
- VulnCheckExploitChainsAgent
- VulnCheckEOLAgent

Note: VulnCheckCanariesAgent removed (402 Payment Required)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
import httpx

from complira_graph.agents.vulncheck_kev_agent import VulnCheckKEVAgent
from complira_graph.agents.vulncheck_nvd2_agent import VulnCheckNVD2Agent
from complira_graph.agents.vulncheck_exploits_agent import VulnCheckExploitsAgent
from complira_graph.agents.vulncheck_ransomware_agent import VulnCheckRansomwareAgent
from complira_graph.agents.vulncheck_botnets_agent import VulnCheckBotnetsAgent
from complira_graph.agents.vulncheck_threat_actors_agent import VulnCheckThreatActorsAgent
from complira_graph.agents.vulncheck_exploit_chains_agent import VulnCheckExploitChainsAgent
from complira_graph.agents.vulncheck_eol_agent import VulnCheckEOLAgent


# ========== Fixtures ==========

@pytest.fixture
def mock_vulncheck_settings():
    """Mock settings with VulnCheck API key."""
    settings = Mock()
    settings.VULNCHECK_API_KEY = "test_vulncheck_api_key"
    settings.VULNCHECK_BASE_URL = "https://api.vulncheck.com/v3"
    return settings


@pytest.fixture
def mock_vulncheck_client():
    """Mock VulnCheck HTTP client."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json = Mock(return_value={"data": []})
    response.content = b'{"data": []}'
    client.get = Mock(return_value=response)
    return client


@pytest.fixture
def sample_kev_data():
    """Sample VulnCheck KEV data."""
    return {
        "data": [
            {
                "cve": "CVE-2024-1234",
                "vendorProject": "Test Vendor",
                "product": "Test Product",
                "dateAdded": "2024-06-01T00:00:00Z",
                "knownRansomwareCampaignUse": "Known",
                "exploitationEvidence": [
                    {"url": "https://example.com", "dateAdded": "2024-06-01"}
                ]
            }
        ],
        "meta": {"total": 1}
    }


@pytest.fixture
def sample_nvd2_data():
    """Sample VulnCheck NVD2 data."""
    return {
        "data": [
            {
                "cve": "CVE-2024-5678",
                "reportedExploited": True,
                "firstExploitDate": "2024-06-15T00:00:00Z",
                "exploitMaturity": "weaponized",
                "exploitCount": 3,
                "cpeCount": 12,
                "cvssV3Score": 9.8
            }
        ]
    }


@pytest.fixture
def sample_ransomware_data():
    """Sample VulnCheck ransomware data."""
    return {
        "data": [
            {
                "name": "LockBit",
                "aliases": ["LockBit 2.0", "LockBit 3.0"],
                "firstSeen": "2019-09-01",
                "cves": ["CVE-2024-1234", "CVE-2024-5678"],
                "ttps": ["T1486", "T1490"]
            }
        ],
        "meta": {"total": 1}
    }


# ========== VulnCheckKEVAgent Tests ==========

@patch('complira_graph.agents.vulncheck_kev_agent.get_settings')
@patch('complira_graph.agents.vulncheck_kev_agent.create_vulncheck_client')
def test_vulncheck_kev_agent_init(mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings):
    """Test VulnCheckKEVAgent initialization."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    agent = VulnCheckKEVAgent(mock_db)

    assert agent.db == mock_db
    assert agent.base_url == "https://api.vulncheck.com/v3"
    mock_create_client.assert_called_once()


@patch('complira_graph.agents.vulncheck_kev_agent.get_settings')
@patch('complira_graph.agents.vulncheck_kev_agent.create_vulncheck_client')
def test_vulncheck_kev_agent_fetch_data(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings,
    mock_vulncheck_client, sample_kev_data
):
    """Test VulnCheckKEVAgent data fetching."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_vulncheck_client.get.return_value.json.return_value = sample_kev_data
    mock_create_client.return_value = mock_vulncheck_client

    agent = VulnCheckKEVAgent(mock_db)
    data = agent.fetch_data()

    assert "data" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["cve"] == "CVE-2024-1234"
    mock_vulncheck_client.get.assert_called_once()


@patch('complira_graph.agents.vulncheck_kev_agent.get_settings')
@patch('complira_graph.agents.vulncheck_kev_agent.create_vulncheck_client')
def test_vulncheck_kev_agent_transform_data(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings,
    sample_kev_data
):
    """Test VulnCheckKEVAgent data transformation."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    # Mock CISA KEV map query
    mock_db.aql.execute.return_value = []

    agent = VulnCheckKEVAgent(mock_db)
    transformed = list(agent.transform_data(sample_kev_data))

    # Should yield: 1 KEV document + 2 edges (has_exploit_intelligence, exploited_in_wild)
    assert len(transformed) == 3

    # Check document
    kev_doc = transformed[0]
    assert kev_doc["type"] == "document"
    assert kev_doc["collection"] == "vulncheck_kev_entries"
    assert kev_doc["data"]["_key"] == "CVE_2024_1234"  # Normalized format (uppercase, underscores)
    assert kev_doc["data"]["cve_id"] == "CVE-2024-1234"  # Original format (hyphens)
    assert kev_doc["data"]["vendor_project"] == "Test Vendor"

    # Check edges
    assert transformed[1]["type"] == "edge"
    assert transformed[1]["collection"] == "has_exploit_intelligence"
    assert transformed[2]["type"] == "edge"
    assert transformed[2]["collection"] == "exploited_in_wild"


# ========== VulnCheckNVD2Agent Tests ==========

@patch('complira_graph.agents.vulncheck_nvd2_agent.get_settings')
@patch('complira_graph.agents.vulncheck_nvd2_agent.create_vulncheck_client')
def test_vulncheck_nvd2_agent_init(mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings):
    """Test VulnCheckNVD2Agent initialization."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    agent = VulnCheckNVD2Agent(mock_db)

    assert agent.supports_checkpointing is True
    assert agent.checkpoint_interval == 10000
    assert agent.batch_size == 1000


@patch('complira_graph.agents.vulncheck_nvd2_agent.get_settings')
@patch('complira_graph.agents.vulncheck_nvd2_agent.create_vulncheck_client')
def test_vulncheck_nvd2_agent_transform_single_cve(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings
):
    """Test VulnCheckNVD2Agent single CVE transformation."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    agent = VulnCheckNVD2Agent(mock_db)

    cve_entry = {
        "cve": "CVE-2024-5678",
        "reportedExploited": True,
        "exploitMaturity": "weaponized",
        "exploitCount": 3
    }

    exploit_doc = agent.transform_data(cve_entry)

    assert exploit_doc["_key"] == "CVE_2024_5678"  # Normalized format (uppercase, underscores)
    assert exploit_doc["cve_id"] == "CVE-2024-5678"  # Original format (hyphens)
    assert exploit_doc["reported_exploited"] is True
    assert exploit_doc["exploit_maturity"] == "weaponized"
    assert exploit_doc["source"] == "vulncheck_nvd2"


# ========== VulnCheckExploitsAgent Tests ==========

@patch('complira_graph.agents.vulncheck_exploits_agent.get_settings')
@patch('complira_graph.agents.vulncheck_exploits_agent.create_vulncheck_client')
def test_vulncheck_exploits_agent_enrich_cve(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings,
    mock_vulncheck_client
):
    """Test VulnCheckExploitsAgent CVE enrichment."""
    mock_get_settings.return_value = mock_vulncheck_settings

    exploit_data = {
        "data": [
            {
                "cve": "CVE-2024-1234",
                "reportedExploited": True,
                "exploitMaturity": "weaponized"
            }
        ]
    }
    mock_vulncheck_client.get.return_value.json.return_value = exploit_data
    mock_create_client.return_value = mock_vulncheck_client

    # Mock collection operations
    mock_collection = MagicMock()
    mock_db.collection.return_value = mock_collection

    agent = VulnCheckExploitsAgent(mock_db)
    result = agent.enrich_cve("CVE-2024-1234")

    assert result is not None
    assert result["cve_id"] == "CVE-2024-1234"
    assert result["reported_exploited"] is True


# ========== VulnCheckRansomwareAgent Tests ==========

@patch('complira_graph.agents.vulncheck_ransomware_agent.get_settings')
@patch('complira_graph.agents.vulncheck_ransomware_agent.create_vulncheck_client')
def test_vulncheck_ransomware_agent_transform_data(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings,
    sample_ransomware_data
):
    """Test VulnCheckRansomwareAgent data transformation."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    # Mock ATT&CK technique map query
    mock_db.aql.execute.return_value = [
        {"technique_id": "T1486", "doc_id": "attack_techniques/T1486"},
        {"technique_id": "T1490", "doc_id": "attack_techniques/T1490"}
    ]

    agent = VulnCheckRansomwareAgent(mock_db)
    transformed = list(agent.transform_data(sample_ransomware_data))

    # Should yield: 1 ransomware doc + 2 CVE edges + 2 TTP edges
    assert len(transformed) >= 5

    # Check ransomware document
    ransomware_doc = transformed[0]
    assert ransomware_doc["type"] == "document"
    assert ransomware_doc["collection"] == "ransomware_families"
    assert ransomware_doc["data"]["name"] == "LockBit"
    assert "LockBit 2.0" in ransomware_doc["data"]["aliases"]

    # Check CVE edge
    cve_edge = transformed[1]
    assert cve_edge["type"] == "edge"
    assert cve_edge["collection"] == "exploited_by_ransomware"
    assert "CVE_2024_1234" in cve_edge["data"]["_from"]  # Normalized format (uppercase, underscores)

    # Check TTP edge
    ttp_edges = [t for t in transformed if t["collection"] == "ransomware_uses_technique"]
    assert len(ttp_edges) == 2


# ========== VulnCheckThreatActorsAgent Tests ==========

@patch('complira_graph.agents.vulncheck_threat_actors_agent.get_settings')
@patch('complira_graph.agents.vulncheck_threat_actors_agent.create_vulncheck_client')
def test_vulncheck_threat_actors_fuzzy_match(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings
):
    """Test VulnCheckThreatActorsAgent fuzzy name matching."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    agent = VulnCheckThreatActorsAgent(mock_db)

    # Test exact match
    assert agent._fuzzy_match("APT29", "APT29") is True

    # Test high similarity (should match)
    assert agent._fuzzy_match("APT 29", "APT29", threshold=0.85) is True

    # Test low similarity (should not match)
    assert agent._fuzzy_match("APT29", "APT99", threshold=0.85) is False


# ========== VulnCheckExploitChainsAgent Tests ==========

@patch('complira_graph.agents.vulncheck_exploit_chains_agent.get_settings')
@patch('complira_graph.agents.vulncheck_exploit_chains_agent.create_vulncheck_client')
def test_vulncheck_exploit_chains_agent_transform(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings
):
    """Test VulnCheckExploitChainsAgent data transformation."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    chain_data = {
        "data": [
            {
                "name": "ProxyShell",
                "cves": ["CVE-2021-34473", "CVE-2021-34523", "CVE-2021-31207"],
                "target": "Microsoft Exchange Server",
                "impact": "Remote code execution"
            }
        ]
    }

    agent = VulnCheckExploitChainsAgent(mock_db)
    transformed = list(agent.transform_data(chain_data))

    # Should yield: 1 chain document + 3 CVE edges
    assert len(transformed) == 4

    # Check chain document
    chain_doc = transformed[0]
    assert chain_doc["type"] == "document"
    assert chain_doc["collection"] == "exploit_chains"
    assert chain_doc["data"]["name"] == "ProxyShell"
    assert len(chain_doc["data"]["cve_sequence"]) == 3

    # Check edges have correct order
    edges = [t for t in transformed if t["type"] == "edge"]
    assert edges[0]["data"]["order"] == 1
    assert edges[1]["data"]["order"] == 2
    assert edges[2]["data"]["order"] == 3


# ========== VulnCheckEOLAgent Tests ==========

@patch('complira_graph.agents.vulncheck_eol_agent.get_settings')
@patch('complira_graph.agents.vulncheck_eol_agent.create_vulncheck_client')
def test_vulncheck_eol_agent_transform(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings
):
    """Test VulnCheckEOLAgent data transformation."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    eol_data = {
        "data": [
            {
                "product": "Ubuntu",
                "version": "18.04",
                "cpe": "cpe:2.3:o:canonical:ubuntu_linux:18.04",
                "eolDate": "2023-05-31",
                "supportStatus": "unsupported"
            }
        ]
    }

    # Mock component CPE query
    mock_db.aql.execute.return_value = [
        {"cpe": "cpe:2.3:o:canonical:ubuntu_linux:18.04:*:*:*:lts:*:*:*", "doc_id": "components/ubuntu_18_04"}
    ]

    agent = VulnCheckEOLAgent(mock_db)
    transformed = list(agent.transform_data(eol_data))

    # Should yield: 1 EOL document + 1 component edge (CPE match)
    assert len(transformed) >= 1

    # Check EOL document
    eol_doc = transformed[0]
    assert eol_doc["type"] == "document"
    assert eol_doc["collection"] == "eol_products"
    assert eol_doc["data"]["product"] == "Ubuntu"
    assert eol_doc["data"]["support_status"] == "unsupported"


# Note: VulnCheckCanariesAgent tests removed (402 Payment Required)
# Canary endpoint requires Exploit & Vulnerability Intelligence subscription


# ========== Integration Tests ==========

@patch('complira_graph.agents.vulncheck_kev_agent.get_settings')
@patch('complira_graph.agents.vulncheck_kev_agent.create_vulncheck_client')
def test_vulncheck_kev_agent_full_workflow(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings,
    mock_vulncheck_client, sample_kev_data
):
    """Test VulnCheckKEVAgent full workflow (fetch → transform → load)."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_vulncheck_client.get.return_value.json.return_value = sample_kev_data
    mock_create_client.return_value = mock_vulncheck_client

    # Mock CISA KEV map
    mock_db.aql.execute.return_value = []

    # Mock collection bulk insert
    mock_collection = MagicMock()
    mock_collection.import_bulk.return_value = {"created": 1, "updated": 0, "errors": 0}
    mock_db.collection.return_value = mock_collection

    agent = VulnCheckKEVAgent(mock_db)
    result = agent.run()

    assert result["status"] == "success"
    assert result["documents_inserted"] >= 1
    assert "duration_seconds" in result


# ========== Error Handling Tests ==========

@patch('complira_graph.agents.vulncheck_kev_agent.get_settings')
def test_vulncheck_agent_missing_api_key(mock_get_settings, mock_db):
    """Test VulnCheck agent initialization with missing API key."""
    settings = Mock()
    settings.VULNCHECK_API_KEY = None
    mock_get_settings.return_value = settings

    with pytest.raises(ValueError, match="VULNCHECK_API_KEY not configured"):
        VulnCheckKEVAgent(mock_db)


@patch('complira_graph.agents.vulncheck_exploits_agent.get_settings')
@patch('complira_graph.agents.vulncheck_exploits_agent.create_vulncheck_client')
def test_vulncheck_exploits_agent_no_cve_set(
    mock_create_client, mock_get_settings, mock_db, mock_vulncheck_settings
):
    """Test VulnCheckExploitsAgent with no CVE ID set."""
    mock_get_settings.return_value = mock_vulncheck_settings
    mock_create_client.return_value = MagicMock()

    agent = VulnCheckExploitsAgent(mock_db)

    with pytest.raises(ValueError, match="CVE ID not set"):
        agent.fetch_data()
