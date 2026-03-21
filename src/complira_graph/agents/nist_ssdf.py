"""
NIST SSDF (Secure Software Development Framework) ingestion agent.

This agent ingests the NIST SSDF framework from the official GitHub repository.
The SSDF provides practices and tasks for secure software development aligned
with NIST SP 800-218.

Data source: https://raw.githubusercontent.com/usnistgov/SSDF/main/ssdf-v1.1.json
Collections populated:
- regulatory_frameworks (1 document: NIST_SSDF framework)
- regulatory_requirements (practices and tasks)
- requirement_hierarchy (edges from practices to tasks)

Checkpoint behavior:
- Supports checkpointing (saves every 10 practices)
- Resumes from last saved practice if interrupted
- Clears checkpoint on successful completion

REFACTORED VERSION using DRY/SOLID utilities:
✅ DRY: Uses RegulatoryKeyGenerator for consistent key generation
✅ SOLID: Uses NormativeRequirement with composition (SRP)
✅ LSP: fetch_data() returns List[Dict[str, Any]] (standardized return type)
✅ OCP: Easy to extend for new SSDF versions
✅ ISP: Uses appropriate requirement type (NormativeRequirement)
"""

from typing import List, Dict, Any, Optional
from datetime import date
import requests

from complira_graph.agents.base import BaseIngestionAgent
from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen
from complira_graph.models.regulatory import (
    RegulatoryFramework,
    NormativeRequirement,
    RequirementIdentity,
    RequirementContent,
    RequirementClassification,
    RequirementHierarchy,
    RequirementProvenance,
    EvidenceSpecification,
    EvidenceRequirement,
)


