"""
Unit tests for DAG builder and topological sorting.
"""

import pytest
from complira_graph.orchestrator.dag import DAGBuilder, AGENT_DEPENDENCIES


class TestDAGBuilder:
    """Test DAG builder functionality."""

    def test_build_returns_batches(self):
        """Test that build() returns list of batches."""
        builder = DAGBuilder()
        batches = builder.build()

        assert isinstance(batches, list)
        assert len(batches) > 0
        assert all(isinstance(batch, list) for batch in batches)

    def test_first_batch_has_no_dependencies(self):
        """Test that first batch contains only agents with no dependencies."""
        builder = DAGBuilder()
        batches = builder.build()

        first_batch = batches[0]

        for agent in first_batch:
            deps = builder.get_dependencies(agent)
            assert len(deps) == 0, f"{agent} should have no dependencies in first batch"

    def test_all_agents_included(self):
        """Test that all agents are included in batches."""
        builder = DAGBuilder()
        batches = builder.build()

        # Flatten all batches
        all_agents = []
        for batch in batches:
            all_agents.extend(batch)

        # Check all agents from AGENT_DEPENDENCIES are included
        for agent in AGENT_DEPENDENCIES.keys():
            assert agent in all_agents, f"{agent} not found in execution batches"

    def test_dependencies_respected(self):
        """Test that dependencies are respected in execution order."""
        builder = DAGBuilder()
        batches = builder.build()

        # Build map of agent -> batch index
        agent_to_batch = {}
        for batch_idx, batch in enumerate(batches):
            for agent in batch:
                agent_to_batch[agent] = batch_idx

        # Check each agent appears after its dependencies
        for agent, deps in AGENT_DEPENDENCIES.items():
            agent_batch = agent_to_batch[agent]
            for dep in deps:
                dep_batch = agent_to_batch[dep]
                assert dep_batch < agent_batch, \
                    f"{agent} (batch {agent_batch}) depends on {dep} (batch {dep_batch})"

    def test_get_dependencies(self):
        """Test get_dependencies() method."""
        builder = DAGBuilder()

        # CWE has no dependencies
        assert builder.get_dependencies('CWEAgent') == []

        # NVD depends on CWE
        assert 'CWEAgent' in builder.get_dependencies('NVDAgent')

        # EPSS depends on NVD
        assert 'NVDAgent' in builder.get_dependencies('EPSSAgent')

    def test_get_dependents(self):
        """Test get_dependents() method."""
        builder = DAGBuilder()

        # CWE is depended on by NVD, OSV, GHSA, etc.
        cwe_dependents = builder.get_dependents('CWEAgent')
        assert 'NVDAgent' in cwe_dependents
        assert 'OSVAgent' in cwe_dependents

        # NVD is depended on by EPSS, KEV, etc.
        nvd_dependents = builder.get_dependents('NVDAgent')
        assert 'EPSSAgent' in nvd_dependents
        assert 'KEVAgent' in nvd_dependents

    def test_validate_graph_success(self):
        """Test validate_graph() with valid dependencies."""
        builder = DAGBuilder()
        is_valid, errors = builder.validate_graph()

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_graph_detects_self_dependency(self):
        """Test validate_graph() detects self-dependencies."""
        invalid_deps = {
            'AgentA': ['AgentA'],  # Self-dependency
        }

        builder = DAGBuilder(agent_dependencies=invalid_deps)
        is_valid, errors = builder.validate_graph()

        assert is_valid is False
        assert any('depends on itself' in error for error in errors)

    def test_validate_graph_detects_invalid_dependency(self):
        """Test validate_graph() detects non-existent dependencies."""
        invalid_deps = {
            'AgentA': [],
            'AgentB': ['NonExistentAgent'],  # Invalid dependency
        }

        builder = DAGBuilder(agent_dependencies=invalid_deps)
        is_valid, errors = builder.validate_graph()

        assert is_valid is False
        assert any('non-existent agent' in error.lower() for error in errors)

    def test_validate_graph_detects_cycle(self):
        """Test validate_graph() detects circular dependencies."""
        cyclic_deps = {
            'AgentA': ['AgentB'],
            'AgentB': ['AgentC'],
            'AgentC': ['AgentA'],  # Cycle: A -> B -> C -> A
        }

        builder = DAGBuilder(agent_dependencies=cyclic_deps)
        is_valid, errors = builder.validate_graph()

        assert is_valid is False
        assert any('circular' in error.lower() for error in errors)

    def test_get_execution_stats(self):
        """Test get_execution_stats() returns valid statistics."""
        builder = DAGBuilder()
        stats = builder.get_execution_stats()

        assert 'total_agents' in stats
        assert 'total_batches' in stats
        assert 'max_parallelism' in stats
        assert 'critical_path_length' in stats
        assert 'avg_batch_size' in stats
        assert 'batches' in stats

        assert stats['total_agents'] > 0
        assert stats['total_batches'] > 0
        assert stats['max_parallelism'] > 0
        assert stats['critical_path_length'] > 0
        assert stats['avg_batch_size'] > 0

    def test_visualize_dag_returns_string(self):
        """Test visualize_dag() returns ASCII art string."""
        builder = DAGBuilder()
        visualization = builder.visualize_dag()

        assert isinstance(visualization, str)
        assert 'AGENT EXECUTION DAG' in visualization
        assert 'Batch 1' in visualization
        assert 'Total Agents:' in visualization


class TestAgentDependenciesStructure:
    """Test the AGENT_DEPENDENCIES structure itself."""

    def test_all_dependencies_exist(self):
        """Test that all referenced dependencies are valid agents."""
        all_agents = set(AGENT_DEPENDENCIES.keys())

        for agent, deps in AGENT_DEPENDENCIES.items():
            for dep in deps:
                assert dep in all_agents, \
                    f"{agent} depends on {dep} which is not in AGENT_DEPENDENCIES"

    def test_no_self_dependencies(self):
        """Test that no agent depends on itself."""
        for agent, deps in AGENT_DEPENDENCIES.items():
            assert agent not in deps, f"{agent} has self-dependency"

    def test_foundation_agents_no_deps(self):
        """Test that foundation agents have no dependencies."""
        foundation_agents = [
            'CWEAgent', 'ATTACKAgent', 'CAPECAgent', 'D3FENDAgent',
            'ATLASAgent', 'SPDXLicensesAgent', 'OSCALAgent', 'SCFAgent',
            'OpenCREAgent'
        ]

        for agent in foundation_agents:
            assert len(AGENT_DEPENDENCIES[agent]) == 0, \
                f"Foundation agent {agent} should have no dependencies"

    def test_nvd_depends_on_cwe(self):
        """Test that NVD depends on CWE (critical relationship)."""
        assert 'CWEAgent' in AGENT_DEPENDENCIES['NVDAgent']

    def test_llm_agents_depend_on_data_agents(self):
        """Test that LLM agents depend on deterministic agents."""
        llm_agents = {
            'CWEClassifierAgent': ['NVDAgent', 'CWEAgent'],
            'PURLtoCPEAgent': ['DepsDevAgent'],
            'VEXSynthesizerAgent': ['NVDAgent', 'DepsDevAgent'],
            'RegulatoryMapperAgent': ['NVDAgent', 'OSCALAgent', 'SCFAgent'],
            'CVEEntityExtractorAgent': ['NVDAgent'],
        }

        for llm_agent, expected_deps in llm_agents.items():
            actual_deps = AGENT_DEPENDENCIES[llm_agent]
            for expected_dep in expected_deps:
                assert expected_dep in actual_deps, \
                    f"{llm_agent} should depend on {expected_dep}"
