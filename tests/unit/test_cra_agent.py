"""
Unit tests for CRA (EU Cyber Resilience Act) agent.

Tests cover:
- Agent initialization
- Key generation for different CRA structures (annex, article, recital)
- Data fetching from YAML
- Data transformation to graph documents
- Evidence inference for essential requirements
- Temporal metadata (deadlines)
- Checkpoint support
- Requirement type classification (essential, procedural, informative)
- LSP compliance (return type)
"""

import pytest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml

from complira_graph.agents.cra import CRAAgent
from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen
from complira_graph.models.regulatory import (
    RegulatoryFramework,
    NormativeRequirement,
    InformativeRequirement,
)


@pytest.fixture
def mock_db():
    """Fixture for mock database instance."""
    return Mock()


@pytest.fixture
def cra_agent(mock_db):
    """Fixture for CRA agent with mock database."""
    return CRAAgent(db=mock_db)


class TestCRAAgentInitialization:
    """Test CRA agent initialization and configuration."""

    def test_agent_initialization(self):
        """Test that CRA agent initializes correctly."""
        mock_db = Mock()
        agent = CRAAgent(db=mock_db)

        assert agent is not None
        assert agent.agent_name == "CRAAgent"
        assert agent.supports_checkpointing is True
        assert agent.checkpoint_interval == 50
        assert agent._get_primary_collection() == "regulatory_requirements"

    def test_yaml_path_exists(self):
        """Test that CRA YAML path is configured correctly."""
        mock_db = Mock()
        agent = CRAAgent(db=mock_db)

        assert hasattr(agent, "CRA_YAML_PATH")
        assert isinstance(agent.CRA_YAML_PATH, Path)
        assert str(agent.CRA_YAML_PATH).endswith("data/regulations/cra.yaml")


class TestKeyGeneration:
    """Test CRA key generation for different structures."""

    def test_annex_section_key(self):
        """Test key generation for Annex + Section."""
        key = KeyGen.cra(annex="I", section=1)
        assert key == "CRA_I_1"

    def test_annex_section_subpara_key(self):
        """Test key generation for Annex + Section + Subparagraph."""
        key = KeyGen.cra(annex="I", section=1, subpara="a")
        assert key == "CRA_I_1_a"

    def test_article_paragraph_key(self):
        """Test key generation for Article + Paragraph."""
        key = KeyGen.cra(article=13, paragraph=1)
        assert key == "CRA_13_1"

    def test_article_paragraph_subpara_key(self):
        """Test key generation for Article + Paragraph + Subparagraph."""
        key = KeyGen.cra(article=14, paragraph=2, subpara="b")
        assert key == "CRA_14_2_b"

    def test_recital_key(self):
        """Test key generation for Recital."""
        key = KeyGen.generate("CRA", "RECITAL", 1)
        assert key == "CRA_RECITAL_1"

    def test_key_validation(self):
        """Test that generated CRA keys are valid."""
        key = KeyGen.cra(annex="I", section=1, subpara="a")
        assert KeyGen.validate_key(key) is True

    def test_framework_extraction(self):
        """Test extracting framework from CRA key."""
        key = KeyGen.cra(annex="I", section=1)
        framework = KeyGen.extract_framework(key)
        assert framework == "CRA"


class TestDataFetching:
    """Test CRA data fetching from YAML."""

    @patch("builtins.open", create=True)
    @patch("yaml.safe_load")
    def test_fetch_data_returns_list(self, mock_yaml_load, mock_open):
        """Test that fetch_data returns List[Dict] (LSP compliance)."""
        # Mock YAML data
        mock_yaml_load.return_value = {
            "framework": {"key": "CRA", "name": "Cyber Resilience Act"},
            "annex_i_requirements": [
                {"annex": "I", "section": 1, "title": "Security by design"}
            ],
            "annex_ii_requirements": [],
            "article_requirements": [],
            "recitals": []
        }

        mock_db = Mock()
        agent = CRAAgent(db=mock_db)

        # Mock Path.exists()
        with patch.object(Path, "exists", return_value=True):
            result = agent.fetch_data()

        # LSP compliance: must return List[Dict]
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(item, dict) for item in result)

    @patch("builtins.open", create=True)
    @patch("yaml.safe_load")
    def test_fetch_data_combines_all_sections(self, mock_yaml_load, mock_open):
        """Test that fetch_data combines all YAML sections."""
        mock_yaml_load.return_value = {
            "framework": {"key": "CRA"},
            "annex_i_requirements": [{"annex": "I", "section": 1}],
            "annex_ii_requirements": [{"annex": "II", "section": 1}],
            "article_requirements": [{"article": 13, "paragraph": 1}],
            "recitals": [{"recital": 1}]
        }

        agent = CRAAgent(db=Mock())

        with patch.object(Path, "exists", return_value=True):
            result = agent.fetch_data()

        # Should have framework + 4 requirements
        assert len(result) == 5

        # Check types are tagged correctly
        types = [item.get("_type") for item in result]
        assert "framework" in types
        assert "annex_i" in types
        assert "annex_ii" in types
        assert "article" in types
        assert "recital" in types

    def test_fetch_data_file_not_found(self):
        """Test fetch_data raises error when YAML file not found."""
        agent = CRAAgent(db=Mock())

        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="CRA YAML file not found"):
                agent.fetch_data()

    @patch("builtins.open", create=True)
    @patch("yaml.safe_load")
    def test_fetch_data_empty_yaml(self, mock_yaml_load, mock_open):
        """Test fetch_data handles empty YAML gracefully."""
        mock_yaml_load.return_value = None

        agent = CRAAgent(db=Mock())

        with patch.object(Path, "exists", return_value=True):
            result = agent.fetch_data()

        assert result == []


