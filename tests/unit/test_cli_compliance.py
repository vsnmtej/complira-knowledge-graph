"""
Unit tests for CLI compliance commands.

Tests the compliance, violations, and requirement CLI commands that leverage
the centralized ComplianceQueries class.
"""

import json
from unittest.mock import Mock, patch, MagicMock
import pytest
from click.testing import CliRunner

from complira_graph.cli import cli


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_db():
    """Mock ArangoDB database."""
    db = Mock()
    db.aql = Mock()
    return db


@pytest.fixture
def sample_frameworks():
    """Sample framework compliance data."""
    return [
        {
            'framework': 'CRA',
            'framework_name': 'EU Cyber Resilience Act',
            'framework_short_name': 'CRA',
            'enforcement_date': '2024-12-15',
            'jurisdiction': 'EU',
            'total_requirements': 45,
            'violated_requirements': 3,
            'compliant_requirements': 42,
            'compliance_score': 0.933,
            'compliance_percentage': '93.3%',
            'status': 'mostly_compliant',
            'violation_summary': {
                'cwe_count': 2,
                'direct_count': 1,
                'total_violations': 3,
                'unique_requirements': 3
            }
        },
        {
            'framework': 'NIST_SSDF',
            'framework_name': 'NIST Secure Software Development Framework',
            'framework_short_name': 'NIST SSDF',
            'enforcement_date': '2024-01-01',
            'jurisdiction': 'US',
            'total_requirements': 43,
            'violated_requirements': 0,
            'compliant_requirements': 43,
            'compliance_score': 1.0,
            'compliance_percentage': '100.0%',
            'status': 'compliant',
            'violation_summary': {
                'cwe_count': 0,
                'direct_count': 0,
                'total_violations': 0,
                'unique_requirements': 0
            }
        }
    ]


@pytest.fixture
def sample_violations():
    """Sample violation data."""
    return {
        'cwe_violations': [
            {
                'requirement_key': 'CRA_I_1_a',
                'requirement_id': 'CRA I.1.a',
                'framework': 'CRA',
                'violation_source': 'cwe_mapping',
                'cve_id': 'CVE-2024-1234',
                'cwe_id': 'CWE-787',
                'cwe_name': 'Out-of-bounds Write',
                'cvss_v3_score': 9.8,
                'component_key': 'comp_1',
                'component_purl': 'pkg:npm/lodash@4.17.20',
                'component_name': 'lodash'
            },
            {
                'requirement_key': 'CRA_I_2_b',
                'requirement_id': 'CRA I.2.b',
                'framework': 'CRA',
                'violation_source': 'cwe_mapping',
                'cve_id': 'CVE-2024-5678',
                'cwe_id': 'CWE-89',
                'cwe_name': 'SQL Injection',
                'cvss_v3_score': 8.5,
                'component_key': 'comp_2',
                'component_purl': 'pkg:npm/express@4.17.0',
                'component_name': 'express'
            }
        ],
        'direct_violations': [
            {
                'requirement_key': 'CRA_I_3_c',
                'requirement_id': 'CRA I.3.c',
                'framework': 'CRA',
                'violation_source': 'scanner_finding',
                'finding_id': 'semgrep_finding_42',
                'finding_type': 'sast_findings',
                'severity': 'high',
                'cwe_id': 'CWE-79',
                'file_path': 'src/api/users.py',
                'line_number': 145,
                'tool_name': 'semgrep',
                'scan_date': '2024-03-01',
                'component_key': 'comp_3',
                'component_purl': 'pkg:pypi/flask@2.0.0'
            }
        ],
        'all_violations': [],  # Will be combined
        'violated_requirements': ['CRA_I_1_a', 'CRA_I_2_b', 'CRA_I_3_c'],
        'summary': {
            'cwe_count': 2,
            'direct_count': 1,
            'total_violations': 3,
            'unique_requirements': 3
        }
    }


