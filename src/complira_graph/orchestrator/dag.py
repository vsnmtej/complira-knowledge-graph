"""
DAG (Directed Acyclic Graph) Builder for Agent Dependencies.

Implements topological sorting using Kahn's algorithm to determine optimal
execution order for data ingestion and enrichment agents.

Ensures:
- Dependency resolution (e.g., NVD requires CWE)
- Parallel execution where possible
- No circular dependencies
"""

from typing import Dict, List, Set, Tuple
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger()


# ========== Agent Dependency Graph ==========

AGENT_DEPENDENCIES: Dict[str, List[str]] = {
    # ========== Batch 1: Foundation Agents (No Dependencies) ==========
    'CWEAgent': [],
    'ATTACKAgent': [],
    'CAPECAgent': [],
    'D3FENDAgent': [],
    'ATLASAgent': [],
    'SPDXLicensesAgent': [],
    'OSCALAgent': [],
    'SCFAgent': [],
    'OpenCREAgent': [],

    # ========== Batch 2: Vulnerability Data (Depends on CWE) ==========
    'NVDAgent': ['CWEAgent'],  # Creates has_weakness edges to CWE
    'OSVAgent': ['CWEAgent'],
    'GHSAAgent': ['CWEAgent'],
    'EPSSAgent': ['NVDAgent'],  # EPSS scores reference CVEs
    'KEVAgent': ['NVDAgent'],  # KEV references CVEs
    'VulnrichmentAgent': ['NVDAgent'],  # Enriches existing CVEs

    # ========== Batch 3: Exploit Data (Depends on CVE, CAPEC) ==========
    'MetasploitAgent': ['NVDAgent', 'CAPECAgent'],
    'ExploitDBAgent': ['NVDAgent', 'CAPECAgent'],
    'NucleiAgent': ['NVDAgent'],
    'PoCInGitHubAgent': ['NVDAgent'],

    # ========== Batch 4: Component Data (No Dependencies) ==========
    'DepsDevAgent': [],
    'EcosystemsAgent': [],
    'EndOfLifeAgent': [],
    'ScorecardAgent': [],

    # ========== LLM Enrichment Agents (Depend on Deterministic Data) ==========
    'CWEClassifierAgent': ['NVDAgent', 'CWEAgent'],  # Classifies CVEs to CWE
    'PURLtoCPEAgent': ['DepsDevAgent'],  # Maps components to CPE
    'VEXSynthesizerAgent': ['NVDAgent', 'DepsDevAgent'],  # Generates VEX
    'RegulatoryMapperAgent': ['NVDAgent', 'OSCALAgent', 'SCFAgent'],  # Maps to controls
    'CVEEntityExtractorAgent': ['NVDAgent'],  # Extracts entities from CVEs
}