class NISTSSDFAgent(BaseIngestionAgent):
    """
    NIST SSDF (Secure Software Development Framework) ingestion agent.

    The SSDF is a set of fundamental, sound, and secure software development
    practices based on established secure software development practice documents.

    Data Source:
        URL: https://raw.githubusercontent.com/usnistgov/SSDF/main/ssdf-v1.1.json
        Format: JSON with practices and tasks
        Structure: {"practices": [{"practice_group": "PO", "practice": "1", "name": "...", "tasks": [...]}]}

    Collections Populated:
        - regulatory_frameworks: Framework metadata
        - regulatory_requirements: Practices and tasks
        - requirement_hierarchy: Practice → Task edges

    Checkpoint Support:
        Enabled with interval of 10 practices to support resume on failure.
    """

    # Data source configuration
    # NOTE: The official NIST SSDF data is available in multiple formats:
    # 1. CycloneDX format: https://github.com/CycloneDX/official-3rd-party-standards
    # 2. Excel/CSV from NIST: https://csrc.nist.gov/projects/ssdf
    # 3. Custom JSON (if we create our own from the official PDF/Excel)
    # For now, using a placeholder URL - in production, this would point to actual structured data
    SSDF_JSON_URL = "https://raw.githubusercontent.com/CycloneDX/official-3rd-party-standards/main/standards/NIST/SSDF/nist_secure-software-development-framework_1.1.cdx.json"

    # Checkpoint configuration
    supports_checkpointing = True
    checkpoint_interval = 10  # Save every 10 practices

    def _get_primary_collection(self) -> str:
        """Get primary collection name for this agent."""
        return "regulatory_requirements"

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch NIST SSDF structured data from GitHub.

        Returns:
            List[Dict[str, Any]]: List of practice dictionaries (LSP compliant)

        Raises:
            requests.RequestException: On network or HTTP errors

        Note:
            Returns List[dict] not dict - this is LSP compliance fix!
            All agents must return same type for substitutability.
        """
        self.logger.info("Fetching NIST SSDF from GitHub", url=self.SSDF_JSON_URL)

        # Check for checkpoint to resume from
        checkpoint = self._load_checkpoint()
        start_index = 0
        if checkpoint:
            start_index = checkpoint.get("processed_practices", 0)
            self.logger.info(
                "Resuming from checkpoint",
                start_index=start_index
            )

        try:
            response = requests.get(self.SSDF_JSON_URL, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract practices
            practices = data.get("practices", [])

            if not practices:
                self.logger.warning("No practices found in SSDF JSON")
                return []

            # If resuming, skip already processed practices
            if start_index > 0:
                practices = practices[start_index:]
                self.logger.info(
                    "Skipping already processed practices",
                    skipped=start_index,
                    remaining=len(practices)
                )

            self.logger.info(
                "Fetched NIST SSDF",
                practices_count=len(practices),
                total_expected=len(data.get("practices", []))
            )

            # Return as list (LSP compliance)
            return practices

        except requests.RequestException as e:
            self.logger.error("Failed to fetch NIST SSDF", error=str(e))
            raise
        except Exception as e:
            self.logger.error("Unexpected error fetching NIST SSDF", error=str(e))
            raise

    def transform_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform NIST SSDF practices to graph nodes and edges.

        This method creates:
        1. One RegulatoryFramework document (NIST_SSDF)
        2. NormativeRequirement documents for each practice
        3. NormativeRequirement documents for each task
        4. RequirementHierarchy edges linking practices to tasks

        Args:
            raw_data: List of practice dicts from fetch_data()

        Returns:
            List of documents (frameworks + requirements + edges)

        Note:
            Saves checkpoints every 10 practices for resume support.
        """
        documents = []
        edges = []

        # Create regulatory framework document (using SOLID model)
        framework = RegulatoryFramework(
            key="NIST_SSDF",
            name="NIST Secure Software Development Framework",
            short_name="NIST SSDF",
            jurisdiction="US",
            issuing_body="NIST",
            document_type="framework",
            version="v1.1",
            publication_date=date(2022, 2, 4),
            effective_date=date(2022, 2, 4),
            source_url="https://csrc.nist.gov/publications/detail/sp/800-218/final",
            source_format="json",
            machine_readable=True,
            applicability={
                "product_types": ["software", "firmware"],
                "sectors": ["all"],
                "organization_types": ["software_publishers", "third_party_developers", "in_house_developers"]
            },
            status="in_force",
            ingestion_method="oscal_import"
        )

        documents.append({
            "_collection": "regulatory_frameworks",
            **framework.to_arango_doc()
        })

        self.logger.info("Created NIST SSDF framework document")

        # Get checkpoint resume point
        checkpoint = self._load_checkpoint()
        processed_count = checkpoint.get("processed_practices", 0) if checkpoint else 0

        # Transform practices to requirements
        for practice_idx, practice in enumerate(raw_data):
            practice_group = practice.get("practice_group", "")  # PO, PS, PW, RV
            practice_id = practice.get("practice", "")  # 1, 2, 3
            practice_name = practice.get("name", "")
            practice_description = practice.get("description", "")

            # ✅ DRY: Use RegulatoryKeyGenerator instead of duplicating logic
            practice_key = KeyGen.nist_ssdf(practice_group, practice_id)

            # ✅ SOLID: Use NormativeRequirement with composition (SRP)
            practice_req = NormativeRequirement(
                identity=RequirementIdentity(
                    key=practice_key,
                    requirement_id=f"{practice_group}.{practice_id}",
                    framework="NIST_SSDF"
                ),
                hierarchy=RequirementHierarchy(
                    parent_key=None,  # Top-level practice
                    depth=1,
                    children_count=len(practice.get("tasks", []))
                ),
                content=RequirementContent(
                    title=practice_name,
                    text=practice_description if practice_description else practice_name
                ),
                classification=RequirementClassification(
                    requirement_type="procedural",
                    obligation_level="should",
                    applies_to=["manufacturer", "developer"],
                    product_scope=["software", "firmware"]
                ),
                provenance=RequirementProvenance(
                    source="oscal_import",
                    confidence=1.0,
                    curator="NISTSSDFAgent",
                    version="v1.1"
                )
            )

            # Convert to ArangoDB doc (backward compatible)
            documents.append({
                "_collection": "regulatory_requirements",
                **practice_req.to_arango_doc()
            })

            # Process tasks (children of practices)
            tasks = practice.get("tasks", [])
            for task in tasks:
                task_id = task.get("task", "")  # 1, 2, 3
                task_description = task.get("description", "")

                # ✅ DRY: Consistent key generation
                task_key = KeyGen.nist_ssdf(practice_group, practice_id, task_id)

                # ✅ SOLID: Use NormativeRequirement
                task_req = NormativeRequirement(
                    identity=RequirementIdentity(
                        key=task_key,
                        requirement_id=f"{practice_group}.{practice_id}.{task_id}",
                        framework="NIST_SSDF"
                    ),
                    hierarchy=RequirementHierarchy(
                        parent_key=practice_key,  # Parent is the practice
                        depth=2,
                        children_count=0
                    ),
                    content=RequirementContent(
                        title=f"Task {task_id}",
                        text=task_description
                    ),
                    classification=RequirementClassification(
                        requirement_type="procedural",
                        obligation_level="should",
                        applies_to=["manufacturer", "developer"],
                        product_scope=["software", "firmware"]
                    ),
                    evidence=self._infer_evidence_types(task_description),
                    provenance=RequirementProvenance(
                        source="oscal_import",
                        confidence=1.0,
                        curator="NISTSSDFAgent",
                        version="v1.1"
                    )
                )

                documents.append({
                    "_collection": "regulatory_requirements",
                    **task_req.to_arango_doc()
                })

                # Create hierarchy edge (practice → task)
                edges.append({
                    "_collection": "requirement_hierarchy",
                    "_from": f"regulatory_requirements/{practice_key}",
                    "_to": f"regulatory_requirements/{task_key}",
                    "relationship": "contains",
                    "order": int(task_id) if task_id.isdigit() else 0
                })

            # Save checkpoint every N practices
            if (practice_idx + 1) % self.checkpoint_interval == 0:
                self._save_checkpoint({
                    "processed_practices": processed_count + practice_idx + 1,
                    "total_practices": processed_count + len(raw_data)
                })

        self.logger.info(
            "Transformed NIST SSDF",
            documents=len(documents),
            edges=len(edges),
            practices=len(raw_data)
        )

        return documents + edges

    def _infer_evidence_types(self, task_description: str) -> Optional[EvidenceSpecification]:
        """
        Infer evidence types from task description using keyword matching.

        This is a simple heuristic-based approach. In production, you might use
        an LLM for more sophisticated inference.

        Args:
            task_description: Task description text

        Returns:
            EvidenceSpecification with inferred evidence types, or None if no evidence detected

        Examples:
            >>> agent._infer_evidence_types("Generate SBOM for all components")
            EvidenceSpecification(evidence_types=[EvidenceRequirement(type="SBOM", ...)])

            >>> agent._infer_evidence_types("Perform static analysis using SAST tools")
            EvidenceSpecification(evidence_types=[EvidenceRequirement(type="SAST", ...)])
        """
        if not task_description:
            return None

        evidence_types = []
        description_lower = task_description.lower()

        # SBOM detection
        if any(keyword in description_lower for keyword in ["sbom", "bill of materials", "software composition"]):
            evidence_types.append(EvidenceRequirement(
                type="SBOM",
                format="CycloneDX 1.6 | SPDX 2.3",
                required=True,
                description="Software Bill of Materials documenting all software components",
                scanner_tools=["syft", "cdxgen", "trivy"],
                validation_spec={
                    "collection": "sbom_artifacts",
                    "filters": {"tenant_id": "@tenant"},
                    "aggregation": "exists"
                }
            ))

        # SAST detection
        if any(keyword in description_lower for keyword in ["static analysis", "sast", "source code analysis", "static application security"]):
            evidence_types.append(EvidenceRequirement(
                type="SAST",
                required=True,
                description="Static Application Security Testing findings",
                scanner_tools=["semgrep", "bandit", "flawfinder", "gosec"],
                validation_spec={
                    "collection": "sast_findings",
                    "filters": {"tenant_id": "@tenant"},
                    "aggregation": "exists"
                }
            ))

        # DAST detection
        if any(keyword in description_lower for keyword in ["dynamic analysis", "dast", "runtime testing", "dynamic application security"]):
            evidence_types.append(EvidenceRequirement(
                type="DAST",
                required=True,
                description="Dynamic Application Security Testing findings",
                scanner_tools=["zap", "burp"],
                validation_spec={
                    "collection": "dast_findings",
                    "filters": {"tenant_id": "@tenant"},
                    "aggregation": "exists"
                }
            ))

        # Dependency scanning
        if any(keyword in description_lower for keyword in ["dependency", "third-party", "open source", "vulnerability scan"]):
            evidence_types.append(EvidenceRequirement(
                type="dependency_scan",
                required=True,
                description="Third-party dependency vulnerability scan",
                scanner_tools=["trivy", "grype", "osv-scanner"],
                validation_spec={
                    "collection": "vulnerability_scans",
                    "filters": {"tenant_id": "@tenant", "scan_type": "dependency"},
                    "aggregation": "exists"
                }
            ))

        # Threat modeling
        if any(keyword in description_lower for keyword in ["threat model", "threat analysis", "attack surface", "stride"]):
            evidence_types.append(EvidenceRequirement(
                type="threat_model",
                required=True,
                description="Threat model documenting potential attack vectors",
                manual_attestation=True,
                validation_spec={
                    "collection": "threat_models",
                    "filters": {"tenant_id": "@tenant"},
                    "aggregation": "exists"
                }
            ))

        # Security testing
        if any(keyword in description_lower for keyword in ["security test", "penetration test", "pen test", "security assessment"]):
            evidence_types.append(EvidenceRequirement(
                type="security_testing",
                required=True,
                description="Security testing and penetration testing results",
                manual_attestation=True,
                validation_spec={
                    "collection": "test_results",
                    "filters": {"tenant_id": "@tenant", "test_type": "security"},
                    "aggregation": "exists"
                }
            ))

        # Return EvidenceSpecification if evidence types were found
        if evidence_types:
            # Determine testability based on evidence types
            has_manual = any(ev.manual_attestation for ev in evidence_types)
            has_automated = any(not ev.manual_attestation for ev in evidence_types)

            if has_automated and has_manual:
                testability = "semi_automated"
            elif has_automated:
                testability = "automated"
            else:
                testability = "manual_only"

            return EvidenceSpecification(
                evidence_types=evidence_types,
                testability=testability,
                verification_method="test" if testability == "automated" else "analysis"
            )

        return None

    def run(self) -> dict:
        """
        Execute full NIST SSDF ingestion workflow with multi-collection support.

        This override handles loading data into multiple collections:
        - regulatory_frameworks
        - regulatory_requirements
        - requirement_hierarchy

        Returns:
            dict: Execution statistics with breakdown by collection
        """
        from datetime import datetime

        start_time = datetime.now()

        self.logger.info("NIST SSDF agent execution started")

        try:
            # Step 1: Fetch
            self.logger.info("Fetching NIST SSDF data")
            raw_data = self.fetch_data()

            if not raw_data:
                self.logger.warning("No data fetched, aborting")
                return {
                    "agent": self.agent_name,
                    "status": "success",
                    "execution_time_seconds": (datetime.now() - start_time).total_seconds(),
                    "created": 0,
                    "updated": 0,
                    "errors": 0,
                    "message": "No data to process"
                }

            # Step 2: Transform
            self.logger.info("Transforming NIST SSDF data")
            documents = self.transform_data(raw_data)

            # Step 3: Load into multiple collections
            self.logger.info("Loading NIST SSDF data into database")

            stats_by_collection = {}
            total_created = 0
            total_updated = 0
            total_errors = 0

            # Group documents by collection
            collections = {}
            for doc in documents:
                collection_name = doc.pop("_collection", self._get_primary_collection())
                if collection_name not in collections:
                    collections[collection_name] = []
                collections[collection_name].append(doc)

            # Load each collection
            for collection_name, docs in collections.items():
                self.logger.info(
                    "Loading collection",
                    collection=collection_name,
                    count=len(docs)
                )

                # Use generator to maintain consistency with base class
                def doc_generator():
                    for doc in docs:
                        yield doc

                stats = self.load_data(
                    doc_generator(),
                    collection_name,
                    on_duplicate="update"
                )

                stats_by_collection[collection_name] = stats
                total_created += stats.get("created", 0)
                total_updated += stats.get("updated", 0)
                total_errors += stats.get("errors", 0)

            execution_time = (datetime.now() - start_time).total_seconds()

            # Step 4: Clear checkpoint on success
            self._clear_checkpoint()

            result = {
                "agent": self.agent_name,
                "status": "success",
                "execution_time_seconds": execution_time,
                "created": total_created,
                "updated": total_updated,
                "errors": total_errors,
                "total": total_created + total_updated + total_errors,
                "collections": stats_by_collection
            }

            self.logger.info(
                "NIST SSDF agent execution completed",
                **result
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "NIST SSDF agent execution failed",
                error=str(e),
                execution_time_seconds=execution_time,
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": execution_time,
            }
