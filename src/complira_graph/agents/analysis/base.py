"""
Base class for analysis agents.

Analysis agents query and analyze data in the knowledge graph to generate
insights, reports, and recommendations without modifying the graph.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime
from arango.database import StandardDatabase
import structlog

from ...config import get_settings

logger = structlog.get_logger()


class BaseAnalysisAgent(ABC):
    """
    Abstract base class for analysis and reporting agents.

    Unlike ingestion agents, analysis agents:
    - Query existing data in the knowledge graph
    - Generate insights, reports, and recommendations
    - Do NOT modify the graph (read-only)

    Lifecycle:
    1. query_data() - Query relevant data from graph
    2. analyze() - Analyze queried data
    3. format_output() - Format results for presentation
    4. run() - Orchestrate the workflow

    Example:
        class VulnerabilityReportAgent(BaseAnalysisAgent):
            def query_data(self):
                # Query vulnerabilities with CISA enrichment
                ...

            def analyze(self, data):
                # Calculate priority scores
                ...

            def format_output(self, analysis):
                # Generate markdown report
                ...
    """

    def __init__(self, db: StandardDatabase, output_format: str = "text"):
        """
        Initialize analysis agent.

        Args:
            db: ArangoDB database instance
            output_format: Output format ("text", "json", "markdown")
        """
        self.db = db
        self.agent_name = self.__class__.__name__
        self.settings = get_settings()
        self.logger = logger.bind(agent=self.agent_name)
        self.output_format = output_format

        self.logger.info("Analysis agent initialized", output_format=output_format)

    @abstractmethod
    def query_data(self, **kwargs) -> Any:
        """
        Query relevant data from the knowledge graph.

        Args:
            **kwargs: Query parameters (e.g., cve_ids, date_range, filters)

        Returns:
            Any: Queried data (format depends on agent)

        Example:
            def query_data(self, limit=100):
                query = '''
                    FOR v IN vulnerabilities
                        FILTER v.cisa_enriched == true
                        LIMIT @limit
                        RETURN v
                '''
                return list(self.db.aql.execute(query, bind_vars={'limit': limit}))
        """
        pass

    @abstractmethod
    def analyze(self, data: Any) -> dict:
        """
        Analyze queried data to generate insights.

        Args:
            data: Data from query_data()

        Returns:
            dict: Analysis results with insights and statistics

        Example:
            def analyze(self, vulns):
                kev_count = sum(1 for v in vulns if v.get('in_cisa_kev'))
                return {
                    'total': len(vulns),
                    'kev_count': kev_count,
                    'critical_percent': kev_count / len(vulns) * 100
                }
        """
        pass

    @abstractmethod
    def format_output(self, analysis: dict) -> str:
        """
        Format analysis results for presentation.

        Args:
            analysis: Analysis results from analyze()

        Returns:
            str: Formatted output (text, JSON, markdown, etc.)

        Example:
            def format_output(self, analysis):
                if self.output_format == "json":
                    return json.dumps(analysis, indent=2)
                else:
                    return f"Total: {analysis['total']}, KEV: {analysis['kev_count']}"
        """
        pass

    def run(self, **kwargs) -> dict:
        """
        Execute full analysis workflow.

        Orchestrates:
        1. Query data from graph
        2. Analyze data
        3. Format output
        4. Return results

        Args:
            **kwargs: Query parameters passed to query_data()

        Returns:
            dict: Execution results with analysis and formatted output
        """
        start_time = datetime.now()

        self.logger.info("Analysis execution started", params=kwargs)

        try:
            # Step 1: Query data
            self.logger.info("Querying data")
            data = self.query_data(**kwargs)

            # Step 2: Analyze
            self.logger.info("Analyzing data")
            analysis = self.analyze(data)

            # Step 3: Format output
            self.logger.info("Formatting output", format=self.output_format)
            output = self.format_output(analysis)

            execution_time = (datetime.now() - start_time).total_seconds()

            result = {
                "agent": self.agent_name,
                "status": "success",
                "execution_time_seconds": execution_time,
                "analysis": analysis,
                "output": output,
            }

            self.logger.info("Analysis execution completed", execution_time=execution_time)

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "Analysis execution failed",
                error=str(e),
                execution_time_seconds=execution_time,
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": execution_time,
            }