class DAGBuilder:
    """
    Builds directed acyclic graph for agent execution order.

    Uses Kahn's algorithm for topological sorting to determine:
    1. Execution batches (agents that can run in parallel)
    2. Dependency validation (detects cycles)
    3. Optimal parallelism
    """

    def __init__(self, agent_dependencies: Dict[str, List[str]] = None):
        """
        Initialize DAG builder.

        Args:
            agent_dependencies: Agent dependency graph (defaults to AGENT_DEPENDENCIES)
        """
        self.dependencies = agent_dependencies or AGENT_DEPENDENCIES
        self.logger = logger.bind(component='DAGBuilder')

    def build(self) -> List[List[str]]:
        """
        Build execution batches using topological sort (Kahn's algorithm).

        Returns:
            list[list[str]]: Batches of agents that can execute in parallel

        Raises:
            ValueError: If circular dependency detected

        Example:
            [
                ['CWEAgent', 'ATTACKAgent', 'SPDXLicensesAgent'],  # Batch 1 (no deps)
                ['NVDAgent', 'OSVAgent'],  # Batch 2 (depends on Batch 1)
                ['EPSSAgent', 'KEVAgent'],  # Batch 3 (depends on Batch 2)
            ]
        """
        self.logger.info("Building agent execution DAG")

        # Calculate in-degrees (number of dependencies)
        in_degree = {agent: 0 for agent in self.dependencies}
        graph = defaultdict(list)

        for agent, deps in self.dependencies.items():
            in_degree[agent] = len(deps)
            for dep in deps:
                graph[dep].append(agent)

        # Find agents with no dependencies (in-degree = 0)
        queue = deque([agent for agent, degree in in_degree.items() if degree == 0])

        batches = []
        visited_count = 0

        while queue:
            # Current batch: all agents with no remaining dependencies
            batch_size = len(queue)
            current_batch = []

            for _ in range(batch_size):
                agent = queue.popleft()
                current_batch.append(agent)
                visited_count += 1

                # Reduce in-degree for dependent agents
                for dependent in graph[agent]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

            batches.append(sorted(current_batch))  # Sort for deterministic output

        # Check for cycles
        if visited_count != len(self.dependencies):
            unvisited = [agent for agent, degree in in_degree.items() if degree > 0]
            raise ValueError(
                f"Circular dependency detected. Unvisited agents: {unvisited}"
            )

        self.logger.info(
            "DAG built successfully",
            total_agents=len(self.dependencies),
            total_batches=len(batches),
            batches=[{
                'batch_num': i + 1,
                'agent_count': len(batch),
                'agents': batch,
            } for i, batch in enumerate(batches)],
        )

        return batches

    def get_dependencies(self, agent_name: str) -> List[str]:
        """
        Get dependencies for a specific agent.

        Args:
            agent_name: Agent class name

        Returns:
            list[str]: List of agent dependencies
        """
        return self.dependencies.get(agent_name, [])

    def get_dependents(self, agent_name: str) -> List[str]:
        """
        Get agents that depend on the specified agent.

        Args:
            agent_name: Agent class name

        Returns:
            list[str]: List of dependent agents
        """
        dependents = []
        for agent, deps in self.dependencies.items():
            if agent_name in deps:
                dependents.append(agent)
        return dependents

    def validate_graph(self) -> Tuple[bool, List[str]]:
        """
        Validate dependency graph for correctness.

        Returns:
            tuple[bool, list[str]]: (is_valid, errors)

        Validations:
            - No circular dependencies
            - All dependencies are valid agent names
            - No self-dependencies
        """
        errors = []

        # Check for self-dependencies
        for agent, deps in self.dependencies.items():
            if agent in deps:
                errors.append(f"{agent} depends on itself")

        # Check for invalid dependencies (non-existent agents)
        all_agents = set(self.dependencies.keys())
        for agent, deps in self.dependencies.items():
            for dep in deps:
                if dep not in all_agents:
                    errors.append(f"{agent} depends on non-existent agent: {dep}")

        # Check for cycles (will raise ValueError if cycle exists)
        try:
            self.build()
        except ValueError as e:
            errors.append(str(e))

        is_valid = len(errors) == 0

        if is_valid:
            self.logger.info("Dependency graph validation passed")
        else:
            self.logger.error("Dependency graph validation failed", errors=errors)

        return is_valid, errors

    def get_execution_stats(self) -> Dict:
        """
        Get execution statistics for the DAG.

        Returns:
            dict: Execution statistics
        """
        batches = self.build()

        # Calculate max parallelism
        max_parallel = max(len(batch) for batch in batches) if batches else 0

        # Calculate critical path (longest dependency chain)
        critical_path_length = len(batches)

        # Calculate average batch size
        avg_batch_size = sum(len(batch) for batch in batches) / len(batches) if batches else 0

        stats = {
            'total_agents': len(self.dependencies),
            'total_batches': len(batches),
            'max_parallelism': max_parallel,
            'critical_path_length': critical_path_length,
            'avg_batch_size': round(avg_batch_size, 2),
            'batches': batches,
        }

        return stats

    def visualize_dag(self) -> str:
        """
        Generate ASCII visualization of DAG.

        Returns:
            str: ASCII art representation of DAG
        """
        batches = self.build()

        lines = []
        lines.append("=" * 80)
        lines.append("AGENT EXECUTION DAG")
        lines.append("=" * 80)
        lines.append("")

        for i, batch in enumerate(batches, 1):
            lines.append(f"Batch {i} (Parallel Execution - {len(batch)} agents):")
            lines.append("-" * 80)
            for agent in batch:
                deps = self.get_dependencies(agent)
                deps_str = f" [depends on: {', '.join(deps)}]" if deps else " [no dependencies]"
                lines.append(f"  • {agent}{deps_str}")
            lines.append("")

        lines.append("=" * 80)

        stats = self.get_execution_stats()
        lines.append(f"Total Agents: {stats['total_agents']}")
        lines.append(f"Total Batches: {stats['total_batches']}")
        lines.append(f"Max Parallelism: {stats['max_parallelism']} agents")
        lines.append(f"Critical Path: {stats['critical_path_length']} batches")
        lines.append("=" * 80)

        return "\n".join(lines)


def get_execution_order() -> List[List[str]]:
    """
    Convenience function to get agent execution order.

    Returns:
        list[list[str]]: Batches of agents for parallel execution
    """
    builder = DAGBuilder()
    return builder.build()


def validate_dependencies() -> bool:
    """
    Convenience function to validate agent dependencies.

    Returns:
        bool: True if dependencies are valid

    Raises:
        ValueError: If validation fails
    """
    builder = DAGBuilder()
    is_valid, errors = builder.validate_graph()

    if not is_valid:
        raise ValueError(f"Dependency validation failed: {errors}")

    return True


if __name__ == '__main__':
    # Run when executed directly (for debugging)
    import sys

    builder = DAGBuilder()

    # Validate graph
    is_valid, errors = builder.validate_graph()
    if not is_valid:
        print("ERROR: Dependency graph validation failed!")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Print visualization
    print(builder.visualize_dag())

    # Print stats
    stats = builder.get_execution_stats()
    print("\nExecution Statistics:")
    print(f"  Total Agents: {stats['total_agents']}")
    print(f"  Total Batches: {stats['total_batches']}")
    print(f"  Max Parallelism: {stats['max_parallelism']} agents can run simultaneously")
    print(f"  Critical Path: {stats['critical_path_length']} sequential batches required")
    print(f"  Average Batch Size: {stats['avg_batch_size']} agents per batch")