@pytest.fixture
def sample_blast_radius():
    """Sample requirement blast radius data."""
    return {
        'requirement_key': 'CRA_I_1_a',
        'requirement_id': 'CRA I.1.a',
        'framework': 'CRA',
        'found': True,
        'affected_components_count': 5,
        'total_violations': 7,
        'cwe_violations_count': 5,
        'direct_violations_count': 2,
        'cwe_violations': [
            {
                'component': {
                    'name': 'lodash',
                    'purl': 'pkg:npm/lodash@4.17.20'
                },
                'vulnerability': {
                    'cve_id': 'CVE-2024-1234',
                    'cvss_v3_score': 9.8
                },
                'cwe': {
                    'cwe_id': 'CWE-787',
                    'name': 'Out-of-bounds Write'
                },
                'source': 'cwe_mapping'
            }
        ],
        'direct_violations': [
            {
                'component': {
                    'name': 'flask-app',
                    'purl': 'pkg:pypi/flask@2.0.0'
                },
                'finding': {
                    'finding_type': 'sast_findings',
                    'severity': 'high',
                    'file_path': 'src/api/users.py'
                },
                'scan_session': {
                    'tool_name': 'semgrep',
                    'scan_date': '2024-03-01'
                },
                'source': 'scanner_finding'
            }
        ]
    }


# ========== Compliance Status Tests ==========

@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_compliance_status_table_format(mock_get_db, mock_queries, runner, mock_db, sample_frameworks):
    """Test compliance status command with table output."""
    mock_get_db.return_value = mock_db
    mock_queries.get_framework_compliance.return_value = sample_frameworks

    result = runner.invoke(cli, ['compliance', 'status', 'acme_corp'])

    assert result.exit_code == 0
    assert 'Compliance Status: acme_corp' in result.output
    assert 'CRA' in result.output
    assert 'NIST SSDF' in result.output
    assert '93.3%' in result.output
    assert '100.0%' in result.output
    assert 'compliant' in result.output.lower()

    # Verify ComplianceQueries was called correctly
    mock_queries.get_framework_compliance.assert_called_once_with(
        mock_db, 'acme_corp', include_violations=False
    )


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_compliance_status_json_format(mock_get_db, mock_queries, runner, mock_db, sample_frameworks):
    """Test compliance status command with JSON output."""
    mock_get_db.return_value = mock_db
    mock_queries.get_framework_compliance.return_value = sample_frameworks

    result = runner.invoke(cli, ['compliance', 'status', 'acme_corp', '--format', 'json'])

    assert result.exit_code == 0
    # Extract JSON from output (skip header line)
    lines = result.output.strip().split('\n')
    json_start = next(i for i, line in enumerate(lines) if line.startswith('['))
    json_output = '\n'.join(lines[json_start:])
    output_data = json.loads(json_output)
    assert len(output_data) == 2
    assert output_data[0]['framework'] == 'CRA'
    assert output_data[1]['framework'] == 'NIST_SSDF'


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_compliance_status_with_framework_filter(mock_get_db, mock_queries, runner, mock_db, sample_frameworks):
    """Test compliance status command filtered by framework."""
    mock_get_db.return_value = mock_db
    mock_queries.get_framework_compliance.return_value = sample_frameworks

    result = runner.invoke(cli, ['compliance', 'status', 'acme_corp', '--framework', 'CRA'])

    assert result.exit_code == 0
    assert 'CRA' in result.output
    # Should only show CRA framework


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_compliance_status_no_frameworks(mock_get_db, mock_queries, runner, mock_db):
    """Test compliance status when no frameworks exist."""
    mock_get_db.return_value = mock_db
    mock_queries.get_framework_compliance.return_value = []

    result = runner.invoke(cli, ['compliance', 'status', 'acme_corp'])

    assert result.exit_code == 0
    assert 'No regulatory frameworks found' in result.output


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_compliance_status_database_error(mock_get_db, mock_queries, runner, mock_db):
    """Test compliance status handles database errors gracefully."""
    mock_get_db.return_value = mock_db
    mock_queries.get_framework_compliance.side_effect = Exception("Database connection failed")

    result = runner.invoke(cli, ['compliance', 'status', 'acme_corp'])

    assert result.exit_code == 1
    assert 'Compliance check failed' in result.output


# ========== Violations List Tests ==========

