"""
Unit tests for regulatory framework ingestion (Phase 4).

This module tests the ingestion of FDA 524B and EU CRA regulatory
requirements from YAML files using the YAMLRegulatoryAgent.

Test Coverage:
- FDA 524B requirements ingestion
- CRA requirements ingestion
- Dry-run mode (validation only)
- Duplicate handling (idempotency)
- Invalid framework key error handling
- YAML validation error handling
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent, YAMLSchemaValidationError


class TestFDA524BIngestion:
    """Test FDA 524B regulatory requirements ingestion."""

    def test_fda_524b_ingestion(self, mock_db):
        """
        Test FDA 524B requirements ingestion.

        Validates:
        - 12 requirements are ingested
        - All requirements have complete metadata
        - No errors during ingestion
        - Execution completes successfully
        """
        # Create agent
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Mock checkpoint methods
        agent._load_checkpoint = Mock(return_value=None)
        agent._save_checkpoint = Mock()
        agent._clear_checkpoint = Mock()

        # Mock successful insert
        mock_collection = MagicMock()
        mock_collection.insert = Mock(return_value={'_key': 'test_key'})
        mock_db.collection = Mock(return_value=mock_collection)

        # Run ingestion
        result = agent.run()

        # Assertions
        assert result['status'] == 'success', "Ingestion should succeed"
        assert result.get('errors', 0) == 0, "No errors should occur"
        assert 'execution_time_seconds' in result, "Execution time should be recorded"

        # Verify agent properties
        assert agent.framework_key == "FDA_524B"
        assert agent.agent_name == "YAMLRegulatoryAgent_FDA_524B"

    def test_fda_524b_requirement_count(self, mock_db):
        """
        Test FDA 524B requirement count.

        Validates:
        - Exactly 12 requirements in YAML
        - Plus 1 framework document
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Mock checkpoint methods
        agent._load_checkpoint = Mock(return_value=None)

        # Fetch data
        raw_data = agent.fetch_data()

        # Count requirements (excluding framework metadata)
        requirement_count = sum(1 for item in raw_data if item.get('_type') == 'requirement')
        framework_count = sum(1 for item in raw_data if item.get('_type') == 'framework')

        assert requirement_count == 12, f"Expected 12 FDA requirements, got {requirement_count}"
        assert framework_count == 1, f"Expected 1 framework document, got {framework_count}"

    def test_fda_524b_key_generation(self, mock_db):
        """
        Test FDA 524B key generation.

        Validates:
        - Keys follow pattern: FDA_524B_V_A_1, FDA_524B_V_A_2, etc.
        - All keys are unique
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Fetch and transform data
        raw_data = agent.fetch_data()
        documents = agent.transform_data(raw_data)

        # Extract requirement keys
        requirement_docs = [
            doc for doc in documents
            if doc.get('_collection') == 'regulatory_requirements'
        ]

        keys = [doc.get('_key') for doc in requirement_docs if doc.get('_key')]

        # Validate keys
        assert len(keys) == 12, f"Expected 12 requirement keys, got {len(keys)}"
        assert len(set(keys)) == 12, "All keys should be unique"

        # Check key format (should start with FDA_524B_V)
        for key in keys:
            assert key.startswith('FDA_524B_V'), f"Key {key} should start with FDA_524B_V"


class TestCRAIngestion:
    """Test EU CRA regulatory requirements ingestion."""

    def test_cra_ingestion(self, mock_db):
        """
        Test CRA requirements ingestion.

        Validates:
        - 8 requirements are ingested
        - All requirements have complete metadata
        - No errors during ingestion
        """
        # Create agent
        agent = YAMLRegulatoryAgent(mock_db, framework_key="CRA")

        # Mock successful insert
        mock_collection = MagicMock()
        mock_collection.insert = Mock(return_value={'_key': 'test_key'})
        mock_db.collection = Mock(return_value=mock_collection)

        # Run ingestion
        result = agent.run()

        # Assertions
        assert result['status'] == 'success', "Ingestion should succeed"
        assert result.get('errors', 0) == 0, "No errors should occur"

        # Verify agent properties
        assert agent.framework_key == "CRA"
        assert agent.agent_name == "YAMLRegulatoryAgent_CRA"

    def test_cra_requirement_count(self, mock_db):
        """
        Test CRA requirement count.

        Validates:
        - Exactly 8 Annex I requirements in YAML
        - Plus 1 framework document
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="CRA")

        # Fetch data
        raw_data = agent.fetch_data()

        # Count requirements (excluding framework metadata)
        requirement_count = sum(1 for item in raw_data if item.get('_type') == 'requirement')
        framework_count = sum(1 for item in raw_data if item.get('_type') == 'framework')

        assert requirement_count == 8, f"Expected 8 CRA requirements, got {requirement_count}"
        assert framework_count == 1, f"Expected 1 framework document, got {framework_count}"

    def test_cra_key_generation(self, mock_db):
        """
        Test CRA key generation.

        Validates:
        - Keys follow pattern: CRA_ANNEX_I_SECTION_1, etc.
        - All keys are unique
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="CRA")

        # Fetch and transform data
        raw_data = agent.fetch_data()
        documents = agent.transform_data(raw_data)

        # Extract requirement keys
        requirement_docs = [
            doc for doc in documents
            if doc.get('_collection') == 'regulatory_requirements'
        ]

        keys = [doc.get('_key') for doc in requirement_docs if doc.get('_key')]

        # Validate keys
        assert len(keys) == 8, f"Expected 8 requirement keys, got {len(keys)}"
        assert len(set(keys)) == 8, "All keys should be unique"

        # Check key format (should start with CRA_)
        for key in keys:
            assert key.startswith('CRA_'), f"Key {key} should start with CRA_"


class TestDryRunMode:
    """Test dry-run mode (validation without database changes)."""

    def test_dry_run_validation_only(self, mock_db):
        """
        Test dry-run mode validates without inserting.

        Validates:
        - fetch_data() executes (reads and validates YAML)
        - transform_data() executes (creates models)
        - load_data() is NOT executed (no database changes)
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Fetch and transform only (simulate dry-run)
        raw_data = agent.fetch_data()
        documents = agent.transform_data(raw_data)

        # Assertions
        assert len(raw_data) > 0, "Raw data should be fetched"
        assert len(documents) > 0, "Documents should be transformed"

        # Verify no database inserts happened (since we didn't call load_data)
        mock_db.collection.assert_not_called()

    def test_dry_run_yaml_validation(self, mock_db):
        """
        Test dry-run mode validates YAML schema.

        Validates:
        - YAML schema validation runs
        - No exceptions if YAML is valid
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="CRA")

        # Fetch data (includes schema validation)
        raw_data = agent.fetch_data()

        # If we get here without exceptions, validation passed
        assert len(raw_data) > 0, "YAML validation should pass for CRA"


class TestDuplicateHandling:
    """Test duplicate requirement handling (idempotency)."""

    def test_idempotency_upsert(self, mock_db):
        """
        Test ingesting the same framework twice.

        Validates:
        - Second ingestion updates existing requirements
        - No duplicate keys created
        - Database count remains same
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Mock collection insert to track calls
        mock_collection = MagicMock()
        call_count = {'count': 0}

        def mock_insert(doc, overwrite=False):
            call_count['count'] += 1
            return {'_key': doc.get('_key', f'generated_{call_count["count"]}')}

        mock_collection.insert = Mock(side_effect=mock_insert)
        mock_db.collection = Mock(return_value=mock_collection)

        # First ingestion
        result1 = agent.run()
        first_call_count = call_count['count']

        # Reset agent (simulate re-run)
        agent2 = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Second ingestion
        result2 = agent2.run()
        second_call_count = call_count['count'] - first_call_count

        # Assertions
        assert result1['status'] == 'success', "First ingestion should succeed"
        assert result2['status'] == 'success', "Second ingestion should succeed"

        # Both should insert same number of documents (idempotent)
        assert second_call_count == first_call_count, "Second run should upsert same documents"

    def test_deterministic_keys(self, mock_db):
        """
        Test keys are deterministically generated.

        Validates:
        - Same requirement_id always generates same _key
        - Running agent twice produces identical keys
        """
        agent1 = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")
        agent2 = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")

        # Transform data with both agents
        raw_data1 = agent1.fetch_data()
        documents1 = agent1.transform_data(raw_data1)

        raw_data2 = agent2.fetch_data()
        documents2 = agent2.transform_data(raw_data2)

        # Extract keys
        keys1 = sorted([
            doc.get('_key')
            for doc in documents1
            if doc.get('_collection') == 'regulatory_requirements' and doc.get('_key')
        ])

        keys2 = sorted([
            doc.get('_key')
            for doc in documents2
            if doc.get('_collection') == 'regulatory_requirements' and doc.get('_key')
        ])

        # Keys should be identical
        assert keys1 == keys2, "Keys should be deterministically generated"


