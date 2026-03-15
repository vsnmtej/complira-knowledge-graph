"""
Unit tests for YAMLRegulatoryAgent (generic YAML-based regulatory framework agent).

Tests cover:
- Agent initialization with different framework keys
- YAML file loading and validation
- Schema validation (required fields, enums, consistency)
- Auto-detection of key generation methods
- Key generation for different frameworks
- Requirement type detection
- Framework document creation
- Normative requirement transformation
- Informative requirement transformation
- Classification requirement transformation
- Hierarchy parsing
- Evidence parsing
- Temporal metadata parsing
- Checkpoint support
- LSP compliance
- Multi-framework support (FDA_524B, IEC_62304)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import yaml
from datetime import date

from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent, YAMLSchemaValidationError
from complira_graph.models.regulatory import (
    RegulatoryFramework,
    NormativeRequirement,
    InformativeRequirement,
    ClassificationRequirement,
)


# ========== Fixtures ==========

@pytest.fixture
def mock_db():
    """Mock ArangoDB database."""
    db = Mock()
    db.has_collection = Mock(return_value=True)
    db.collection = Mock(return_value=Mock())
    return db


@pytest.fixture
def minimal_fda_yaml():
    """Minimal valid FDA 524B YAML for testing."""
    return {
        "framework": {
            "key": "FDA_524B",
            "name": "FDA Section 524B",
            "short_name": "FDA 524B",
            "jurisdiction": "US",
            "issuing_body": "FDA",
            "document_type": "guidance",
            "version": "Draft 2023",
            "source_url": "https://www.fda.gov/guidance",
            "source_format": "pdf"
        },
        "requirements": [
            {
                "requirement_id": "V.A.1",
                "title": "SBOM",
                "text": "Manufacturers shall maintain SBOM",
                "requirement_type": "procedural",
                "obligation_level": "shall"
            }
        ]
    }


@pytest.fixture
def minimal_iec_yaml():
    """Minimal valid IEC 62304 YAML for testing."""
    return {
        "framework": {
            "key": "IEC_62304",
            "name": "IEC 62304",
            "short_name": "IEC 62304",
            "jurisdiction": "international",
            "issuing_body": "IEC",
            "document_type": "standard",
            "version": "Edition 2.0",
            "source_url": "https://www.iec.ch/62304",
            "source_format": "pdf"
        },
        "requirements": [
            {
                "requirement_id": "5.1.1",
                "title": "Software Development Plan",
                "text": "Manufacturer shall define plan",
                "requirement_type": "procedural",
                "obligation_level": "shall"
            },
            {
                "requirement_id": "Class A",
                "title": "Safety Class A",
                "text": "No injury possible",
                "requirement_type": "classification",
                "obligation_level": "informative",
                "classification_level": "A",
                "risk_category": "low"
            }
        ]
    }


@pytest.fixture
def fda_yaml_with_evidence():
    """FDA YAML with evidence types."""
    return {
        "framework": {
            "key": "FDA_524B",
            "name": "FDA Section 524B",
            "short_name": "FDA 524B",
            "jurisdiction": "US",
            "issuing_body": "FDA",
            "document_type": "guidance",
            "version": "Draft 2023",
            "source_url": "https://www.fda.gov/guidance",
            "source_format": "pdf"
        },
        "requirements": [
            {
                "requirement_id": "V.A.1",
                "title": "SBOM",
                "text": "Manufacturers shall maintain SBOM",
                "requirement_type": "procedural",
                "obligation_level": "shall",
                "evidence_types": [
                    {
                        "type": "SBOM",
                        "format": "CycloneDX 1.6 | SPDX 2.3",
                        "required": True,
                        "scanner_tools": ["syft", "cdxgen"]
                    }
                ],
                "deadline": "2025-09-01"
            }
        ]
    }


# ========== Initialization Tests ==========

def test_agent_initialization_fda(mock_db):
    """Test agent initialization with FDA_524B framework."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    assert agent.framework_key == "FDA_524B"
    assert agent.agent_name == "YAMLRegulatoryAgent_FDA_524B"
    assert agent.yaml_path.name == "fda_524b.yaml"
    assert agent.supports_checkpointing is True
    assert agent.checkpoint_interval == 50