@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_all_sources(mock_get_db, mock_queries, runner, mock_db, sample_violations):
    """Test violations list command showing all sources."""
    mock_get_db.return_value = mock_db
    mock_queries.get_all_violations.return_value = sample_violations

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp'])

    assert result.exit_code == 0
    assert 'Compliance Violations: acme_corp' in result.output
    assert 'Path A: CWE Mapping Violations' in result.output
    assert 'Path B: Direct Scanner Finding Violations' in result.output
    assert 'CVE-2024-1234' in result.output
    assert 'CVE-2024-5678' in result.output
    assert 'sast_findings' in result.output  # Finding type is displayed


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_cwe_source_only(mock_get_db, mock_queries, runner, mock_db, sample_violations):
    """Test violations list filtered to CWE source only."""
    mock_get_db.return_value = mock_db
    mock_queries.get_violations_via_cwe_mapping.return_value = sample_violations['cwe_violations']

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp', '--source', 'cwe'])

    assert result.exit_code == 0
    assert 'CVE-2024-1234' in result.output
    mock_queries.get_violations_via_cwe_mapping.assert_called_once()


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_scanner_source_only(mock_get_db, mock_queries, runner, mock_db, sample_violations):
    """Test violations list filtered to scanner source only."""
    mock_get_db.return_value = mock_db
    mock_queries.get_violations_via_scanner_findings.return_value = sample_violations['direct_violations']

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp', '--source', 'scanner'])

    assert result.exit_code == 0
    assert 'sast_findings' in result.output  # Finding type is displayed
    assert 'CWE-79' in result.output  # CWE ID is displayed
    mock_queries.get_violations_via_scanner_findings.assert_called_once()


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_with_framework_filter(mock_get_db, mock_queries, runner, mock_db, sample_violations):
    """Test violations list filtered by framework."""
    mock_get_db.return_value = mock_db
    mock_queries.get_all_violations.return_value = sample_violations

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp', '--framework', 'CRA'])

    assert result.exit_code == 0
    # Verify framework was passed to query
    mock_queries.get_all_violations.assert_called_once_with(mock_db, 'acme_corp', 'CRA')


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_with_limit(mock_get_db, mock_queries, runner, mock_db, sample_violations):
    """Test violations list with result limit."""
    mock_get_db.return_value = mock_db
    # Create more violations to test limit
    many_violations = sample_violations.copy()
    many_violations['cwe_violations'] = sample_violations['cwe_violations'] * 15  # 30 violations
    mock_queries.get_all_violations.return_value = many_violations

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp', '--limit', '10'])

    assert result.exit_code == 0
    assert 'more CWE violations' in result.output  # Should show truncation message


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_json_format(mock_get_db, mock_queries, runner, mock_db, sample_violations):
    """Test violations list with JSON output."""
    mock_get_db.return_value = mock_db
    mock_queries.get_all_violations.return_value = sample_violations

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp', '--format', 'json'])

    assert result.exit_code == 0
    # Extract JSON from output (skip header line)
    lines = result.output.strip().split('\n')
    json_start = next(i for i, line in enumerate(lines) if line.startswith('{'))
    json_output = '\n'.join(lines[json_start:])
    output_data = json.loads(json_output)
    assert 'cwe_violations' in output_data
    assert 'direct_violations' in output_data
    assert 'summary' in output_data


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_no_violations(mock_get_db, mock_queries, runner, mock_db):
    """Test violations list when no violations exist."""
    mock_get_db.return_value = mock_db
    mock_queries.get_all_violations.return_value = {
        'cwe_violations': [],
        'direct_violations': [],
        'summary': {'total_violations': 0}
    }

    result = runner.invoke(cli, ['violations', 'list', 'acme_corp'])

    assert result.exit_code == 0
    assert 'No compliance violations found' in result.output


# ========== Requirement Show Tests ==========

