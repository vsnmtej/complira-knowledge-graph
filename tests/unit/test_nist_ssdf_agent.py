"""
Unit tests for NIST SSDF Agent (refactored with DRY/SOLID utilities).

Tests the NISTSSDFAgent ingestion functionality with mocked HTTP requests.

Run:
    pytest tests/unit/test_nist_ssdf_agent.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import date

from complira_graph.agents.nist_ssdf import NISTSSDFAgent
from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen


class TestNISTSSDFAgent:
    """Test suite for NIST SSDF agent."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock ArangoDB database."""
        db = MagicMock()

        # Mock collection methods
        mock_collection = MagicMock()
        mock_collection.import_bulk.return_value = {
            "created": 10,
            "updated": 0,
            "errors": 0
        }
        mock_collection.has.return_value = False

        db.collection.return_value = mock_collection
        db.has_collection.return_value = True

        return db

    @pytest.fixture
    def mock_ssdf_data(self):
        """Create mock SSDF JSON data."""
        return {
            "practices": [
                {
                    "practice_group": "PO",
                    "practice": "1",
                    "name": "Define Security Requirements",
                    "description": "Define and document security requirements for the software.",
                    "tasks": [
                        {
                            "task": "1",
                            "description": "Identify and document security requirements based on business needs."
                        },
                        {
                            "task": "2",
                            "description": "Generate SBOM for all software components."
                        },
                        {
                            "task": "3",
                            "description": "Perform static analysis using SAST tools."
                        }
                    ]
                },
                {
                    "practice_group": "PW",
                    "practice": "1",
                    "name": "Secure Coding Practices",
                    "description": "Follow secure coding practices during development.",
                    "tasks": [
                        {
                            "task": "1",
                            "description": "Use automated tools to check for common vulnerabilities."
                        }
                    ]
                }
            ]
        }

    @pytest.fixture
    def agent(self, mock_db):
        """Create a NISTSSDFAgent instance with mock database."""
        return NISTSSDFAgent(mock_db)

    def test_agent_initialization(self, agent):
        """Test that agent initializes correctly."""
        assert agent.agent_name == "NISTSSDFAgent"
        assert agent.supports_checkpointing is True
        assert agent.checkpoint_interval == 10
        assert agent._get_primary_collection() == "regulatory_requirements"

    def test_key_generation(self):
        """Test that key generation follows DRY principles."""
        # Practice keys
        assert KeyGen.nist_ssdf("PO", 1) == "NIST_SSDF_PO_1"
        assert KeyGen.nist_ssdf("PW", 1) == "NIST_SSDF_PW_1"
        assert KeyGen.nist_ssdf("RV", 2) == "NIST_SSDF_RV_2"

        # Task keys
        assert KeyGen.nist_ssdf("PO", 1, 1) == "NIST_SSDF_PO_1_1"
        assert KeyGen.nist_ssdf("PW", 1, 3) == "NIST_SSDF_PW_1_3"

    @patch('complira_graph.agents.nist_ssdf.requests.get')
    def test_fetch_data_success(self, mock_get, agent, mock_ssdf_data):
        """Test successful data fetch from GitHub."""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = mock_ssdf_data
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Fetch data
        result = agent.fetch_data()

        # Assertions
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["practice_group"] == "PO"
        assert result[1]["practice_group"] == "PW"

        # Verify URL was called
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert agent.SSDF_JSON_URL in str(call_args)

    @patch('complira_graph.agents.nist_ssdf.requests.get')
    def test_fetch_data_network_error(self, mock_get, agent):
        """Test fetch_data handles network errors gracefully."""
        # Mock network error
        import requests
        mock_get.side_effect = requests.RequestException("Network error")

        # Should raise exception
        with pytest.raises(requests.RequestException):
            agent.fetch_data()

    def test_transform_data_creates_correct_documents(self, agent, mock_ssdf_data):
        """Test that transform_data creates correct documents."""
        practices = mock_ssdf_data["practices"]
        documents = agent.transform_data(practices)

        # Should create:
        # 1 framework + 2 practices + 4 tasks + 4 edges = 11 documents
        assert len(documents) == 11

        # Check framework document
        framework_docs = [d for d in documents if d.get("_collection") == "regulatory_frameworks"]
        assert len(framework_docs) == 1
        framework = framework_docs[0]
        assert framework["_key"] == "NIST_SSDF"
        assert framework["name"] == "NIST Secure Software Development Framework"
        assert framework["short_name"] == "NIST SSDF"
        assert framework["jurisdiction"] == "US"
        assert framework["issuing_body"] == "NIST"
        assert framework["version"] == "v1.1"

        # Check practice documents
        practice_docs = [d for d in documents
                        if d.get("_collection") == "regulatory_requirements"
                        and d.get("depth") == 1]
        assert len(practice_docs) == 2

        # Check first practice
        po_practice = [p for p in practice_docs if p["_key"] == "NIST_SSDF_PO_1"][0]
        assert po_practice["requirement_id"] == "PO.1"
        assert po_practice["framework"] == "NIST_SSDF"
        assert po_practice["title"] == "Define Security Requirements"
        assert po_practice["requirement_type"] == "procedural"
        assert po_practice["obligation_level"] == "should"
        assert po_practice["depth"] == 1
        assert po_practice["children_count"] == 3

        # Check task documents
        task_docs = [d for d in documents
                    if d.get("_collection") == "regulatory_requirements"
                    and d.get("depth") == 2]
        assert len(task_docs) == 4

        # Check specific task
        po_1_1 = [t for t in task_docs if t["_key"] == "NIST_SSDF_PO_1_1"][0]
        assert po_1_1["requirement_id"] == "PO.1.1"
        assert po_1_1["framework"] == "NIST_SSDF"
        assert po_1_1["parent_key"] == "NIST_SSDF_PO_1"
        assert po_1_1["depth"] == 2

        # Check hierarchy edges
        edge_docs = [d for d in documents if d.get("_collection") == "requirement_hierarchy"]
        assert len(edge_docs) == 4

        # Check edge structure
        edge = edge_docs[0]
        assert "_from" in edge
        assert "_to" in edge
        assert edge["relationship"] == "contains"
        assert "regulatory_requirements/" in edge["_from"]
        assert "regulatory_requirements/" in edge["_to"]

    def test_infer_evidence_types_sbom(self, agent):
        """Test evidence inference for SBOM."""
        description = "Generate SBOM for all software components"
        evidence_spec = agent._infer_evidence_types(description)

        assert evidence_spec is not None
        assert len(evidence_spec.evidence_types) == 1
        assert evidence_spec.evidence_types[0].type == "SBOM"
        assert "CycloneDX" in evidence_spec.evidence_types[0].format
        assert evidence_spec.evidence_types[0].required is True
        assert evidence_spec.testability == "automated"

    def test_infer_evidence_types_sast(self, agent):
        """Test evidence inference for SAST."""
        description = "Perform static analysis using SAST tools"
        evidence_spec = agent._infer_evidence_types(description)

        assert evidence_spec is not None
        assert len(evidence_spec.evidence_types) == 1
        assert evidence_spec.evidence_types[0].type == "SAST"
        assert evidence_spec.evidence_types[0].required is True
        assert "semgrep" in evidence_spec.evidence_types[0].scanner_tools
        assert evidence_spec.testability == "automated"

    def test_infer_evidence_types_multiple(self, agent):
        """Test evidence inference for multiple evidence types."""
        description = "Generate SBOM and perform static analysis with SAST tools"
        evidence_spec = agent._infer_evidence_types(description)

        assert evidence_spec is not None
        assert len(evidence_spec.evidence_types) == 2

        types = [ev.type for ev in evidence_spec.evidence_types]
        assert "SBOM" in types
        assert "SAST" in types
        assert evidence_spec.testability == "automated"

    def test_infer_evidence_types_threat_model(self, agent):
        """Test evidence inference for threat modeling."""
        description = "Create threat model using STRIDE methodology"
        evidence_spec = agent._infer_evidence_types(description)

        assert evidence_spec is not None
        assert len(evidence_spec.evidence_types) == 1
        assert evidence_spec.evidence_types[0].type == "threat_model"
        assert evidence_spec.evidence_types[0].manual_attestation is True
        assert evidence_spec.testability == "manual_only"

    def test_infer_evidence_types_mixed_manual_automated(self, agent):
        """Test evidence inference with mixed manual and automated evidence."""
        description = "Generate SBOM and create threat model"
        evidence_spec = agent._infer_evidence_types(description)

        assert evidence_spec is not None
        assert len(evidence_spec.evidence_types) == 2
        assert evidence_spec.testability == "semi_automated"

    def test_infer_evidence_types_no_evidence(self, agent):
        """Test evidence inference when no evidence keywords found."""
        description = "Review security documentation"
        evidence_spec = agent._infer_evidence_types(description)

        assert evidence_spec is None

    def test_infer_evidence_types_empty_description(self, agent):
        """Test evidence inference with empty description."""
        evidence_spec = agent._infer_evidence_types("")
        assert evidence_spec is None

        evidence_spec = agent._infer_evidence_types(None)
        assert evidence_spec is None

    def test_checkpoint_support(self, agent):
        """Test that agent supports checkpointing."""
        assert agent.supports_checkpointing is True
        assert agent.checkpoint_interval == 10

    @patch('complira_graph.agents.nist_ssdf.requests.get')
    def test_checkpoint_resume(self, mock_get, agent, mock_ssdf_data):
        """Test that agent can resume from checkpoint."""
        # Mock checkpoint
        agent._load_checkpoint = Mock(return_value={
            "processed_practices": 1,
            "total_practices": 2
        })

        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = mock_ssdf_data
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Fetch should start from checkpoint
        result = agent.fetch_data()

        # Should skip first practice and return only second one
        assert len(result) == 1
        assert result[0]["practice_group"] == "PW"

    def test_provenance_metadata(self, agent, mock_ssdf_data):
        """Test that provenance metadata is correctly set."""
        practices = mock_ssdf_data["practices"]
        documents = agent.transform_data(practices)

        # Check that requirements have provenance
        req_docs = [d for d in documents if d.get("_collection") == "regulatory_requirements"]

        for doc in req_docs:
            assert doc["source"] == "oscal_import"
            assert doc["confidence"] == 1.0
            assert doc["curator"] == "NISTSSDFAgent"
            assert doc["version"] == "v1.1"

    def test_requirement_classification(self, agent, mock_ssdf_data):
        """Test that requirements are classified correctly."""
        practices = mock_ssdf_data["practices"]
        documents = agent.transform_data(practices)

        req_docs = [d for d in documents if d.get("_collection") == "regulatory_requirements"]

        for doc in req_docs:
            assert doc["requirement_type"] == "procedural"
            assert doc["obligation_level"] == "should"
            assert "manufacturer" in doc["applies_to"]
            assert "developer" in doc["applies_to"]
            assert "software" in doc["product_scope"]

    def test_lsp_compliance_return_type(self, mock_db, mock_ssdf_data):
        """Test that fetch_data returns List[Dict] for LSP compliance."""
        agent = NISTSSDFAgent(mock_db)

        with patch('complira_graph.agents.nist_ssdf.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_ssdf_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            result = agent.fetch_data()

            # Must return list, not dict (LSP compliance)
            assert isinstance(result, list)
            assert not isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