def test_agent_initialization_iec(mock_db):
    """Test agent initialization with IEC_62304 framework."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    assert agent.framework_key == "IEC_62304"
    assert agent.agent_name == "YAMLRegulatoryAgent_IEC_62304"
    assert agent.yaml_path.name == "iec_62304.yaml"


def test_agent_initialization_custom(mock_db):
    """Test agent initialization with custom framework."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="DORA")

    assert agent.framework_key == "DORA"
    assert agent.agent_name == "YAMLRegulatoryAgent_DORA"
    assert agent.yaml_path.name == "dora.yaml"


# ========== YAML Loading Tests ==========

def test_fetch_data_file_not_found(mock_db):
    """Test fetch_data raises FileNotFoundError when YAML doesn't exist."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="NONEXISTENT")

    with pytest.raises(FileNotFoundError, match="YAML file not found"):
        agent.fetch_data()


@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_fetch_data_empty_file(mock_exists, mock_open, mock_db, tmp_path):
    """Test fetch_data handles empty YAML file."""
    mock_open.return_value.__enter__.return_value.read.return_value = ""

    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    with patch.object(yaml, 'safe_load', return_value=None):
        result = agent.fetch_data()
        assert result == []


@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_fetch_data_invalid_yaml(mock_exists, mock_open, mock_db):
    """Test fetch_data handles invalid YAML syntax."""
    mock_open.return_value.__enter__.return_value = "invalid: yaml: syntax:"

    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    with patch.object(yaml, 'safe_load', side_effect=yaml.YAMLError("Invalid YAML")):
        with pytest.raises(yaml.YAMLError):
            agent.fetch_data()


@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_fetch_data_valid_yaml(mock_exists, mock_open, mock_db, minimal_fda_yaml):
    """Test fetch_data successfully loads valid YAML."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    with patch.object(yaml, 'safe_load', return_value=minimal_fda_yaml):
        result = agent.fetch_data()

        assert isinstance(result, list)
        assert len(result) == 2  # 1 framework + 1 requirement
        assert result[0]["_type"] == "framework"
        assert result[1]["_type"] == "requirement"


# ========== Schema Validation Tests ==========

def test_validate_schema_missing_framework(mock_db):
    """Test schema validation fails when framework section is missing."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    invalid_data = {"requirements": []}

    with pytest.raises(YAMLSchemaValidationError, match="Missing required top-level field: 'framework'"):
        agent._validate_schema(invalid_data)


def test_validate_schema_missing_requirements(mock_db):
    """Test schema validation fails when requirements section is missing."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    invalid_data = {
        "framework": {
            "key": "FDA_524B",
            "name": "FDA",
            "short_name": "FDA",
            "jurisdiction": "US",
            "issuing_body": "FDA",
            "document_type": "guidance",
            "version": "1.0",
            "source_url": "http://example.com",
            "source_format": "pdf"
        }
    }

    with pytest.raises(YAMLSchemaValidationError, match="Missing required top-level field: 'requirements'"):
        agent._validate_schema(invalid_data)


def test_validate_schema_missing_framework_field(mock_db):
    """Test schema validation fails when required framework field is missing."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    invalid_data = {
        "framework": {
            "key": "FDA_524B",
            # Missing name
            "short_name": "FDA",
            "jurisdiction": "US",
            "issuing_body": "FDA",
            "document_type": "guidance",
            "version": "1.0",
            "source_url": "http://example.com",
            "source_format": "pdf"
        },
        "requirements": []
    }

    with pytest.raises(YAMLSchemaValidationError, match="Missing required framework field: 'name'"):
        agent._validate_schema(invalid_data)


def test_validate_schema_invalid_jurisdiction(mock_db):
    """Test schema validation fails for invalid jurisdiction."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    invalid_data = {
        "framework": {
            "key": "FDA_524B",
            "name": "FDA",
            "short_name": "FDA",
            "jurisdiction": "INVALID",  # Invalid
            "issuing_body": "FDA",
            "document_type": "guidance",
            "version": "1.0",
            "source_url": "http://example.com",
            "source_format": "pdf"
        },
        "requirements": []
    }

    with pytest.raises(YAMLSchemaValidationError, match="Invalid jurisdiction"):
        agent._validate_schema(invalid_data)


