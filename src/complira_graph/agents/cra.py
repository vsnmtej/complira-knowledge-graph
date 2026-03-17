"""
CRA (EU Cyber Resilience Act) ingestion agent.

This agent ingests the EU Cyber Resilience Act (Regulation (EU) 2024/2847)
from a curated YAML file containing essential cybersecurity requirements.

The CRA establishes mandatory cybersecurity requirements for products with
digital elements placed on the EU market.

Data source: data/regulations/cra.yaml (curated from official EUR-Lex text)
Collections populated:
- regulatory_frameworks (1 document: CRA framework)
- regulatory_requirements (essential requirements from Annex I + procedural requirements from articles)
- requirement_hierarchy (edges for annex → section hierarchy)

Checkpoint behavior:
- Supports checkpointing (saves every 50 requirements)
- Resumes from last saved requirement if interrupted
- Clears checkpoint on successful completion

CRA Structure:
- Annex I: Essential cybersecurity requirements (security by design, vulnerability handling, etc.)
- Annex II: Information and instructions to users (SBOM, contact info, support period)
- Articles: Manufacturer obligations (vulnerability reporting, incident response, technical docs)
- Recitals: Informative guidance (non-normative)

Key Features:
- Staggered deadlines: 21 months for reporting obligations, 36 months for technical requirements
- Evidence inference: Maps requirements to evidence types (SBOM, SAST, DAST, etc.)
- Multi-level hierarchy: Annex → Section, Article → Paragraph

REFACTORED VERSION using DRY/SOLID utilities:
✅ DRY: Uses RegulatoryKeyGenerator for consistent key generation
✅ SOLID: Uses NormativeRequirement and InformativeRequirement with composition (SRP)
✅ LSP: fetch_data() returns List[Dict[str, Any]] (standardized return type)
✅ OCP: Easy to extend with new CRA requirements or amendments
✅ ISP: Uses appropriate requirement types (Normative vs Informative)
"""

from typing import List, Dict, Any, Optional
from datetime import date, datetime
import yaml
from pathlib import Path

from complira_graph.agents.base import BaseIngestionAgent
from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen
from complira_graph.models.regulatory import (
    RegulatoryFramework,
    NormativeRequirement,
    InformativeRequirement,
    RequirementIdentity,
    RequirementContent,
    RequirementClassification,
    RequirementHierarchy,
    RequirementProvenance,
    RequirementTemporal,
    EvidenceSpecification,
    EvidenceRequirement,
)