class TestDataTransformation:
    """Test CRA data transformation to graph documents."""

    def test_transform_creates_framework_document(self):
        """Test that transform creates RegulatoryFramework document."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "framework",
                "key": "CRA",
                "name": "Cyber Resilience Act",
                "short_name": "CRA",
                "version": "Regulation (EU) 2024/2847",
                "jurisdiction": "EU",
                "issuing_body": "European Parliament and Council",
                "publication_date": "2024-12-10",
                "effective_date": "2024-12-10",
                "enforcement_date": "2027-12-11",
                "source_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "source_format": "yaml",
                "machine_readable": True,
                "status": "in_force",
                "ingestion_method": "yaml_config"
            }
        ]

        documents = agent.transform_data(raw_data)

        assert len(documents) >= 1

        # Find framework document
        framework_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_frameworks"),
            None
        )

        assert framework_doc is not None
        assert framework_doc["_key"] == "CRA"
        assert framework_doc["name"] == "Cyber Resilience Act"
        assert framework_doc["jurisdiction"] == "EU"
        assert framework_doc["document_type"] == "regulation"

    def test_transform_creates_annex_i_requirement(self):
        """Test that transform creates NormativeRequirement for Annex I."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 1,
                "title": "Security by design",
                "text": "Products shall be secure by default",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "applies_to": ["manufacturer"],
                "product_scope": ["products_with_digital_elements"],
                "deadline": "2027-12-11",
                "transition_period": "36 months"
            }
        ]

        documents = agent.transform_data(raw_data)

        assert len(documents) >= 1

        # Find requirement document
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc is not None
        assert req_doc["_key"] == "CRA_I_1"
        assert req_doc["framework"] == "CRA"
        assert req_doc["requirement_type"] == "essential"
        assert req_doc["obligation_level"] == "shall"
        assert req_doc["title"] == "Security by design"

    def test_transform_creates_article_requirement(self):
        """Test that transform creates NormativeRequirement for Article."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "article",
                "article": 13,
                "paragraph": 1,
                "title": "Vulnerability handling",
                "text": "Manufacturers shall handle vulnerabilities",
                "requirement_type": "procedural",
                "obligation_level": "shall",
                "applies_to": ["manufacturer"],
                "deadline": "2027-12-11"
            }
        ]

        documents = agent.transform_data(raw_data)

        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc is not None
        assert req_doc["_key"] == "CRA_13_1"
        assert req_doc["framework"] == "CRA"
        assert req_doc["requirement_type"] == "procedural"
        assert req_doc["obligation_level"] == "shall"

    def test_transform_creates_recital_informative(self):
        """Test that transform creates InformativeRequirement for Recital."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "recital",
                "recital": 1,
                "title": "Digital transformation",
                "text": "Digital transformation brings benefits and risks",
                "requirement_type": "informative",
                "applies_to": ["manufacturer"]
            }
        ]

        documents = agent.transform_data(raw_data)

        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc is not None
        assert req_doc["_key"] == "CRA_RECITAL_1"
        assert req_doc["framework"] == "CRA"
        assert req_doc["requirement_type"] == "informative"
        assert req_doc["obligation_level"] == "informative"