def test_validate_schema_invalid_requirement_type(mock_db):
    """Test schema validation fails for invalid requirement_type."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    invalid_data = {
        "framework": {
            "key": "FDA_524B",
            "name": "FDA",
            "short_name": "FDA",
            "jurisdiction": "US",
            "issuing_body": "FDA",
            "document_type": "guidance",
            "version": "1.0",
            "source_url": "http://example.com",
            "source_format": "pdf"
        },
        "requirements": [
            {
                "requirement_id": "1",
                "title": "Test",
                "text": "Test",
                "requirement_type": "INVALID",  # Invalid
                "obligation_level": "shall"
            }
        ]
    }

    with pytest.raises(YAMLSchemaValidationError, match="Invalid requirement_type"):
        agent._validate_schema(invalid_data)


def test_validate_schema_classification_with_evidence(mock_db):
    """Test schema validation fails when classification has evidence."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    invalid_data = {
        "framework": {
            "key": "IEC_62304",
            "name": "IEC",
            "short_name": "IEC",
            "jurisdiction": "international",
            "issuing_body": "IEC",
            "document_type": "standard",
            "version": "1.0",
            "source_url": "http://example.com",
            "source_format": "pdf"
        },
        "requirements": [
            {
                "requirement_id": "Class A",
                "title": "Class A",
                "text": "Safety class",
                "requirement_type": "classification",
                "obligation_level": "informative",
                "evidence_types": [{"type": "SBOM"}]  # Invalid - classifications can't have evidence
            }
        ]
    }

    with pytest.raises(YAMLSchemaValidationError, match="Classification requirements cannot have evidence_types"):
        agent._validate_schema(invalid_data)


def test_validate_schema_valid(mock_db, minimal_fda_yaml):
    """Test schema validation passes for valid YAML."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    # Should not raise
    agent._validate_schema(minimal_fda_yaml)


# ========== Key Generation Tests ==========

def test_get_key_generator_method_fda(mock_db):
    """Test key generator method detection for FDA_524B."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    method = agent._get_key_generator_method()
    assert method is not None
    assert callable(method)


def test_get_key_generator_method_iec(mock_db):
    """Test key generator method detection for IEC_62304."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    method = agent._get_key_generator_method()
    assert method is not None
    assert callable(method)


def test_get_key_generator_method_unknown(mock_db):
    """Test key generator method returns None for unknown framework."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="UNKNOWN_FRAMEWORK")

    method = agent._get_key_generator_method()
    assert method is None


def test_parse_requirement_id_fda(mock_db):
    """Test requirement_id parsing for FDA 524B."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    # V.A.1
    result = agent._parse_requirement_id("V.A.1")
    assert result == {"section": "V", "subsection": "A", "requirement": "1"}

    # VI.B.2
    result = agent._parse_requirement_id("VI.B.2")
    assert result == {"section": "VI", "subsection": "B", "requirement": "2"}

    # V.C (no requirement number)
    result = agent._parse_requirement_id("V.C")
    assert result == {"section": "V", "subsection": "C", "requirement": None}


def test_parse_requirement_id_iec(mock_db):
    """Test requirement_id parsing for IEC 62304."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    # 5.1.1
    result = agent._parse_requirement_id("5.1.1")
    assert result == {"clause": "5", "subclause": "1", "item": "1"}

    # 5.1
    result = agent._parse_requirement_id("5.1")
    assert result == {"clause": "5", "subclause": "1", "item": None}

    # Class A
    result = agent._parse_requirement_id("Class A")
    assert result == {"clause": "Class A"}