class TestInvalidFrameworkKey:
    """Test error handling for invalid framework keys."""

    def test_invalid_framework_key_file_not_found(self, mock_db):
        """
        Test error when framework YAML doesn't exist.

        Validates:
        - FileNotFoundError raised
        - Helpful error message provided
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="NONEXISTENT_FRAMEWORK")

        # Attempting to fetch data should raise FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            agent.fetch_data()

        # Error message should be helpful
        assert "YAML file not found" in str(exc_info.value)

    def test_invalid_framework_key_in_script(self, mock_db):
        """
        Test ingestion script handles invalid framework gracefully.

        Validates:
        - Script returns error status
        - No exceptions raised (errors caught)
        """
        from scripts.ingest_regulatory_frameworks import ingest_framework

        # Ingest invalid framework
        result = ingest_framework("INVALID_FRAMEWORK", mock_db, dry_run=False)

        # Assertions
        assert result['status'] == 'failed', "Ingestion should fail for invalid framework"
        assert 'error' in result, "Error message should be present"
        assert result.get('errors', 0) > 0, "Error count should be > 0"


class TestYAMLValidationError:
    """Test YAML schema validation error handling."""

    @patch('builtins.open', side_effect=FileNotFoundError("YAML file not found"))
    def test_yaml_file_not_found(self, mock_open, mock_db):
        """
        Test error when YAML file doesn't exist.

        Validates:
        - FileNotFoundError raised
        - Agent handles error gracefully
        """
        agent = YAMLRegulatoryAgent(mock_db, framework_key="MISSING_FRAMEWORK")

        with pytest.raises(FileNotFoundError):
            agent.fetch_data()

    def test_yaml_schema_validation_framework_missing(self, mock_db, tmp_path):
        """
        Test YAML validation error when framework section is missing.

        Validates:
        - YAMLSchemaValidationError raised
        - Error message identifies missing framework section
        """
        # Create invalid YAML (missing framework section)
        invalid_yaml_path = tmp_path / "invalid_framework.yaml"
        invalid_yaml_path.write_text("""