class TestEvidenceInference:
    """Test evidence type inference for CRA requirements."""

    def test_evidence_types_parsed_from_yaml(self):
        """Test that evidence types are correctly parsed from YAML."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 1,
                "title": "Security by design",
                "text": "Security requirements",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "evidence_types": [
                    {
                        "type": "SAST",
                        "required": True,
                        "description": "Static analysis",
                        "scanner_tools": ["semgrep", "bandit"],
                        "manual_attestation": False
                    },
                    {
                        "type": "threat_model",
                        "required": True,
                        "description": "Threat modeling",
                        "manual_attestation": True
                    }
                ]
            }
        ]

        documents = agent.transform_data(raw_data)

        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc is not None
        assert "evidence_types" in req_doc
        assert len(req_doc["evidence_types"]) == 2

        # Check SAST evidence
        sast_ev = next((ev for ev in req_doc["evidence_types"] if ev["type"] == "SAST"), None)
        assert sast_ev is not None
        assert sast_ev["required"] is True
        assert "semgrep" in sast_ev["scanner_tools"]

        # Check threat model evidence
        threat_ev = next((ev for ev in req_doc["evidence_types"] if ev["type"] == "threat_model"), None)
        assert threat_ev is not None
        assert threat_ev["manual_attestation"] is True

    def test_testability_inference(self):
        """Test that testability is correctly inferred from evidence types."""
        agent = CRAAgent(db=Mock())

        # Semi-automated (mix of manual and automated)
        raw_data_semi = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 1,
                "title": "Test",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "evidence_types": [
                    {"type": "SAST", "required": True, "manual_attestation": False},
                    {"type": "threat_model", "required": True, "manual_attestation": True}
                ]
            }
        ]

        documents = agent.transform_data(raw_data_semi)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )
        assert req_doc["testability"] == "semi_automated"

        # Automated only
        raw_data_auto = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 2,
                "title": "Test",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "evidence_types": [
                    {"type": "SAST", "required": True, "manual_attestation": False}
                ]
            }
        ]

        documents = agent.transform_data(raw_data_auto)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements" and doc.get("_key") == "CRA_I_2"),
            None
        )
        assert req_doc["testability"] == "automated"

        # Manual only
        raw_data_manual = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 3,
                "title": "Test",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "evidence_types": [
                    {"type": "threat_model", "required": True, "manual_attestation": True}
                ]
            }
        ]

        documents = agent.transform_data(raw_data_manual)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements" and doc.get("_key") == "CRA_I_3"),
            None
        )
        assert req_doc["testability"] == "manual_only"


class TestTemporalMetadata:
    """Test temporal metadata (deadlines) for CRA requirements."""

    def test_deadline_parsing(self):
        """Test that deadline dates are correctly parsed."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 1,
                "title": "Test",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "deadline": "2027-12-11",
                "transition_period": "36 months from entry into force"
            }
        ]

        documents = agent.transform_data(raw_data)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc is not None
        assert "deadline" in req_doc
        # Deadline is stored as date object, convert to string for comparison
        assert str(req_doc["deadline"]) == "2027-12-11" or req_doc["deadline"] == date(2027, 12, 11)
        assert req_doc["transition_period"] == "36 months from entry into force"

    def test_staggered_deadlines(self):
        """Test that different CRA requirements have correct staggered deadlines."""
        agent = CRAAgent(db=Mock())

        # Technical requirement: 36 months
        raw_data_tech = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 1,
                "title": "Security",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall",
                "deadline": "2027-12-11",
                "transition_period": "36 months"
            }
        ]

        # Reporting requirement: 21 months
        raw_data_report = [
            {
                "_type": "article",
                "article": 13,
                "paragraph": 5,
                "title": "Reporting",
                "text": "Test",
                "requirement_type": "reporting",
                "obligation_level": "shall",
                "deadline": "2026-09-11",
                "transition_period": "21 months"
            }
        ]

        docs_tech = agent.transform_data(raw_data_tech)
        req_tech = next(
            (doc for doc in docs_tech if doc.get("_collection") == "regulatory_requirements"),
            None
        )
        # Deadline is stored as date object, convert to string for comparison
        assert str(req_tech["deadline"]) == "2027-12-11" or req_tech["deadline"] == date(2027, 12, 11)

        docs_report = agent.transform_data(raw_data_report)
        req_report = next(
            (doc for doc in docs_report if doc.get("_collection") == "regulatory_requirements"),
            None
        )
        # Deadline is stored as date object, convert to string for comparison
        assert str(req_report["deadline"]) == "2026-09-11" or req_report["deadline"] == date(2026, 9, 11)