def test_generate_key_fda(mock_db):
    """Test key generation for FDA 524B."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    req_data = {"requirement_id": "V.A.1"}
    key = agent._generate_key(req_data)

    assert key == "FDA_524B_V_A_1"


def test_generate_key_iec(mock_db):
    """Test key generation for IEC 62304."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    req_data = {"requirement_id": "5.1.1"}
    key = agent._generate_key(req_data)

    assert key == "IEC_62304_5_1_1"


def test_generate_key_with_explicit_key(mock_db):
    """Test that explicit key is used when provided in create methods."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    req_data = {
        "key": "CUSTOM_KEY",
        "requirement_id": "V.A.1",
        "title": "Test",
        "text": "Test text",
        "requirement_type": "procedural",
        "obligation_level": "shall"
    }

    # Test through create_normative_requirement which uses the key if provided
    requirement = agent._create_normative_requirement(req_data)

    assert requirement.identity.key == "CUSTOM_KEY"


# ========== Requirement Type Detection Tests ==========

def test_detect_requirement_type_normative(mock_db):
    """Test requirement type detection for normative requirements."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    assert agent._detect_requirement_type({"requirement_type": "essential"}) == "normative"
    assert agent._detect_requirement_type({"requirement_type": "procedural"}) == "normative"
    assert agent._detect_requirement_type({"requirement_type": "testing"}) == "normative"


def test_detect_requirement_type_classification(mock_db):
    """Test requirement type detection for classification."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    assert agent._detect_requirement_type({"requirement_type": "classification"}) == "classification"


def test_detect_requirement_type_informative(mock_db):
    """Test requirement type detection for informative."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    assert agent._detect_requirement_type({"requirement_type": "informative"}) == "informative"


# ========== Framework Creation Tests ==========

def test_create_framework(mock_db, minimal_fda_yaml):
    """Test framework document creation."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    framework = agent._create_framework(minimal_fda_yaml["framework"])

    assert isinstance(framework, RegulatoryFramework)
    assert framework.key == "FDA_524B"
    assert framework.name == "FDA Section 524B"
    assert framework.jurisdiction == "US"
    assert framework.document_type == "guidance"


def test_create_framework_with_dates(mock_db):
    """Test framework creation with date parsing."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    framework_data = {
        "key": "FDA_524B",
        "name": "FDA",
        "short_name": "FDA",
        "jurisdiction": "US",
        "issuing_body": "FDA",
        "document_type": "guidance",
        "version": "1.0",
        "source_url": "http://example.com",
        "source_format": "pdf",
        "publication_date": "2023-01-01",
        "effective_date": "2024-01-01"
    }

    framework = agent._create_framework(framework_data)

    assert framework.publication_date == date(2023, 1, 1)
    assert framework.effective_date == date(2024, 1, 1)


# ========== Normative Requirement Tests ==========

def test_create_normative_requirement(mock_db):
    """Test normative requirement creation."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    req_data = {
        "requirement_id": "V.A.1",
        "title": "SBOM",
        "text": "Manufacturers shall maintain SBOM",
        "requirement_type": "procedural",
        "obligation_level": "shall"
    }

    requirement = agent._create_normative_requirement(req_data)

    assert isinstance(requirement, NormativeRequirement)
    assert requirement.identity.requirement_id == "V.A.1"
    assert requirement.identity.framework == "FDA_524B"
    assert requirement.content.title == "SBOM"
    assert requirement.classification.requirement_type == "procedural"
    assert requirement.classification.obligation_level == "shall"


def test_create_normative_requirement_with_evidence(mock_db):
    """Test normative requirement with evidence types."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    req_data = {
        "requirement_id": "V.A.1",
        "title": "SBOM",
        "text": "Manufacturers shall maintain SBOM",
        "requirement_type": "procedural",
        "obligation_level": "shall",
        "evidence_types": [
            {
                "type": "SBOM",
                "format": "CycloneDX 1.6",
                "required": True,
                "scanner_tools": ["syft"]
            }
        ]
    }

    requirement = agent._create_normative_requirement(req_data)

    assert requirement.evidence is not None
    assert len(requirement.evidence.evidence_types) == 1
    assert requirement.evidence.evidence_types[0].type == "SBOM"
    assert requirement.evidence.evidence_types[0].format == "CycloneDX 1.6"