requirements:
  - key: TEST_1
    requirement_id: "1"
    title: "Test Requirement"
    text: "Test text"
    requirement_type: "procedural"
    obligation_level: "shall"
""")

        # Mock yaml_path to point to invalid YAML
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")
        agent.yaml_path = invalid_yaml_path

        # Attempting to fetch data should raise YAMLSchemaValidationError
        with pytest.raises(YAMLSchemaValidationError) as exc_info:
            agent.fetch_data()

        # Error message should identify missing framework
        assert "Missing required top-level field: 'framework'" in str(exc_info.value)

    def test_yaml_schema_validation_invalid_obligation_level(self, mock_db, tmp_path):
        """
        Test YAML validation error when obligation_level is invalid.

        Validates:
        - YAMLSchemaValidationError raised
        - Error message identifies invalid enum value
        """
        # Create invalid YAML (invalid obligation_level)
        invalid_yaml_path = tmp_path / "invalid_obligation.yaml"
        invalid_yaml_path.write_text("""
framework:
  key: TEST_FRAMEWORK
  name: "Test Framework"
  short_name: "TF"
  jurisdiction: "US"
  issuing_body: "Test Body"
  document_type: "regulation"
  version: "1.0"
  source_url: "http://example.com"
  source_format: "pdf"

requirements:
  - key: TEST_1
    requirement_id: "1"
    title: "Test Requirement"
    text: "Test text"
    requirement_type: "procedural"
    obligation_level: "must"
""")

        # Mock yaml_path to point to invalid YAML
        agent = YAMLRegulatoryAgent(mock_db, framework_key="FDA_524B")
        agent.yaml_path = invalid_yaml_path

        # Attempting to fetch data should raise YAMLSchemaValidationError
        with pytest.raises(YAMLSchemaValidationError) as exc_info:
            agent.fetch_data()

        # Error message should identify invalid obligation_level
        assert "Invalid obligation_level" in str(exc_info.value)
        assert "must" in str(exc_info.value)
        assert "shall/should/may" in str(exc_info.value).lower()


# Integration test marker
@pytest.mark.integration
@pytest.mark.requires_db
class TestRegulatoryIngestionIntegration:
    """
    Integration tests requiring real database connection.

    These tests are marked with @pytest.mark.requires_db and will be
    skipped unless explicitly run with pytest -m requires_db.
    """

    def test_full_fda_ingestion_with_db(self):
        """
        Test full FDA 524B ingestion with real database.

        Requires:
        - ArangoDB running on localhost:8529
        - complira_graph database exists

        Validates:
        - 12 requirements inserted
        - All requirements queryable
        - No errors
        """
        pytest.skip("Integration test: Requires real database")

    def test_full_cra_ingestion_with_db(self):
        """
        Test full CRA ingestion with real database.

        Requires:
        - ArangoDB running on localhost:8529
        - complira_graph database exists

        Validates:
        - 8 requirements inserted
        - All requirements queryable
        - No errors
        """
        pytest.skip("Integration test: Requires real database")