@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_requirement_show_table_format(mock_get_db, mock_queries, runner, mock_db, sample_blast_radius):
    """Test requirement show command with table output."""
    mock_get_db.return_value = mock_db
    mock_queries.get_requirement_blast_radius.return_value = sample_blast_radius

    result = runner.invoke(cli, ['requirement', 'show', 'CRA_I_1_a', 'acme_corp'])

    assert result.exit_code == 0
    assert 'Requirement Blast Radius: CRA_I_1_a' in result.output
    assert 'CRA I.1.a' in result.output
    assert 'CRA' in result.output
    assert 'Affected Components' in result.output
    assert '5' in result.output  # affected_components_count


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_requirement_show_json_format(mock_get_db, mock_queries, runner, mock_db, sample_blast_radius):
    """Test requirement show command with JSON output."""
    mock_get_db.return_value = mock_db
    mock_queries.get_requirement_blast_radius.return_value = sample_blast_radius

    result = runner.invoke(cli, ['requirement', 'show', 'CRA_I_1_a', 'acme_corp', '--format', 'json'])

    assert result.exit_code == 0
    # Extract JSON from output (skip header line)
    lines = result.output.strip().split('\n')
    json_start = next(i for i, line in enumerate(lines) if line.startswith('{'))
    json_output = '\n'.join(lines[json_start:])
    output_data = json.loads(json_output)
    assert output_data['requirement_key'] == 'CRA_I_1_a'
    assert output_data['found'] is True
    assert output_data['affected_components_count'] == 5


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_requirement_show_not_found(mock_get_db, mock_queries, runner, mock_db):
    """Test requirement show when requirement doesn't exist."""
    mock_get_db.return_value = mock_db
    mock_queries.get_requirement_blast_radius.return_value = {
        'requirement_key': 'INVALID_KEY',
        'found': False,
        'error': 'Requirement not found'
    }

    result = runner.invoke(cli, ['requirement', 'show', 'INVALID_KEY', 'acme_corp'])

    assert result.exit_code == 1
    assert 'Requirement not found' in result.output


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_requirement_show_no_violations(mock_get_db, mock_queries, runner, mock_db):
    """Test requirement show when no violations exist."""
    mock_get_db.return_value = mock_db
    blast_radius_no_violations = {
        'requirement_key': 'CRA_I_1_a',
        'requirement_id': 'CRA I.1.a',
        'framework': 'CRA',
        'found': True,
        'affected_components_count': 0,
        'total_violations': 0,
        'cwe_violations_count': 0,
        'direct_violations_count': 0,
        'cwe_violations': [],
        'direct_violations': []
    }
    mock_queries.get_requirement_blast_radius.return_value = blast_radius_no_violations

    result = runner.invoke(cli, ['requirement', 'show', 'CRA_I_1_a', 'acme_corp'])

    assert result.exit_code == 0
    assert 'No violations found for this requirement' in result.output


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_requirement_show_database_error(mock_get_db, mock_queries, runner, mock_db):
    """Test requirement show handles database errors gracefully."""
    mock_get_db.return_value = mock_db
    mock_queries.get_requirement_blast_radius.side_effect = Exception("Database error")

    result = runner.invoke(cli, ['requirement', 'show', 'CRA_I_1_a', 'acme_corp'])

    assert result.exit_code == 1
    assert 'Requirement query failed' in result.output


# ========== File Output Tests ==========

@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_compliance_status_file_output(mock_get_db, mock_queries, runner, mock_db, sample_frameworks, tmp_path):
    """Test compliance status saves to file."""
    mock_get_db.return_value = mock_db
    mock_queries.get_framework_compliance.return_value = sample_frameworks

    output_file = tmp_path / "compliance.json"
    result = runner.invoke(cli, ['compliance', 'status', 'acme_corp', '--output', str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert len(data) == 2
    assert 'saved to' in result.output


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_violations_list_file_output(mock_get_db, mock_queries, runner, mock_db, sample_violations, tmp_path):
    """Test violations list saves to file."""
    mock_get_db.return_value = mock_db
    mock_queries.get_all_violations.return_value = sample_violations

    output_file = tmp_path / "violations.json"
    result = runner.invoke(cli, ['violations', 'list', 'acme_corp', '--output', str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert 'cwe_violations' in data


@patch('complira_graph.queries.compliance.ComplianceQueries')
@patch('complira_graph.cli.get_db')
def test_requirement_show_file_output(mock_get_db, mock_queries, runner, mock_db, sample_blast_radius, tmp_path):
    """Test requirement show saves to file."""
    mock_get_db.return_value = mock_db
    mock_queries.get_requirement_blast_radius.return_value = sample_blast_radius

    output_file = tmp_path / "blast_radius.json"
    result = runner.invoke(cli, ['requirement', 'show', 'CRA_I_1_a', 'acme_corp', '--output', str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert data['requirement_key'] == 'CRA_I_1_a'