def test_create_normative_requirement_with_temporal(mock_db):
    """Test normative requirement with temporal metadata."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    req_data = {
        "requirement_id": "V.A.1",
        "title": "SBOM",
        "text": "Manufacturers shall maintain SBOM",
        "requirement_type": "procedural",
        "obligation_level": "shall",
        "deadline": "2025-09-01",
        "effective_date": "2024-01-01"
    }

    requirement = agent._create_normative_requirement(req_data)

    assert requirement.temporal is not None
    assert requirement.temporal.deadline == date(2025, 9, 1)
    assert requirement.temporal.effective_date == date(2024, 1, 1)


# ========== Informative Requirement Tests ==========

def test_create_informative_requirement(mock_db):
    """Test informative requirement creation."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    req_data = {
        "requirement_id": "Guidance 1",
        "title": "Guidance Note",
        "text": "This provides context...",
        "requirement_type": "informative",
        "obligation_level": "informative"
    }

    requirement = agent._create_informative_requirement(req_data)

    assert isinstance(requirement, InformativeRequirement)
    assert requirement.identity.requirement_id == "Guidance 1"
    assert requirement.obligation_level == "informative"
    assert requirement.content.title == "Guidance Note"


# ========== Classification Requirement Tests ==========

def test_create_classification_requirement(mock_db):
    """Test classification requirement creation."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    req_data = {
        "requirement_id": "Class A",
        "title": "Safety Class A",
        "text": "No injury possible",
        "requirement_type": "classification",
        "obligation_level": "informative",
        "classification_level": "A",
        "risk_category": "low"
    }

    requirement = agent._create_classification_requirement(req_data)

    assert isinstance(requirement, ClassificationRequirement)
    assert requirement.identity.requirement_id == "Class A"
    assert requirement.classification_level == "A"
    assert requirement.risk_category == "low"


# ========== Evidence Parsing Tests ==========

def test_parse_evidence_specification_empty(mock_db):
    """Test evidence parsing with empty list."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    result = agent._parse_evidence_specification([])

    assert result is None


def test_parse_evidence_specification_automated(mock_db):
    """Test evidence parsing with automated evidence."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    evidence_data = [
        {
            "type": "SBOM",
            "required": True,
            "scanner_tools": ["syft"],
            "manual_attestation": False
        }
    ]

    result = agent._parse_evidence_specification(evidence_data)

    assert result is not None
    assert result.testability == "automated"
    assert len(result.evidence_types) == 1


def test_parse_evidence_specification_manual(mock_db):
    """Test evidence parsing with manual evidence."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    evidence_data = [
        {
            "type": "threat_model",
            "required": True,
            "manual_attestation": True
        }
    ]

    result = agent._parse_evidence_specification(evidence_data)

    assert result is not None
    assert result.testability == "manual_only"


def test_parse_evidence_specification_mixed(mock_db):
    """Test evidence parsing with mixed automated and manual."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    evidence_data = [
        {
            "type": "SBOM",
            "manual_attestation": False
        },
        {
            "type": "threat_model",
            "manual_attestation": True
        }
    ]

    result = agent._parse_evidence_specification(evidence_data)

    assert result is not None
    assert result.testability == "semi_automated"


# ========== Transform Tests ==========

@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_transform_data(mock_exists, mock_open, mock_db, minimal_fda_yaml):
    """Test transform_data creates correct documents."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    with patch.object(yaml, 'safe_load', return_value=minimal_fda_yaml):
        raw_data = agent.fetch_data()
        documents = agent.transform_data(raw_data)

        assert len(documents) >= 2
        # Check framework document
        framework_docs = [d for d in documents if d.get("_collection") == "regulatory_frameworks"]
        assert len(framework_docs) == 1
        assert framework_docs[0]["_key"] == "FDA_524B"

        # Check requirement documents
        req_docs = [d for d in documents if d.get("_collection") == "regulatory_requirements"]
        assert len(req_docs) >= 1