class TestCheckpointSupport:
    """Test checkpoint support for resume functionality."""

    def test_checkpoint_support_enabled(self):
        """Test that checkpoint support is enabled."""
        agent = CRAAgent(db=Mock())
        assert agent.supports_checkpointing is True
        assert agent.checkpoint_interval == 50

    @patch.object(CRAAgent, "_load_checkpoint")
    @patch.object(CRAAgent, "_save_checkpoint")
    @patch("builtins.open", create=True)
    @patch("yaml.safe_load")
    def test_checkpoint_saved_during_transform(
        self,
        mock_yaml_load,
        mock_open,
        mock_save_checkpoint,
        mock_load_checkpoint
    ):
        """Test that checkpoint is saved during transformation."""
        mock_load_checkpoint.return_value = None

        agent = CRAAgent(db=Mock())

        # Create 51 requirements to trigger checkpoint
        raw_data = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": i,
                "title": f"Req {i}",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall"
            }
            for i in range(1, 52)
        ]

        agent.transform_data(raw_data)

        # Should save checkpoint at least once (at 50 requirements)
        assert mock_save_checkpoint.called

    @patch.object(CRAAgent, "_load_checkpoint")
    @patch("builtins.open", create=True)
    @patch("yaml.safe_load")
    def test_checkpoint_resume(self, mock_yaml_load, mock_open, mock_load_checkpoint):
        """Test that agent can resume from checkpoint."""
        # Mock checkpoint with 10 processed requirements
        mock_load_checkpoint.return_value = {
            "processed_requirements": 10,
            "total_requirements": 20
        }

        mock_yaml_load.return_value = {
            "framework": {"key": "CRA"},
            "annex_i_requirements": [{"annex": "I", "section": i} for i in range(1, 21)],
            "annex_ii_requirements": [],
            "article_requirements": [],
            "recitals": []
        }

        agent = CRAAgent(db=Mock())

        with patch.object(Path, "exists", return_value=True):
            result = agent.fetch_data()

        # Should skip first 10 requirements (already processed)
        # Framework (1) + 20 requirements = 21 total
        # After checkpoint: 21 - 10 = 11 remaining
        assert len(result) == 11


class TestRequirementClassification:
    """Test requirement type classification."""

    def test_essential_requirement_classification(self):
        """Test that Annex I requirements are classified as essential."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "annex_i",
                "annex": "I",
                "section": 1,
                "title": "Security",
                "text": "Test",
                "requirement_type": "essential",
                "obligation_level": "shall"
            }
        ]

        documents = agent.transform_data(raw_data)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc["requirement_type"] == "essential"
        assert req_doc["obligation_level"] == "shall"

    def test_procedural_requirement_classification(self):
        """Test that Article requirements are classified as procedural."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "article",
                "article": 13,
                "paragraph": 1,
                "title": "Vulnerability handling",
                "text": "Test",
                "requirement_type": "procedural",
                "obligation_level": "shall"
            }
        ]

        documents = agent.transform_data(raw_data)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc["requirement_type"] == "procedural"
        assert req_doc["obligation_level"] == "shall"

    def test_informative_requirement_classification(self):
        """Test that Recitals are classified as informative."""
        agent = CRAAgent(db=Mock())

        raw_data = [
            {
                "_type": "recital",
                "recital": 1,
                "title": "Context",
                "text": "Test",
                "requirement_type": "informative"
            }
        ]

        documents = agent.transform_data(raw_data)
        req_doc = next(
            (doc for doc in documents if doc.get("_collection") == "regulatory_requirements"),
            None
        )

        assert req_doc["requirement_type"] == "informative"
        assert req_doc["obligation_level"] == "informative"


class TestCollectionInference:
    """Test collection name inference from evidence types."""

    def test_infer_collection_from_sbom(self):
        """Test collection inference for SBOM evidence."""
        agent = CRAAgent(db=Mock())
        collection = agent._infer_collection_from_type("SBOM")
        assert collection == "sbom_artifacts"

    def test_infer_collection_from_sast(self):
        """Test collection inference for SAST evidence."""
        agent = CRAAgent(db=Mock())
        collection = agent._infer_collection_from_type("SAST")
        assert collection == "sast_findings"

    def test_infer_collection_from_dast(self):
        """Test collection inference for DAST evidence."""
        agent = CRAAgent(db=Mock())
        collection = agent._infer_collection_from_type("DAST")
        assert collection == "dast_findings"

    def test_infer_collection_from_threat_model(self):
        """Test collection inference for threat model evidence."""
        agent = CRAAgent(db=Mock())
        collection = agent._infer_collection_from_type("threat_model")
        assert collection == "threat_models"

    def test_infer_collection_default(self):
        """Test collection inference for unknown evidence types."""
        agent = CRAAgent(db=Mock())
        collection = agent._infer_collection_from_type("unknown_type")
        assert collection == "attestations"


class TestDateParsing:
    """Test date parsing functionality."""

    def test_parse_valid_date(self):
        """Test parsing valid ISO date string."""
        agent = CRAAgent(db=Mock())
        parsed = agent._parse_date("2027-12-11")
        assert parsed == date(2027, 12, 11)

    def test_parse_none_date(self):
        """Test parsing None returns None."""
        agent = CRAAgent(db=Mock())
        parsed = agent._parse_date(None)
        assert parsed is None

    def test_parse_invalid_date(self):
        """Test parsing invalid date returns None."""
        agent = CRAAgent(db=Mock())
        parsed = agent._parse_date("invalid-date")
        assert parsed is None