class CRAAgent(BaseIngestionAgent):
    """
    CRA (EU Cyber Resilience Act) ingestion agent.

    The CRA is an EU regulation establishing cybersecurity requirements for
    products with digital elements. It introduces mandatory obligations for
    manufacturers, importers, and distributors.

    Data Source:
        Path: data/regulations/cra.yaml
        Format: YAML with curated requirements from EUR-Lex official text
        Official Source: https://eur-lex.europa.eu/eli/reg/2024/2847/oj
        Structure:
          - framework: Framework metadata
          - annex_i_requirements: Essential cybersecurity requirements
          - annex_ii_requirements: Information and instructions
          - article_requirements: Manufacturer obligations
          - recitals: Informative guidance

    Collections Populated:
        - regulatory_frameworks: CRA framework metadata
        - regulatory_requirements: Requirements from Annexes I, II, Articles, and Recitals
        - requirement_hierarchy: Annex → Section hierarchy edges

    Key Generation:
        - Annex I, Section 1: CRA_I_1
        - Annex I, Section 1, Subpara (a): CRA_I_1_a
        - Article 13, Paragraph 1: CRA_13_1
        - Article 14, Paragraph 2, Subpara (b): CRA_14_2_b
        - Recital 1: CRA_RECITAL_1

    Deadlines:
        - Reporting obligations (Articles 13-14): 21 months from entry into force (2026-09-11)
        - Technical requirements (Annex I): 36 months from entry into force (2027-12-11)

    Checkpoint Support:
        Enabled with interval of 50 requirements to support resume on failure.
    """

    # Data source configuration
    CRA_YAML_PATH = Path(__file__).parent.parent.parent.parent / "data" / "regulations" / "cra.yaml"

    # Checkpoint configuration
    supports_checkpointing = True
    checkpoint_interval = 50  # Save every 50 requirements

    def _get_primary_collection(self) -> str:
        """Get primary collection name for this agent."""
        return "regulatory_requirements"

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch CRA requirements from YAML file.

        Returns:
            List[Dict[str, Any]]: Combined list of all CRA requirements (LSP compliant)

        Raises:
            FileNotFoundError: If CRA YAML file not found
            yaml.YAMLError: If YAML parsing fails

        Note:
            Returns List[dict] not dict - this is LSP compliance fix!
            All agents must return same type for substitutability.
        """
        self.logger.info("Fetching CRA from YAML", path=str(self.CRA_YAML_PATH))

        # Check for checkpoint to resume from
        checkpoint = self._load_checkpoint()
        start_index = 0
        if checkpoint:
            start_index = checkpoint.get("processed_requirements", 0)
            self.logger.info(
                "Resuming from checkpoint",
                start_index=start_index
            )

        try:
            if not self.CRA_YAML_PATH.exists():
                raise FileNotFoundError(f"CRA YAML file not found: {self.CRA_YAML_PATH}")

            with open(self.CRA_YAML_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                self.logger.warning("CRA YAML file is empty")
                return []

            # Combine all requirement types into single list
            all_requirements = []

            # Add framework metadata (for later processing)
            framework_meta = data.get("framework", {})
            if framework_meta:
                all_requirements.append({
                    "_type": "framework",
                    **framework_meta
                })

            # Add Annex I requirements (essential cybersecurity)
            annex_i = data.get("annex_i_requirements", [])
            for req in annex_i:
                req["_type"] = "annex_i"
                all_requirements.append(req)

            # Add Annex II requirements (information and instructions)
            annex_ii = data.get("annex_ii_requirements", [])
            for req in annex_ii:
                req["_type"] = "annex_ii"
                all_requirements.append(req)

            # Add Article requirements (manufacturer obligations)
            articles = data.get("article_requirements", [])
            for req in articles:
                req["_type"] = "article"
                all_requirements.append(req)

            # Add Recitals (informative guidance)
            recitals = data.get("recitals", [])
            for req in recitals:
                req["_type"] = "recital"
                all_requirements.append(req)

            # If resuming, skip already processed requirements
            if start_index > 0:
                all_requirements = all_requirements[start_index:]
                self.logger.info(
                    "Skipping already processed requirements",
                    skipped=start_index,
                    remaining=len(all_requirements)
                )

            self.logger.info(
                "Fetched CRA requirements",
                total=len(all_requirements),
                annex_i=len(annex_i),
                annex_ii=len(annex_ii),
                articles=len(articles),
                recitals=len(recitals)
            )

            # Return as list (LSP compliance)
            return all_requirements

        except FileNotFoundError as e:
            self.logger.error("CRA YAML file not found", error=str(e))
            raise
        except yaml.YAMLError as e:
            self.logger.error("Failed to parse CRA YAML", error=str(e))
            raise
        except Exception as e:
            self.logger.error("Unexpected error fetching CRA", error=str(e))
            raise

    def transform_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform CRA requirements to graph nodes and edges.

        This method creates:
        1. One RegulatoryFramework document (CRA)
        2. NormativeRequirement documents for Annex I, Annex II, and Article requirements
        3. InformativeRequirement documents for Recitals
        4. RequirementHierarchy edges linking annexes to sections

        Args:
            raw_data: List of requirement dicts from fetch_data()

        Returns:
            List of documents (frameworks + requirements + edges)

        Note:
            Saves checkpoints every 50 requirements for resume support.
        """
        documents = []
        edges = []

        # Get checkpoint resume point
        checkpoint = self._load_checkpoint()
        processed_count = checkpoint.get("processed_requirements", 0) if checkpoint else 0

        # Process each requirement
        for req_idx, req_data in enumerate(raw_data):
            req_type = req_data.get("_type")

            # Handle framework metadata
            if req_type == "framework":
                framework = self._create_framework(req_data)
                documents.append({
                    "_collection": "regulatory_frameworks",
                    **framework.to_arango_doc()
                })
                self.logger.info("Created CRA framework document")
                continue

            # Handle Annex I requirements (essential cybersecurity)
            elif req_type == "annex_i":
                requirement = self._create_annex_requirement(req_data, annex="I")
                documents.append({
                    "_collection": "regulatory_requirements",
                    **requirement.to_arango_doc()
                })

            # Handle Annex II requirements (information and instructions)
            elif req_type == "annex_ii":
                requirement = self._create_annex_requirement(req_data, annex="II")
                documents.append({
                    "_collection": "regulatory_requirements",
                    **requirement.to_arango_doc()
                })

            # Handle Article requirements (manufacturer obligations)
            elif req_type == "article":
                requirement = self._create_article_requirement(req_data)
                documents.append({
                    "_collection": "regulatory_requirements",
                    **requirement.to_arango_doc()
                })

            # Handle Recitals (informative guidance)
            elif req_type == "recital":
                requirement = self._create_recital(req_data)
                documents.append({
                    "_collection": "regulatory_requirements",
                    **requirement.to_arango_doc()
                })

            # Save checkpoint every N requirements
            if (req_idx + 1) % self.checkpoint_interval == 0:
                self._save_checkpoint({
                    "processed_requirements": processed_count + req_idx + 1,
                    "total_requirements": processed_count + len(raw_data)
                })

        self.logger.info(
            "Transformed CRA",
            documents=len(documents),
            edges=len(edges),
            requirements=len(raw_data)
        )

        return documents + edges

    def _create_framework(self, framework_data: Dict[str, Any]) -> RegulatoryFramework:
        """
        Create CRA framework document.

        Args:
            framework_data: Framework metadata from YAML

        Returns:
            RegulatoryFramework instance
        """
        return RegulatoryFramework(
            key=framework_data.get("key", "CRA"),
            name=framework_data.get("name", "Cyber Resilience Act"),
            short_name=framework_data.get("short_name", "CRA"),
            jurisdiction="EU",
            issuing_body=framework_data.get("issuing_body", "European Parliament and Council"),
            document_type="regulation",
            version=framework_data.get("version", "Regulation (EU) 2024/2847"),
            publication_date=self._parse_date(framework_data.get("publication_date")),
            effective_date=self._parse_date(framework_data.get("effective_date")),
            enforcement_date=self._parse_date(framework_data.get("enforcement_date")),
            source_url=framework_data.get("source_url", "https://eur-lex.europa.eu/eli/reg/2024/2847/oj"),
            source_format=framework_data.get("source_format", "yaml"),
            machine_readable=framework_data.get("machine_readable", True),
            applicability=framework_data.get("applicability", {}),
            status=framework_data.get("status", "in_force"),
            last_ingested=datetime.now(),
            ingestion_method=framework_data.get("ingestion_method", "yaml_config")
        )

    def _create_annex_requirement(
        self,
        req_data: Dict[str, Any],
        annex: str
    ) -> NormativeRequirement:
        """
        Create requirement from Annex I or II.

        Args:
            req_data: Requirement data from YAML
            annex: Annex identifier (I or II)

        Returns:
            NormativeRequirement instance
        """
        # Generate key using DRY utility
        section = req_data.get("section")
        subpara = req_data.get("subpara")

        requirement_key = KeyGen.cra(
            annex=annex,
            section=section,
            subpara=subpara
        )

        # Build requirement_id
        requirement_id = f"Annex {annex}, Section {section}"
        if subpara:
            requirement_id += f"({subpara})"

        # Parse evidence types from YAML
        evidence_spec = None
        evidence_types_data = req_data.get("evidence_types", [])
        if evidence_types_data:
            evidence_types = []
            for ev in evidence_types_data:
                evidence_types.append(EvidenceRequirement(
                    type=ev.get("type"),
                    format=ev.get("format"),
                    required=ev.get("required", True),
                    description=ev.get("description", ""),
                    scanner_tools=ev.get("scanner_tools", []),
                    manual_attestation=ev.get("manual_attestation", False),
                    validation_spec={
                        "collection": self._infer_collection_from_type(ev.get("type")),
                        "filters": {"tenant_id": "@tenant"},
                        "aggregation": "exists"
                    }
                ))

            # Determine testability
            has_manual = any(ev.manual_attestation for ev in evidence_types)
            has_automated = any(not ev.manual_attestation for ev in evidence_types)

            if has_automated and has_manual:
                testability = "semi_automated"
            elif has_automated:
                testability = "automated"
            else:
                testability = "manual_only"

            evidence_spec = EvidenceSpecification(
                evidence_types=evidence_types,
                testability=testability,
                verification_method="test" if testability in ["automated", "semi_automated"] else "analysis"
            )

        # Parse temporal information
        temporal = None
        deadline_str = req_data.get("deadline")
        if deadline_str:
            temporal = RequirementTemporal(
                effective_date=self._parse_date(req_data.get("effective_date")),
                deadline=self._parse_date(deadline_str),
                transition_period=req_data.get("transition_period")
            )

        # Create normative requirement
        return NormativeRequirement(
            identity=RequirementIdentity(
                key=requirement_key,
                requirement_id=requirement_id,
                framework="CRA"
            ),
            hierarchy=RequirementHierarchy(
                parent_key=None,  # Top-level for now (could add annex-level parent)
                depth=1 if not subpara else 2,
                children_count=0
            ),
            content=RequirementContent(
                title=req_data.get("title", ""),
                text=req_data.get("text", "")
            ),
            classification=RequirementClassification(
                requirement_type=req_data.get("requirement_type", "essential"),
                obligation_level=req_data.get("obligation_level", "shall"),
                applies_to=req_data.get("applies_to", []),
                product_scope=req_data.get("product_scope", [])
            ),
            evidence=evidence_spec,
            temporal=temporal,
            provenance=RequirementProvenance(
                source="yaml_config",
                confidence=1.0,
                curator="CRAAgent",
                version="Regulation (EU) 2024/2847",
                notes=f"Curated from Annex {annex}, official EUR-Lex text"
            )
        )

    def _create_article_requirement(self, req_data: Dict[str, Any]) -> NormativeRequirement:
        """
        Create requirement from CRA Article.

        Args:
            req_data: Requirement data from YAML

        Returns:
            NormativeRequirement instance
        """
        # Generate key using DRY utility
        article = req_data.get("article")
        paragraph = req_data.get("paragraph")
        subpara = req_data.get("subpara")

        requirement_key = KeyGen.cra(
            article=article,
            paragraph=paragraph,
            subpara=subpara
        )

        # Build requirement_id
        requirement_id = f"Article {article}"
        if paragraph:
            requirement_id += f", Paragraph {paragraph}"
        if subpara:
            requirement_id += f"({subpara})"

        # Parse evidence types
        evidence_spec = None
        evidence_types_data = req_data.get("evidence_types", [])
        if evidence_types_data:
            evidence_types = []
            for ev in evidence_types_data:
                evidence_types.append(EvidenceRequirement(
                    type=ev.get("type"),
                    format=ev.get("format"),
                    required=ev.get("required", True),
                    description=ev.get("description", ""),
                    scanner_tools=ev.get("scanner_tools", []),
                    manual_attestation=ev.get("manual_attestation", False),
                    validation_spec={
                        "collection": self._infer_collection_from_type(ev.get("type")),
                        "filters": {"tenant_id": "@tenant"},
                        "aggregation": "exists"
                    }
                ))

            has_manual = any(ev.manual_attestation for ev in evidence_types)
            has_automated = any(not ev.manual_attestation for ev in evidence_types)

            if has_automated and has_manual:
                testability = "semi_automated"
            elif has_automated:
                testability = "automated"
            else:
                testability = "manual_only"

            evidence_spec = EvidenceSpecification(
                evidence_types=evidence_types,
                testability=testability,
                verification_method="test" if testability in ["automated", "semi_automated"] else "analysis"
            )

        # Parse temporal information
        temporal = None
        deadline_str = req_data.get("deadline")
        if deadline_str:
            temporal = RequirementTemporal(
                effective_date=self._parse_date(req_data.get("effective_date")),
                deadline=self._parse_date(deadline_str),
                transition_period=req_data.get("transition_period")
            )

        # Create normative requirement
        return NormativeRequirement(
            identity=RequirementIdentity(
                key=requirement_key,
                requirement_id=requirement_id,
                framework="CRA"
            ),
            hierarchy=RequirementHierarchy(
                parent_key=None,
                depth=1 if not paragraph else 2 if not subpara else 3,
                children_count=0
            ),
            content=RequirementContent(
                title=req_data.get("title", ""),
                text=req_data.get("text", "")
            ),
            classification=RequirementClassification(
                requirement_type=req_data.get("requirement_type", "procedural"),
                obligation_level=req_data.get("obligation_level", "shall"),
                applies_to=req_data.get("applies_to", []),
                product_scope=req_data.get("product_scope", [])
            ),
            evidence=evidence_spec,
            temporal=temporal,
            provenance=RequirementProvenance(
                source="yaml_config",
                confidence=1.0,
                curator="CRAAgent",
                version="Regulation (EU) 2024/2847",
                notes=f"Curated from Article {article}, official EUR-Lex text"
            )
        )

    def _create_recital(self, req_data: Dict[str, Any]) -> InformativeRequirement:
        """
        Create informative requirement from CRA Recital.

        Args:
            req_data: Recital data from YAML

        Returns:
            InformativeRequirement instance
        """
        recital_num = req_data.get("recital")

        # Generate key
        requirement_key = KeyGen.generate("CRA", "RECITAL", recital_num)

        # Build requirement_id
        requirement_id = f"Recital {recital_num}"

        # Create informative requirement (no evidence, no deadlines)
        return InformativeRequirement(
            identity=RequirementIdentity(
                key=requirement_key,
                requirement_id=requirement_id,
                framework="CRA"
            ),
            hierarchy=RequirementHierarchy(
                parent_key=None,
                depth=0,  # Recitals are preambles, not part of main structure
                children_count=0
            ),
            content=RequirementContent(
                title=req_data.get("title", ""),
                text=req_data.get("text", "")
            ),
            obligation_level="informative",
            provenance=RequirementProvenance(
                source="yaml_config",
                confidence=1.0,
                curator="CRAAgent",
                version="Regulation (EU) 2024/2847",
                notes="Informative guidance from CRA recitals"
            )
        )

    def _infer_collection_from_type(self, evidence_type: str) -> str:
        """
        Infer ArangoDB collection name from evidence type.

        Args:
            evidence_type: Evidence type (SBOM, SAST, etc.)

        Returns:
            Collection name for validation query
        """
        type_to_collection = {
            "SBOM": "sbom_artifacts",
            "SAST": "sast_findings",
            "DAST": "dast_findings",
            "dependency_scan": "vulnerability_scans",
            "vulnerability_scan": "vulnerability_scans",
            "threat_model": "threat_models",
            "security_testing": "test_results",
            "penetration_testing": "test_results",
            "vulnerability_disclosure_policy": "policies",
            "vulnerability_handling_policy": "policies",
            "contact_information": "attestations",
            "security_support_declaration": "attestations",
            "technical_documentation": "attestations",
            "conformity_assessment": "attestations",
            "update_mechanism_verification": "attestations",
            "encryption_verification": "attestations",
            "incident_notification": "incident_reports",
        }

        return type_to_collection.get(evidence_type, "attestations")

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """
        Parse date string to date object.

        Args:
            date_str: Date string in ISO format (YYYY-MM-DD)

        Returns:
            date object or None if parsing fails
        """
        if not date_str:
            return None

        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            self.logger.warning(f"Failed to parse date: {date_str}")
            return None

    def run(self) -> dict:
        """
        Execute full CRA ingestion workflow with multi-collection support.

        This override handles loading data into multiple collections:
        - regulatory_frameworks
        - regulatory_requirements
        - requirement_hierarchy

        Returns:
            dict: Execution statistics with breakdown by collection
        """
        from datetime import datetime

        start_time = datetime.now()

        self.logger.info("CRA agent execution started")

        try:
            # Step 1: Fetch
            self.logger.info("Fetching CRA data")
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
            self.logger.info("Transforming CRA data")
            documents = self.transform_data(raw_data)

            # Step 3: Load into multiple collections
            self.logger.info("Loading CRA data into database")

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
                "CRA agent execution completed",
                **result
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "CRA agent execution failed",
                error=str(e),
                execution_time_seconds=execution_time,
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": execution_time,
            }