@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_transform_data_multiple_requirement_types(mock_exists, mock_open, mock_db, minimal_iec_yaml):
    """Test transform_data handles multiple requirement types."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    with patch.object(yaml, 'safe_load', return_value=minimal_iec_yaml):
        raw_data = agent.fetch_data()
        documents = agent.transform_data(raw_data)

        req_docs = [d for d in documents if d.get("_collection") == "regulatory_requirements"]
        # Should have both normative and classification requirements
        assert len(req_docs) == 2

        # Check for both types
        requirement_types = [d.get("requirement_type") for d in req_docs]
        assert "procedural" in requirement_types
        assert "classification" in requirement_types


# ========== LSP Compliance Tests ==========

@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_fetch_data_returns_list(mock_exists, mock_open, mock_db, minimal_fda_yaml):
    """Test fetch_data returns List[Dict] for LSP compliance."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    with patch.object(yaml, 'safe_load', return_value=minimal_fda_yaml):
        result = agent.fetch_data()

        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)


# ========== Checkpoint Tests ==========

def test_checkpoint_support_enabled(mock_db):
    """Test that checkpoint support is enabled."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    assert agent.supports_checkpointing is True
    assert agent.checkpoint_interval == 50


# ========== Helper Method Tests ==========

def test_infer_collection_from_type(mock_db):
    """Test evidence type to collection mapping."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    assert agent._infer_collection_from_type("SBOM") == "sbom_artifacts"
    assert agent._infer_collection_from_type("SAST") == "sast_findings"
    assert agent._infer_collection_from_type("DAST") == "dast_findings"
    assert agent._infer_collection_from_type("threat_model") == "threat_models"
    assert agent._infer_collection_from_type("unknown_type") == "attestations"


def test_parse_date_valid(mock_db):
    """Test date parsing with valid ISO date."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    result = agent._parse_date("2025-09-01")
    assert result == date(2025, 9, 1)


def test_parse_date_invalid(mock_db):
    """Test date parsing with invalid date."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    result = agent._parse_date("invalid-date")
    assert result is None


def test_parse_date_none(mock_db):
    """Test date parsing with None."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    result = agent._parse_date(None)
    assert result is None


# ========== Integration Tests ==========

def test_primary_collection(mock_db):
    """Test _get_primary_collection returns correct collection."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    assert agent._get_primary_collection() == "regulatory_requirements"


@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_end_to_end_fda(mock_exists, mock_open, mock_db, minimal_fda_yaml):
    """Test end-to-end workflow for FDA_524B."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

    with patch.object(yaml, 'safe_load', return_value=minimal_fda_yaml):
        # Fetch
        raw_data = agent.fetch_data()
        assert len(raw_data) == 2

        # Transform
        documents = agent.transform_data(raw_data)
        assert len(documents) >= 2

        # Verify framework
        framework_doc = next(d for d in documents if d.get("_collection") == "regulatory_frameworks")
        assert framework_doc["_key"] == "FDA_524B"
        assert framework_doc["name"] == "FDA Section 524B"

        # Verify requirement
        req_doc = next(d for d in documents if d.get("_collection") == "regulatory_requirements")
        assert req_doc["framework"] == "FDA_524B"
        assert req_doc["requirement_type"] == "procedural"


@patch("builtins.open")
@patch("pathlib.Path.exists", return_value=True)
def test_end_to_end_iec(mock_exists, mock_open, mock_db, minimal_iec_yaml):
    """Test end-to-end workflow for IEC_62304."""
    agent = YAMLRegulatoryAgent(mock_db, framework_key="IEC_62304")

    with patch.object(yaml, 'safe_load', return_value=minimal_iec_yaml):
        # Fetch
        raw_data = agent.fetch_data()
        assert len(raw_data) == 3  # 1 framework + 2 requirements

        # Transform
        documents = agent.transform_data(raw_data)
        assert len(documents) >= 3

        # Verify classification requirement
        classification_docs = [d for d in documents if d.get("requirement_type") == "classification"]
        assert len(classification_docs) == 1
        assert classification_docs[0]["classification_level"] == "A"
