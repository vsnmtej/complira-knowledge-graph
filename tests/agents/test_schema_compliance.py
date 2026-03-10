"""
Schema Compliance Tests for Vulnerability Agents

Tests all vulnerability ingestion agents to ensure their output validates
against the Vulnerability schema. Prevents TICKET-001 and TICKET-002 class bugs.

Note: Tests validate required fields and naming conventions without Pydantic
due to circular import issues between models.py and models/ package.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock

# Import agents
from complira_graph.agents.ghsa import GHSAAgent
from complira_graph.agents.nvd import NVDAgent


# Vulnerability schema requirements (from src/complira_graph/models.py:44-98)
VULNERABILITY_REQUIRED_FIELDS = {"vulnerability_id", "source"}
VULNERABILITY_OPTIONAL_FIELDS = {
    "cve_id", "summary", "description", "published", "modified", "last_modified",
    "withdrawn", "cvss_v2_score", "cvss_v2_vector", "cvss_v2_severity",
    "cvss_v3_score", "cvss_v3_vector", "cvss_v3_severity", "cwe_ids", "aliases",
    "references", "cpe_matches", "affected_packages", "cisa_enriched", "cisa_cwe_ids"
}
VALID_SOURCES = {"nvd", "osv", "ghsa"}
VALID_CVSS_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


class TestGHSAAgentSchemaCompliance:
    """Test GHSA agent output validates against Vulnerability schema."""

    @pytest.fixture
    def sample_ghsa_data(self):
        """Load sample GHSA API response."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "ghsa" / "sample_advisory.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.fixture
    def mock_db(self):
        """Mock database for agent initialization."""
        db = Mock()
        db.collection = Mock(return_value=Mock())
        return db

    def test_ghsa_agent_output_validates(self, mock_db, sample_ghsa_data):
        """GHSA agent output should validate against Vulnerability schema."""
        # Initialize agent
        agent = GHSAAgent(db=mock_db)

        # Transform sample data
        records = list(agent.transform_data([sample_ghsa_data]))

        # Filter out edge documents (has _from/_to fields)
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]

        assert len(vuln_docs) > 0, "No vulnerability documents generated"

        vuln_doc = vuln_docs[0]

        # Validate required fields
        assert "vulnerability_id" in vuln_doc, "Missing required field: vulnerability_id"
        assert vuln_doc["vulnerability_id"] is not None, "vulnerability_id cannot be None"
        assert vuln_doc["vulnerability_id"] == sample_ghsa_data["ghsa_id"], \
            "vulnerability_id should be ghsa_id for GHSA source"

        assert "source" in vuln_doc, "Missing required field: source"
        assert vuln_doc["source"] == "ghsa", "source should be 'ghsa'"

    def test_ghsa_agent_has_required_fields(self, mock_db, sample_ghsa_data):
        """GHSA agent must include all required fields."""
        agent = GHSAAgent(db=mock_db)
        records = list(agent.transform_data([sample_ghsa_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]
        vuln_doc = vuln_docs[0]

        # Required field: vulnerability_id
        assert "vulnerability_id" in vuln_doc, "Missing required field: vulnerability_id"
        assert vuln_doc["vulnerability_id"] is not None, "vulnerability_id cannot be None"

    def test_ghsa_agent_correct_field_names(self, mock_db, sample_ghsa_data):
        """GHSA agent should not use old/incorrect field names."""
        agent = GHSAAgent(db=mock_db)
        records = list(agent.transform_data([sample_ghsa_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]
        vuln_doc = vuln_docs[0]

        # Should NOT have these incorrect field names
        incorrect_fields = {
            "ghsa_id": "Should use vulnerability_id",
            "severity": "Should use cvss_v3_severity",
            "cvss_score": "Should use cvss_v3_score",
        }

        for field, reason in incorrect_fields.items():
            # Allow ghsa_id as additional field, but vulnerability_id must also exist
            if field == "ghsa_id":
                continue
            assert field not in vuln_doc, f"Agent uses '{field}': {reason}"

    def test_ghsa_agent_cvss_severity_normalized(self, mock_db, sample_ghsa_data):
        """GHSA agent should normalize CVSS severity to uppercase."""
        agent = GHSAAgent(db=mock_db)
        records = list(agent.transform_data([sample_ghsa_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]
        vuln_doc = vuln_docs[0]

        if "cvss_v3_severity" in vuln_doc and vuln_doc["cvss_v3_severity"]:
            severity = vuln_doc["cvss_v3_severity"]
            assert severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"], \
                f"cvss_v3_severity must be uppercase: got '{severity}'"


class TestNVDAgentSchemaCompliance:
    """Test NVD agent output validates against Vulnerability schema."""

    @pytest.fixture
    def sample_nvd_data(self):
        """Load sample NVD API response."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "nvd" / "sample_cve.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.fixture
    def mock_db(self):
        """Mock database for agent initialization."""
        db = Mock()
        db.collection = Mock(return_value=Mock())
        return db

    def test_nvd_agent_output_validates(self, mock_db, sample_nvd_data):
        """NVD agent output should validate against Vulnerability schema."""
        agent = NVDAgent(db=mock_db)
        records = list(agent.transform_data([sample_nvd_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]

        assert len(vuln_docs) > 0, "No vulnerability documents generated"

        vuln_doc = vuln_docs[0]

        # Validate required fields
        assert "vulnerability_id" in vuln_doc, "Missing required field: vulnerability_id"
        assert vuln_doc["vulnerability_id"] is not None, "vulnerability_id cannot be None"
        assert vuln_doc["vulnerability_id"] == sample_nvd_data["cve"]["id"], \
            "vulnerability_id should be cve_id for NVD source"

        assert "source" in vuln_doc, "Missing required field: source"
        assert vuln_doc["source"] == "nvd", "source should be 'nvd'"

    def test_nvd_agent_has_vulnerability_id(self, mock_db, sample_nvd_data):
        """NVD agent must include vulnerability_id field (TICKET-002 prevention)."""
        agent = NVDAgent(db=mock_db)
        records = list(agent.transform_data([sample_nvd_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]
        vuln_doc = vuln_docs[0]

        # This is the bug that caused TICKET-002
        assert "vulnerability_id" in vuln_doc, \
            "Missing vulnerability_id - would cause TICKET-002 bug"
        assert vuln_doc["vulnerability_id"] is not None, \
            "vulnerability_id cannot be None"
        assert vuln_doc["vulnerability_id"] == vuln_doc["cve_id"], \
            "vulnerability_id should equal cve_id for NVD"

    def test_nvd_agent_cve_id_matches_vulnerability_id(self, mock_db, sample_nvd_data):
        """For NVD agent, vulnerability_id should equal cve_id."""
        agent = NVDAgent(db=mock_db)
        records = list(agent.transform_data([sample_nvd_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]
        vuln_doc = vuln_docs[0]

        assert vuln_doc.get("vulnerability_id") == vuln_doc.get("cve_id"), \
            "For NVD source, vulnerability_id should equal cve_id"


class TestRequiredFieldsPresent:
    """Test all agents include required fields in their output."""

    REQUIRED_FIELDS = [
        "vulnerability_id",  # Always required for Vulnerability documents
    ]

    @pytest.fixture
    def mock_db(self):
        """Mock database for agent initialization."""
        db = Mock()
        db.collection = Mock(return_value=Mock())
        return db

    @pytest.fixture
    def sample_ghsa_data(self):
        """Load GHSA sample data."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "ghsa" / "sample_advisory.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.fixture
    def sample_nvd_data(self):
        """Load NVD sample data."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "nvd" / "sample_cve.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.mark.parametrize("agent_class,fixture_name", [
        (GHSAAgent, "sample_ghsa_data"),
        (NVDAgent, "sample_nvd_data"),
    ])
    def test_agent_has_required_fields(self, mock_db, agent_class, fixture_name, request):
        """All agents must include required fields."""
        sample_data = request.getfixturevalue(fixture_name)
        agent = agent_class(db=mock_db)
        records = list(agent.transform_data([sample_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]

        assert len(vuln_docs) > 0, f"{agent_class.__name__} generated no documents"

        vuln_doc = vuln_docs[0]

        for field in self.REQUIRED_FIELDS:
            assert field in vuln_doc, \
                f"{agent_class.__name__} missing required field: {field}"
            assert vuln_doc[field] is not None, \
                f"{agent_class.__name__} has null {field}"


class TestFieldNamingConventions:
    """Test agents use correct field names (not old/wrong names)."""

    # Fields that should NOT appear (old/incorrect names)
    INCORRECT_FIELD_NAMES = {
        "severity": "Use cvss_v3_severity instead",
        "cvss_score": "Use cvss_v3_score instead",
        "cvss_vector": "Use cvss_v3_vector instead",
        "updated": "Use modified or last_modified instead",
    }

    @pytest.fixture
    def mock_db(self):
        """Mock database for agent initialization."""
        db = Mock()
        db.collection = Mock(return_value=Mock())
        return db

    @pytest.fixture
    def sample_ghsa_data(self):
        """Load GHSA sample data."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "ghsa" / "sample_advisory.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.fixture
    def sample_nvd_data(self):
        """Load NVD sample data."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "nvd" / "sample_cve.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.mark.parametrize("agent_class,fixture_name", [
        (GHSAAgent, "sample_ghsa_data"),
        (NVDAgent, "sample_nvd_data"),
    ])
    def test_agent_uses_correct_field_names(self, mock_db, agent_class, fixture_name, request):
        """Agents should not use old/incorrect field names."""
        sample_data = request.getfixturevalue(fixture_name)
        agent = agent_class(db=mock_db)
        records = list(agent.transform_data([sample_data]))
        vuln_docs = [r for r in records if "_from" not in r and "_to" not in r]

        assert len(vuln_docs) > 0

        vuln_doc = vuln_docs[0]

        for incorrect_name, reason in self.INCORRECT_FIELD_NAMES.items():
            assert incorrect_name not in vuln_doc, \
                f"{agent_class.__name__} uses '{incorrect_name}': {reason}"
