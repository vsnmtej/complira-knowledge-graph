# Phase 3: VulnCheck Integration - Proposed Design

**Ticket:** phase-3-vulncheck-integration
**Stage:** 3 (Design Basis)
**Date:** 2026-03-03
**Status:** v1

---

## Design Overview

### Architecture Summary

Phase 3A integrates VulnCheck exploit intelligence into Complira's knowledge graph through 9 data ingestion agents, 6 new collections, 10 new edges, and extended enrichment capabilities.

**Key Components:**
1. **9 VulnCheck Agents** - Daily bulk sync + on-demand enrichment
2. **6 New Collections** - Ransomware, botnets, exploit intelligence, canary observations, exploit chains, EOL products
3. **10 New Edges** - Connect VulnCheck intelligence to existing graph (vulnerabilities, threat_groups, attack_techniques, regulatory_requirements)
4. **3 Repositories** - VulnCheckRepository, RegulatoryEdgeRepository, CanaryRepository
5. **2 Services** - VulnCheckEnrichmentService, RegulatoryTriggerService
6. **1 Endpoint Extension** - POST /v1/enrich (add VulnCheck intelligence fields)
7. **Regulatory Auto-Generation** - 4 high-confidence rules, suggestion system for lower-confidence

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     VulnCheck API (Community Tier)                      │
│  - /v3/backup/vulncheck-kev      - /v3/backup/ransomware              │
│  - /v3/backup/vulncheck-nvd2     - /v3/backup/botnets                 │
│  - /v3/index/exploits?cve={id}   - /v3/backup/threat-actors           │
│  - /v3/index/canaries            - /v3/backup/exploit-chains          │
│  - /v3/backup/eol                                                      │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         │ Bearer Token Auth, Rate Limit: 1000 req/min
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    9 VulnCheck Ingestion Agents                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 1. VulnCheckNVD2Agent - Sync vulncheck-nvd2 (244K CVEs, daily)  │  │
│  │ 2. VulnCheckKEVAgent - Sync vulncheck-kev (3.7K entries, daily) │  │
│  │ 3. VulnCheckExploitsAgent - Query exploits per CVE (on-demand)  │  │
│  │ 4. VulnCheckRansomwareAgent - Sync ransomware (50-100, daily)   │  │
│  │ 5. VulnCheckBotnetsAgent - Sync botnets (30-50, daily)          │  │
│  │ 6. VulnCheckThreatActorsAgent - Sync threat-actors (daily)      │  │
│  │ 7. VulnCheckExploitChainsAgent - Sync chains (20-40, daily)     │  │
│  │ 8. VulnCheckEOLAgent - Sync EOL products (1.5-2K, daily)        │  │
│  │ 9. VulnCheckCanariesAgent - Sync canaries (daily, pending verify)│ │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Pattern: BaseAgent → API fetch → streaming parser → batch upsert     │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         │ Documents + Edges (atomic)
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  ArangoDB Knowledge Graph (Reference DB)                │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ NEW: 6 Document Collections                                       │ │
│  │  - ransomware_families (50-100 docs)                              │ │
│  │  - botnets (30-50 docs)                                           │ │
│  │  - exploit_intelligence (10K+ docs, on-demand)                    │ │
│  │  - canary_observations (TBD, pending verification)                │ │
│  │  - exploit_chains (20-40 docs)                                    │ │
│  │  - eol_products (1.5-2K docs)                                     │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ NEW: 10 Edge Collections                                          │ │
│  │  - has_exploit_intelligence (vulnerabilities → exploit_intelligence)│ │
│  │  - exploited_by_ransomware (vulnerabilities → ransomware_families)│ │
│  │  - exploited_by_botnet (vulnerabilities → botnets)                │ │
│  │  - exploited_by_threat_actor (vulnerabilities → threat_groups)    │ │
│  │  - observed_by_canary (vulnerabilities → canary_observations)     │ │
│  │  - chain_includes_vuln (exploit_chains → vulnerabilities)         │ │
│  │  - component_eol_status (components → eol_products)               │ │
│  │  - ransomware_uses_technique (ransomware_families → attack_techniques)│ │
│  │  - botnet_uses_technique (botnets → attack_techniques)            │ │
│  │  - vuln_triggers_requirement (vulnerabilities → regulatory_requirements)│ │
│  └───────────────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ ENRICHED: Existing Collections                                    │ │
│  │  - vulnerabilities (add vc_ssvc_*, vc_vulnerable_cpes, etc.)      │ │
│  │  - vulncheck_kev_entries (populate 3.7K+ entries)                 │ │
│  │  - threat_groups (add vc_cve_references)                          │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         │ Graph Queries
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Repository Layer (3 New)                            │
│  - VulnCheckRepository (query exploit intelligence, ransomware, etc.)  │
│  - RegulatoryEdgeRepository (create vuln_triggers_requirement edges)   │
│  - CanaryRepository (query canary observations)                        │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         │ Pydantic Models
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Service Layer (2 New)                              │
│  - VulnCheckEnrichmentService (orchestrate VulnCheck intelligence)     │
│  - RegulatoryTriggerService (auto-generate regulatory edges)           │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         │ Extended EnrichedFinding Model
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  API Endpoint (Extended from Phase 2)                   │
│                     POST /v1/enrich                                     │
│  Request: {scan_session_id, include_vulncheck_intelligence: true}      │
│  Response: EnrichedFinding + exploit_intelligence + ransomware +       │
│            botnets + canary_observations + chains + regulatory_impact  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Designs (9 Agents)

### Agent 1: VulnCheckNVD2Agent

**Purpose:** Sync VulnCheck's enriched NVD data (SSVC, CPE, CAPEC, ATT&CK)

**Source:** `/v3/backup/vulncheck-nvd2` (244,866+ CVEs)

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
```python
class VulnCheckNVD2Agent(BaseAgent):
    """Sync VulnCheck NVD2 enrichment data to vulnerabilities collection."""

    def __init__(self, db, api_token):
        super().__init__(db)
        self.api_token = api_token
        self.endpoint = "https://api.vulncheck.com/v3/backup/vulncheck-nvd2"

    def run(self):
        """
        Main sync flow:
        1. Fetch backup endpoint (streaming JSON parser for large response)
        2. Extract VulnCheck enrichment fields per CVE
        3. Upsert to vulnerabilities collection (enrich existing docs)
        4. Return sync stats
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}

        # Streaming JSON parser (ijson) for large response (~500MB-1GB)
        response = requests.get(self.endpoint, headers=headers, stream=True)
        response.raise_for_status()

        parser = ijson.items(response.raw, "data.item")
        batch = []
        batch_size = 1000
        total_enriched = 0

        for cve_data in parser:
            enrichment = self._extract_enrichment(cve_data)
            batch.append(enrichment)

            if len(batch) >= batch_size:
                self._batch_upsert(batch)
                total_enriched += len(batch)
                self.logger.info(f"Enriched {total_enriched} CVEs")
                batch = []

        # Final batch
        if batch:
            self._batch_upsert(batch)
            total_enriched += len(batch)

        return {"total_enriched": total_enriched}

    def _extract_enrichment(self, cve_data):
        """
        Extract VulnCheck enrichment fields from API response.

        Returns dict to merge into existing vulnerabilities document:
        {
            "_key": "CVE-2024-1234",
            "vc_ssvc_exploitation": "active",
            "vc_ssvc_automatable": "yes",
            "vc_ssvc_technical_impact": "total",
            "vc_vulnerable_cpes": ["cpe:2.3:..."],
            "vc_related_attack_patterns": [{"capec_id": "CAPEC-123", ...}],
            "vc_attack_techniques": [{"technique_id": "T1190", ...}],
            "vc_categories": ["ICS/OT", "IoMT"],
            "vc_status": "Analyzed",
            "vc_enriched": True,
            "vc_enriched_at": datetime.utcnow(),
            "cpe_source": "vulncheck"  # Preferred over NVD
        }
        """
        return {
            "_key": cve_data["cve"],
            "vc_ssvc_exploitation": cve_data.get("vcSSVC", {}).get("exploitation"),
            "vc_ssvc_automatable": cve_data.get("vcSSVC", {}).get("automatable"),
            "vc_ssvc_technical_impact": cve_data.get("vcSSVC", {}).get("technicalImpact"),
            "vc_vulnerable_cpes": cve_data.get("vcVulnerableCPEs", []),
            "vc_related_attack_patterns": cve_data.get("vcCAPECs", []),
            "vc_attack_techniques": cve_data.get("vcATTACKs", []),
            "vc_categories": cve_data.get("vcCategories", []),
            "vc_status": cve_data.get("vcStatus"),
            "vc_enriched": True,
            "vc_enriched_at": datetime.utcnow().isoformat(),
            "cpe_source": "vulncheck" if cve_data.get("vcVulnerableCPEs") else "nvd",
        }

    def _batch_upsert(self, batch):
        """Upsert batch to vulnerabilities collection (merge enrichment fields)."""
        collection = self.db.collection("vulnerabilities")

        # AQL upsert query (UPSERT = INSERT or UPDATE)
        query = """
        FOR doc IN @batch
            UPSERT {_key: doc._key}
            INSERT MERGE(doc, {source: "nvd+vulncheck"})
            UPDATE MERGE(KEEP(CURRENT, ATTRIBUTES(CURRENT)), doc)
            IN vulnerabilities
        """

        self.db.aql.execute(query, bind_vars={"batch": batch})
```

**Error Handling:**
- Retry on 429 (rate limit) with exponential backoff
- Log and skip malformed CVE data (don't fail entire sync)
- Resume capability (track last synced CVE, resume from there if interrupted)

**Expected Output:**
- Enriched 244,866 CVEs with VulnCheck SSVC, CPE, CAPEC, ATT&CK
- Execution time: ~15-20 minutes (streaming + batch upsert)

---

### Agent 2: VulnCheckKEVAgent

**Purpose:** Populate vulncheck_kev_entries collection

**Source:** `/v3/backup/vulncheck-kev` (3,700+ entries)

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
```python
class VulnCheckKEVAgent(BaseAgent):
    """Sync VulnCheck KEV catalog to vulncheck_kev_entries collection."""

    def run(self):
        """
        Main sync flow:
        1. Fetch /v3/backup/vulncheck-kev
        2. Parse KEV entries
        3. Calculate lead_time_days vs CISA KEV
        4. Create documents + edges (has_exploit_intelligence, vuln_triggers_requirement)
        5. Return sync stats
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = requests.get(
            "https://api.vulncheck.com/v3/backup/vulncheck-kev",
            headers=headers
        )
        response.raise_for_status()

        data = response.json()
        kev_entries = data["data"]

        # Fetch CISA KEV for comparison (check if VulnCheck discovered first)
        cisa_kev_map = self._get_cisa_kev_map()

        documents = []
        edges = []

        for entry in kev_entries:
            doc = self._create_kev_document(entry, cisa_kev_map)
            documents.append(doc)

            # Create has_exploit_intelligence edge
            edges.append({
                "_from": f"vulnerabilities/{entry['cve']}",
                "_to": f"vulncheck_kev_entries/{entry['cve']}",
                "source": "vulncheck_kev",
                "synced_at": datetime.utcnow().isoformat(),
            })

        # Batch upsert
        self.db.collection("vulncheck_kev_entries").import_bulk(documents, on_duplicate="replace")
        self.db.collection("exploited_in_wild").import_bulk(edges, on_duplicate="ignore")

        return {
            "total_kev_entries": len(documents),
            "vulncheck_first_discoveries": sum(1 for d in documents if d.get("vulncheck_first")),
        }

    def _create_kev_document(self, entry, cisa_kev_map):
        """
        Create vulncheck_kev_entries document with lead time calculation.

        Returns:
        {
            "_key": "CVE-2024-1234",
            "cve_id": "CVE-2024-1234",
            "vendor_project": "Vendor Name",
            "product": "Product Name",
            "short_description": "...",
            "date_added": "2024-06-01T00:00:00Z",
            "known_ransomware_campaign_use": "Known",
            "exploitation_evidence": [{"url": "...", "date_added": "..."}],
            "in_cisa_kev": True,
            "vulncheck_first": True,
            "lead_time_days": 28,  # VulnCheck added 28 days before CISA
            "source": "vulncheck",
            "last_synced": "2024-06-20T12:00:00Z"
        }
        """
        cve_id = entry["cve"]
        vc_date_added = datetime.fromisoformat(entry["dateAdded"].rstrip("Z"))

        # Check CISA KEV
        cisa_entry = cisa_kev_map.get(cve_id)
        in_cisa_kev = cisa_entry is not None
        vulncheck_first = False
        lead_time_days = 0

        if in_cisa_kev:
            cisa_date_added = datetime.fromisoformat(cisa_entry["dateAdded"].rstrip("Z"))
            if vc_date_added < cisa_date_added:
                vulncheck_first = True
                lead_time_days = (cisa_date_added - vc_date_added).days
        else:
            vulncheck_first = True  # Only in VulnCheck KEV

        return {
            "_key": cve_id,
            "cve_id": cve_id,
            "vendor_project": entry.get("vendorProject"),
            "product": entry.get("product"),
            "short_description": entry.get("shortDescription"),
            "date_added": entry["dateAdded"],
            "known_ransomware_campaign_use": entry.get("knownRansomwareCampaignUse", "Unknown"),
            "exploitation_evidence": [
                {"url": ref["url"], "date_added": entry["dateAdded"]}
                for ref in entry.get("references", [])
            ],
            "in_cisa_kev": in_cisa_kev,
            "vulncheck_first": vulncheck_first,
            "lead_time_days": lead_time_days,
            "source": "vulncheck",
            "last_synced": datetime.utcnow().isoformat(),
        }

    def _get_cisa_kev_map(self):
        """Fetch existing CISA KEV entries for comparison."""
        query = "FOR k IN kev_entries RETURN {cve_id: k.cve_id, dateAdded: k.date_added}"
        cursor = self.db.aql.execute(query)
        return {entry["cve_id"]: entry for entry in cursor}
```

**Regulatory Edge Auto-Generation:**
After upserting KEV entries, trigger `RegulatoryTriggerService` to auto-generate `vuln_triggers_requirement` edges for all VulnCheck KEV CVEs.

**Expected Output:**
- 3,700+ KEV entries populated
- ~2,200 VulnCheck-first discoveries (28-day average lead time)
- 3,700+ `exploited_in_wild` edges created
- 3,700+ `vuln_triggers_requirement` edges auto-generated

---

### Agent 3: VulnCheckExploitsAgent

**Purpose:** On-demand exploit intelligence per CVE

**Source:** `/v3/index/exploits?cve={cve_id}` (10,480+ CVEs with exploits)

**Schedule:** On-demand (triggered during POST /v1/enrich)

**Implementation:**
```python
class VulnCheckExploitsAgent(BaseAgent):
    """Query exploit intelligence for a specific CVE (on-demand)."""

    def enrich_cve(self, cve_id: str) -> Optional[ExploitIntelligence]:
        """
        Fetch exploit intelligence for a single CVE.

        Returns:
            ExploitIntelligence Pydantic model or None if no data
        """
        # Check cache first (avoid redundant API calls)
        cached = self._check_cache(cve_id)
        if cached:
            return cached

        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = requests.get(
            f"https://api.vulncheck.com/v3/index/exploits?cve={cve_id}",
            headers=headers
        )

        if response.status_code == 404:
            return None  # No exploit intelligence for this CVE

        response.raise_for_status()
        data = response.json()["data"]

        if not data:
            return None

        exploit_intel = data[0]  # Single record per CVE

        # Create exploit_intelligence document
        doc = self._create_exploit_intelligence_doc(cve_id, exploit_intel)

        # Upsert to database
        self.db.collection("exploit_intelligence").insert(doc, overwrite=True)

        # Create has_exploit_intelligence edge
        self.db.collection("has_exploit_intelligence").insert({
            "_from": f"vulnerabilities/{cve_id}",
            "_to": f"exploit_intelligence/{cve_id}",
            "max_exploit_maturity": doc["max_exploit_maturity"],
            "reported_exploited": doc["reported_exploited"],
            "source": "vulncheck",
        }, overwrite=True)

        # Trigger regulatory edge auto-generation if actively exploited
        if doc["reported_exploited"]:
            self._trigger_regulatory_edges(cve_id, doc)

        return ExploitIntelligence(**doc)

    def _create_exploit_intelligence_doc(self, cve_id, exploit_intel):
        """
        Create exploit_intelligence document from API response.

        Schema matches AC-004 requirements:
        - Boolean flags (public_exploit_found, weaponized_exploit_found, etc.)
        - Timeline (nvd_published, first_exploit_published, etc.)
        - Exploit references with maturity classification
        """
        return {
            "_key": cve_id,
            "cve_id": cve_id,
            # Boolean flags
            "public_exploit_found": exploit_intel.get("publicExploitFound", False),
            "commercial_exploit_found": exploit_intel.get("commercialExploitFound", False),
            "weaponized_exploit_found": exploit_intel.get("weaponizedExploitFound", False),
            "max_exploit_maturity": exploit_intel.get("maxExploitMaturity", "unreported"),
            "reported_exploited": exploit_intel.get("reportedExploited", False),
            "reported_exploited_by_honeypot_service": exploit_intel.get("reportedExploitedByHoneypotService", False),
            "reported_exploited_by_vulncheck_canaries": exploit_intel.get("reportedExploitedByVulnCheckCanaries", False),
            "reported_exploited_by_threat_actors": exploit_intel.get("reportedExploitedByThreatActors", False),
            "reported_exploited_by_ransomware": exploit_intel.get("reportedExploitedByRansomware", False),
            "reported_exploited_by_botnets": exploit_intel.get("reportedExploitedByBotnets", False),
            "in_cisa_kev": exploit_intel.get("inKEV", False),
            "in_vulncheck_kev": exploit_intel.get("inVCKEV", False),
            # Timeline
            "timeline": {
                "nvd_published": exploit_intel.get("nvdPublishedDate"),
                "nvd_last_modified": exploit_intel.get("nvdLastModifiedDate"),
                "first_exploit_published": exploit_intel.get("firstExploitPublishedDate"),
                "first_exploit_published_weaponized_or_higher": exploit_intel.get("firstExploitPublishedWeaponizedOrHigherDate"),
                "most_recent_exploit_published": exploit_intel.get("mostRecentExploitPublishedDate"),
                "first_reported_threat_actor": exploit_intel.get("firstReportedThreatActorDate"),
                "most_recent_reported_threat_actor": exploit_intel.get("mostRecentReportedThreatActorDate"),
                "first_reported_ransomware": exploit_intel.get("firstReportedRansomwareDate"),
                "most_recent_reported_ransomware": exploit_intel.get("mostRecentReportedRansomwareDate"),
                "first_reported_botnet": exploit_intel.get("firstReportedBotnetDate"),
                "most_recent_reported_botnet": exploit_intel.get("mostRecentReportedBotnetDate"),
            },
            # Individual exploit references
            "exploits": exploit_intel.get("exploits", []),
            "source": "vulncheck",
            "last_synced": datetime.utcnow().isoformat(),
        }
```

**Rate Limiting:**
- Community tier: 1,000 req/min
- Batch CVE enrichment requests (e.g., enrich 100 CVEs during POST /v1/enrich)
- Queue requests to avoid rate limit exhaustion

**Expected Output:**
- Exploit intelligence for requested CVE
- `exploit_intelligence` document created
- `has_exploit_intelligence` edge created
- Regulatory edges auto-generated if actively exploited

---

### Agent 4: VulnCheckRansomwareAgent

**Purpose:** Sync ransomware family CVE attribution

**Source:** `/v3/backup/ransomware` (50-100 families)

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
```python
class VulnCheckRansomwareAgent(BaseAgent):
    """Sync ransomware families with CVE attribution."""

    def run(self):
        """
        Main sync flow:
        1. Fetch /v3/backup/ransomware
        2. Create ransomware_families documents
        3. Create exploited_by_ransomware edges (M:N, CVE → ransomware)
        4. Create ransomware_uses_technique edges (M:N, ransomware → ATT&CK)
        5. Return sync stats
        """
        response = requests.get(
            "https://api.vulncheck.com/v3/backup/ransomware",
            headers={"Authorization": f"Bearer {self.api_token}"}
        )
        response.raise_for_status()

        data = response.json()["data"]

        documents = []
        cve_edges = []
        technique_edges = []

        for family in data:
            # Create ransomware_families document
            doc = {
                "_key": self._slugify(family["family"]),
                "family_name": family["family"],
                "aliases": family.get("aliases", []),
                "malpedia_url": family.get("malpediaUrl"),
                "first_seen": family.get("firstSeen"),
                "last_seen": family.get("lastSeen"),
                "cve_count": len(family.get("cveReferences", [])),
                "cve_references": family.get("cveReferences", []),
                "ttps": family.get("ttps", []),
                "source": "vulncheck",
                "last_synced": datetime.utcnow().isoformat(),
            }
            documents.append(doc)

            # Create exploited_by_ransomware edges (CVE → ransomware)
            for cve_ref in family.get("cveReferences", []):
                for cve_id in cve_ref.get("cve", []):
                    cve_edges.append({
                        "_from": f"vulnerabilities/{cve_id}",
                        "_to": f"ransomware_families/{doc['_key']}",
                        "first_reported": cve_ref.get("dateAdded"),
                        "most_recent_reported": family.get("lastSeen"),
                        "evidence_urls": [cve_ref.get("url")],
                        "source": "vulncheck",
                    })

            # Create ransomware_uses_technique edges (ransomware → ATT&CK)
            for ttp in family.get("ttps", []):
                technique_edges.append({
                    "_from": f"ransomware_families/{doc['_key']}",
                    "_to": f"attack_techniques/{ttp}",
                    "technique_id": ttp,
                    "evidence_urls": [family.get("malpediaUrl")],
                    "source": "vulncheck",
                })

        # Batch upsert
        self.db.collection("ransomware_families").import_bulk(documents, on_duplicate="replace")
        self.db.collection("exploited_by_ransomware").import_bulk(cve_edges, on_duplicate="replace")
        self.db.collection("ransomware_uses_technique").import_bulk(technique_edges, on_duplicate="ignore")

        # Trigger regulatory edge auto-generation for ransomware CVEs
        ransomware_cve_ids = set(edge["_from"].split("/")[1] for edge in cve_edges)
        self._trigger_regulatory_edges(ransomware_cve_ids, trigger="ransomware")

        return {
            "total_families": len(documents),
            "total_cve_attributions": len(cve_edges),
            "total_ttp_mappings": len(technique_edges),
        }

    def _slugify(self, name):
        """Convert family name to _key (e.g., 'LockBit 3.0' → 'lockbit-3')."""
        return name.lower().replace(" ", "-").replace(".", "")
```

**Expected Output:**
- 50-100 ransomware families
- 500-1,000 CVE attributions
- 300-500 ATT&CK technique mappings
- Auto-generated `vuln_triggers_requirement` edges for ransomware CVEs

---

### Agent 5: VulnCheckBotnetsAgent

**Purpose:** Sync botnet CVE attribution

**Source:** `/v3/backup/botnets` (30-50 botnets)

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
Similar to VulnCheckRansomwareAgent, but for botnets collection.

**Key Differences:**
- `target_categories` field (IoT, Router, DVR, etc.)
- `botnet_uses_technique` edges (if TTP data available)

**Expected Output:**
- 30-50 botnets
- 300-500 CVE attributions

---

### Agent 6: VulnCheckThreatActorsAgent

**Purpose:** Enrich existing threat_groups collection with CVE attribution

**Source:** `/v3/backup/threat-actors`

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
```python
class VulnCheckThreatActorsAgent(BaseAgent):
    """Enrich threat_groups collection with VulnCheck CVE attribution."""

    def run(self):
        """
        Main sync flow:
        1. Fetch /v3/backup/threat-actors
        2. Enrich existing threat_groups documents
        3. Create exploited_by_threat_actor edges (CVE → threat_groups)
        4. Return sync stats
        """
        # Fetch threat actor data from VulnCheck
        # Match to existing threat_groups by MITRE group ID or name
        # Add vc_cve_references field to threat_groups
        # Create exploited_by_threat_actor edges
```

**Expected Output:**
- Enriched threat_groups collection (add vc_cve_references field)
- 1,000-2,000 CVE attributions

---

### Agent 7: VulnCheckExploitChainsAgent

**Purpose:** Sync multi-CVE attack chains

**Source:** `/v3/backup/exploit-chains` (20-40 chains)

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
```python
class VulnCheckExploitChainsAgent(BaseAgent):
    """Sync multi-CVE exploit chains."""

    def run(self):
        """
        Main sync flow:
        1. Fetch /v3/backup/exploit-chains
        2. Create exploit_chains documents
        3. Create chain_includes_vuln edges (M:N, chain → CVEs)
        4. Include chain_position and role (initial_access, privilege_escalation, etc.)
        5. Return sync stats
        """
```

**Expected Output:**
- 20-40 exploit chains
- 60-120 CVE inclusions (avg 3 CVEs per chain)

---

### Agent 8: VulnCheckEOLAgent

**Purpose:** Sync end-of-life product data

**Source:** `/v3/backup/eol` (1,500-2,000 products)

**Schedule:** Daily bulk sync (02:00 UTC)

**Implementation:**
```python
class VulnCheckEOLAgent(BaseAgent):
    """Sync EOL product data for FDA unsupported software documentation."""

    def run(self):
        """
        Main sync flow:
        1. Fetch /v3/backup/eol
        2. Create eol_products documents
        3. Calculate days_past_eol
        4. Create component_eol_status edges (future, requires SBOM ingestion)
        5. Return sync stats
        """
```

**Expected Output:**
- 1,500-2,000 EOL products
- 0 edges (requires components collection population from SBOM ingestion)

---

### Agent 9: VulnCheckCanariesAgent

**Purpose:** Sync canary network exploitation observations (PENDING VERIFICATION)

**Source:** `/v3/index/canaries` (tier TBD)

**Schedule:** Daily sync (02:00 UTC) - IF available in Community tier

**Implementation:**
```python
class VulnCheckCanariesAgent(BaseAgent):
    """Sync VulnCheck canary network observations (highest-confidence exploitation data)."""

    def run(self):
        """
        Main sync flow:
        1. Fetch /v3/index/canaries (test endpoint availability first)
        2. Create canary_observations documents
        3. Create observed_by_canary edges (CVE → canary observations)
        4. Trigger immediate regulatory edges (canary_observed urgency: immediate)
        5. Return sync stats

        NOTE: If endpoint returns 403 Forbidden, log warning and skip agent.
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = requests.get(
            "https://api.vulncheck.com/v3/index/canaries",
            headers=headers
        )

        if response.status_code == 403:
            self.logger.warning(
                "Canaries endpoint unavailable (403 Forbidden). "
                "Likely requires Professional tier. Skipping agent."
            )
            return {"status": "skipped", "reason": "canaries_unavailable"}

        response.raise_for_status()

        # Process canary observations...
```

**Canary Observation Document Schema:**
```python
{
    "_key": "<unique_observation_id>",
    "cve_id": "CVE-2024-1234",
    "observation_date": "2024-06-16T14:23:00Z",
    "source_ips": ["<anonymized>"],  # Anonymized/aggregated
    "source_countries": ["CN", "RU"],
    "exploit_signature": "Suricata rule 12345",
    "payload_hash": "sha256:...",
    "siftrank_score": 9.8,  # AI-driven prioritization
    "is_novel": True,  # No prior public exploitation evidence
    "validation_method": "suricata",  # 'suricata' | 'yara' | 'clustering'
    "source": "vulncheck-canaries",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Regulatory Auto-Generation:**
Canary observations trigger **immediate** regulatory obligations (Rule 1):
```python
if canary_observations.count > 0:
    create_edge(vuln, fda_524b_5_2_4, trigger="canary_observed", urgency="immediate")
    create_edge(vuln, cra_article_11, trigger="canary_observed", urgency="immediate")
```

**Expected Output (IF available):**
- TBD canary observations
- TBD `observed_by_canary` edges
- Auto-generated `vuln_triggers_requirement` edges with `urgency: immediate`

---

## Collection Schemas (6 New Collections)

### 1. ransomware_families

```python
{
    "_key": "lockbit-3",  # Slugified family name
    "family_name": "LockBit 3.0",
    "aliases": ["LockBit Black", "LockBit 3"],
    "malpedia_url": "https://malpedia.caad.fkie.fraunhofer.de/details/...",
    "first_seen": "2022-06-01T00:00:00Z",
    "last_seen": "2024-06-01T00:00:00Z",
    "cve_count": 15,
    "cve_references": [
        {
            "cve": ["CVE-2023-41266", "CVE-2023-48365"],
            "url": "https://...",
            "date_added": "2024-02-01T00:00:00Z"
        }
    ],
    "ttps": ["T1486", "T1490", "T1059"],
    "source": "vulncheck",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Indexes:**
- `family_name` (persistent, unique)
- `last_seen` (persistent)

---

### 2. botnets

```python
{
    "_key": "mirai",
    "botnet_name": "Mirai",
    "aliases": ["Mirai", "Miori"],
    "malpedia_url": "https://malpedia.caad.fkie.fraunhofer.de/details/...",
    "first_seen": "2016-08-01T00:00:00Z",
    "last_seen": "2024-06-01T00:00:00Z",
    "cve_count": 10,
    "cve_references": [...],
    "target_categories": ["IoT", "Router", "DVR"],
    "source": "vulncheck",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Indexes:**
- `botnet_name` (persistent, unique)
- `last_seen` (persistent)

---

### 3. exploit_intelligence

```python
{
    "_key": "CVE-2024-4577",
    "cve_id": "CVE-2024-4577",
    # Boolean flags
    "public_exploit_found": True,
    "commercial_exploit_found": False,
    "weaponized_exploit_found": True,
    "max_exploit_maturity": "weaponized",
    "reported_exploited": True,
    "reported_exploited_by_honeypot_service": False,
    "reported_exploited_by_vulncheck_canaries": False,
    "reported_exploited_by_threat_actors": True,
    "reported_exploited_by_ransomware": False,
    "reported_exploited_by_botnets": False,
    "in_cisa_kev": False,
    "in_vulncheck_kev": True,
    # Timeline
    "timeline": {
        "nvd_published": "2024-06-01T00:00:00Z",
        "nvd_last_modified": "2024-06-15T00:00:00Z",
        "first_exploit_published": "2024-06-08T00:00:00Z",
        "first_exploit_published_weaponized_or_higher": "2024-06-10T00:00:00Z",
        "most_recent_exploit_published": "2024-06-18T00:00:00Z",
        "first_reported_threat_actor": "2024-06-12T00:00:00Z",
        "most_recent_reported_threat_actor": "2024-06-18T00:00:00Z",
        "first_reported_ransomware": None,
        "most_recent_reported_ransomware": None,
        "first_reported_botnet": None,
        "most_recent_reported_botnet": None
    },
    # Individual exploit references
    "exploits": [
        {
            "url": "https://github.com/.../exploit.py",
            "name": "CVE-2024-4577 Exploit",
            "refsource": "github",
            "date_added": "2024-06-08T00:00:00Z",
            "exploit_maturity": "poc",
            "exploit_availability": "publicly-available"
        },
        {
            "url": "https://www.metasploit.com/.../cve_2024_4577.rb",
            "name": "Metasploit Module",
            "refsource": "metasploit",
            "date_added": "2024-06-10T00:00:00Z",
            "exploit_maturity": "weaponized",
            "exploit_availability": "publicly-available"
        }
    ],
    "source": "vulncheck",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Indexes:**
- `cve_id` (persistent, unique)
- `max_exploit_maturity` (persistent)
- `reported_exploited` (persistent)
- `reported_exploited_by_ransomware` (persistent)
- `timeline.first_exploit_published` (persistent)

---

### 4. canary_observations (PENDING VERIFICATION)

```python
{
    "_key": "obs_<uuid>",
    "cve_id": "CVE-2024-1234",
    "observation_date": "2024-06-16T14:23:00Z",
    "source_ips": ["<anonymized>"],
    "source_countries": ["CN", "RU"],
    "exploit_signature": "Suricata rule 12345",
    "payload_hash": "sha256:abc123...",
    "siftrank_score": 9.8,
    "is_novel": True,
    "validation_method": "suricata",
    "source": "vulncheck-canaries",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Indexes:**
- `cve_id` (persistent)
- `observation_date` (persistent)
- `is_novel` (persistent)

---

### 5. exploit_chains

```python
{
    "_key": "proxyshell",
    "chain_name": "ProxyShell",
    "description": "Microsoft Exchange Server RCE chain",
    "cve_ids": ["CVE-2021-34473", "CVE-2021-34523", "CVE-2021-31207"],
    "attack_vector": "Network",
    "impact": "Complete system compromise",
    "affected_products": ["Microsoft Exchange Server 2013", "2016", "2019"],
    "references": [
        {"url": "https://...", "title": "ProxyShell Analysis", "date_added": "2021-08-01"}
    ],
    "source": "vulncheck",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Indexes:**
- `chain_name` (persistent)

---

### 6. eol_products

```python
{
    "_key": "microsoft_windows_server_2012_6.2",
    "product_name": "Windows Server 2012",
    "vendor": "Microsoft",
    "version": "6.2",
    "release_date": "2012-09-04",
    "eol_date": "2023-10-10",
    "lts_end_date": None,
    "is_eol": True,
    "days_past_eol": 234,  # Calculated: current_date - eol_date
    "source": "vulncheck",
    "last_synced": "2024-06-20T12:00:00Z"
}
```

**Indexes:**
- `product_name, version` (persistent, compound)
- `eol_date` (persistent)
- `is_eol` (persistent)

---

## Edge Schemas (10 New Edge Collections)

### 1. has_exploit_intelligence

```python
{
    "_from": "vulnerabilities/CVE-2024-1234",
    "_to": "exploit_intelligence/CVE-2024-1234",
    "max_exploit_maturity": "weaponized",  # Denormalized for fast traversal
    "reported_exploited": True,
    "days_to_first_exploit": 7,  # NVD publish → first exploit
    "source": "vulncheck",
    "synced_at": "2024-06-20T12:00:00Z"
}
```

**Cardinality:** 1:1 (one CVE, one exploit intelligence record)

---

### 2. exploited_by_ransomware

```python
{
    "_from": "vulnerabilities/CVE-2023-41266",
    "_to": "ransomware_families/lockbit-3",
    "first_reported": "2024-02-01T00:00:00Z",
    "most_recent_reported": "2024-06-01T00:00:00Z",
    "evidence_urls": ["https://..."],
    "source": "vulncheck"
}
```

**Cardinality:** M:N (one CVE can be exploited by multiple ransomware families)

---

### 3. exploited_by_botnet

```python
{
    "_from": "vulnerabilities/CVE-2016-10401",
    "_to": "botnets/mirai",
    "first_reported": "2017-03-01T00:00:00Z",
    "most_recent_reported": "2024-06-01T00:00:00Z",
    "evidence_urls": ["https://..."],
    "source": "vulncheck"
}
```

**Cardinality:** M:N

---

### 4. exploited_by_threat_actor

```python
{
    "_from": "vulnerabilities/CVE-2024-1234",
    "_to": "threat_groups/APT28",
    "first_reported": "2024-06-12T00:00:00Z",
    "most_recent_reported": "2024-06-18T00:00:00Z",
    "evidence_urls": ["https://..."],
    "mitre_group_id": "G0007",
    "attribution_confidence": "confirmed",  # 'confirmed' | 'suspected'
    "source": "vulncheck"
}
```

**Cardinality:** M:N

---

### 5. observed_by_canary (PENDING VERIFICATION)

```python
{
    "_from": "vulnerabilities/CVE-2024-1234",
    "_to": "canary_observations/obs_<uuid>",
    "first_observed": "2024-06-16T14:23:00Z",
    "observation_count": 3,
    "is_novel_exploitation": True,  # No prior public evidence
    "source": "vulncheck-canaries"
}
```

**Cardinality:** 1:N (one CVE can have multiple canary observations)

---

### 6. chain_includes_vuln

```python
{
    "_from": "exploit_chains/proxyshell",
    "_to": "vulnerabilities/CVE-2021-34473",
    "chain_position": 1,  # Order in the chain
    "role": "initial_access",  # 'initial_access' | 'privilege_escalation' | 'lateral_movement' | 'impact'
    "source": "vulncheck"
}
```

**Cardinality:** M:N

---

### 7. component_eol_status

```python
{
    "_from": "components/<component_key>",
    "_to": "eol_products/microsoft_windows_server_2012_6.2",
    "matched_version": "6.2",
    "is_eol": True,
    "days_past_eol": 234,
    "support_status": "eol",  # 'active' | 'lts' | 'eol' | 'unknown'
    "source": "vulncheck"
}
```

**Cardinality:** N:1 (multiple components can reference same EOL product)

**Note:** Requires components collection population from SBOM ingestion (future phase)

---

### 8. ransomware_uses_technique

```python
{
    "_from": "ransomware_families/lockbit-3",
    "_to": "attack_techniques/T1486",
    "technique_id": "T1486",  # Data Encrypted for Impact
    "evidence_urls": ["https://malpedia.caad.fkie.fraunhofer.de/..."],
    "source": "vulncheck"
}
```

**Cardinality:** M:N

---

### 9. botnet_uses_technique

```python
{
    "_from": "botnets/mirai",
    "_to": "attack_techniques/T1110",
    "technique_id": "T1110",  # Brute Force
    "evidence_urls": ["https://malpedia.caad.fkie.fraunhofer.de/..."],
    "source": "vulncheck"
}
```

**Cardinality:** M:N

---

### 10. vuln_triggers_requirement (COMPLIRA DIFFERENTIATOR)

```python
{
    "_from": "vulnerabilities/CVE-2024-1234",
    "_to": "regulatory_requirements/fda_524b_5_2_4",
    "trigger_condition": "actively_exploited",  # 'actively_exploited' | 'ransomware' | 'vulncheck_kev' | 'canary_observed'
    "urgency": "24h",  # 'immediate' | '24h' | '72h' | '30d' | 'next_review'
    "required_actions": ["update_vex", "notify_authority", "update_threat_model"],
    "evidence_chain": [
        {
            "source": "vulncheck_kev",
            "evidence_type": "exploitation_confirmed",
            "timestamp": "2024-06-01T00:00:00Z",
            "url": "https://..."
        }
    ],
    "auto_generated": True,  # True if created by auto-generation rules
    "source": "complira"
}
```

**Cardinality:** M:N (one CVE can trigger multiple regulatory requirements)

**Auto-Generation Rules:** See "Regulatory Auto-Generation" section below

---

## Repository Layer (3 New Repositories)

### VulnCheckRepository

```python
class VulnCheckRepository(BaseRepository):
    """Query VulnCheck intelligence from knowledge graph."""

    def get_exploit_intelligence(self, cve_id: str) -> Optional[ExploitIntelligence]:
        """Get exploit intelligence for a CVE."""
        query = """
        FOR ei IN exploit_intelligence
            FILTER ei.cve_id == @cve_id
            RETURN ei
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        result = list(cursor)
        return ExploitIntelligence(**result[0]) if result else None

    def batch_get_exploit_intelligence(self, cve_ids: List[str]) -> Dict[str, ExploitIntelligence]:
        """Batch get exploit intelligence for multiple CVEs."""
        query = """
        FOR cve_id IN @cve_ids
            LET ei = FIRST(
                FOR e IN exploit_intelligence
                    FILTER e.cve_id == cve_id
                    RETURN e
            )
            FILTER ei != null
            RETURN ei
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_ids": cve_ids})
        results = list(cursor)
        return {ei_dict["cve_id"]: ExploitIntelligence(**ei_dict) for ei_dict in results}

    def get_ransomware_families_for_cve(self, cve_id: str) -> List[RansomwareFamily]:
        """Get ransomware families that exploit a CVE."""
        query = """
        FOR rw IN 1..1 OUTBOUND CONCAT('vulnerabilities/', @cve_id) exploited_by_ransomware
            RETURN rw
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return [RansomwareFamily(**rw_dict) for rw_dict in results]

    def get_botnets_for_cve(self, cve_id: str) -> List[Botnet]:
        """Get botnets that exploit a CVE."""
        query = """
        FOR bn IN 1..1 OUTBOUND CONCAT('vulnerabilities/', @cve_id) exploited_by_botnet
            RETURN bn
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return [Botnet(**bn_dict) for bn_dict in results]

    def get_canary_observations_for_cve(self, cve_id: str) -> List[CanaryObservation]:
        """Get canary observations for a CVE (pending verification)."""
        query = """
        FOR co IN 1..1 OUTBOUND CONCAT('vulnerabilities/', @cve_id) observed_by_canary
            RETURN co
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return [CanaryObservation(**co_dict) for co_dict in results]

    def get_exploit_chains_for_cve(self, cve_id: str) -> List[ExploitChain]:
        """Get exploit chains that include a CVE."""
        query = """
        FOR chain IN 1..1 INBOUND CONCAT('vulnerabilities/', @cve_id) chain_includes_vuln
            RETURN chain
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return [ExploitChain(**chain_dict) for chain_dict in results]
```

---

### RegulatoryEdgeRepository

```python
class RegulatoryEdgeRepository(BaseRepository):
    """Manage vuln_triggers_requirement edges (auto-generation + suggestions)."""

    def create_regulatory_edge(
        self,
        cve_id: str,
        requirement_key: str,
        trigger_condition: str,
        urgency: str,
        required_actions: List[str],
        evidence_chain: List[Dict],
        auto_generated: bool = True
    ):
        """Create vuln_triggers_requirement edge."""
        edge = {
            "_from": f"vulnerabilities/{cve_id}",
            "_to": f"regulatory_requirements/{requirement_key}",
            "trigger_condition": trigger_condition,
            "urgency": urgency,
            "required_actions": required_actions,
            "evidence_chain": evidence_chain,
            "auto_generated": auto_generated,
            "source": "complira",
            "created_at": datetime.utcnow().isoformat(),
        }

        self.db.collection("vuln_triggers_requirement").insert(edge, overwrite=True)

    def get_triggered_requirements(self, cve_id: str) -> List[RegulatoryTrigger]:
        """Get all regulatory requirements triggered by a CVE."""
        query = """
        FOR req IN 1..1 OUTBOUND CONCAT('vulnerabilities/', @cve_id) vuln_triggers_requirement
            RETURN {
                framework: req.framework,
                requirement_id: req.requirement_id,
                description: req.description,
                trigger_condition: req.trigger_condition,
                urgency: req.urgency,
                required_actions: req.required_actions,
                auto_generated: req.auto_generated
            }
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return [RegulatoryTrigger(**trigger_dict) for trigger_dict in results]
```

---

### CanaryRepository

```python
class CanaryRepository(BaseRepository):
    """Query canary observations (pending verification)."""

    def get_canary_observations(self, cve_id: str) -> List[CanaryObservation]:
        """Get all canary observations for a CVE."""
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id == @cve_id
            FOR co IN 1..1 OUTBOUND vuln observed_by_canary
                RETURN co
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return [CanaryObservation(**co_dict) for co_dict in results]

    def is_novel_exploitation(self, cve_id: str) -> bool:
        """Check if any canary observation represents novel exploitation (no prior public evidence)."""
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id == @cve_id
            FOR co IN 1..1 OUTBOUND vuln observed_by_canary
                FILTER co.is_novel == true
                LIMIT 1
                RETURN true
        """
        cursor = self.db.aql.execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)
        return len(results) > 0
```

---

## Service Layer (2 New Services)

### VulnCheckEnrichmentService

```python
class VulnCheckEnrichmentService(BaseGraphService):
    """Orchestrate VulnCheck intelligence enrichment."""

    def __init__(self, db, cache, vulncheck_repo, canary_repo):
        super().__init__(db, cache)
        self.vulncheck_repo = vulncheck_repo
        self.canary_repo = canary_repo

    async def enrich_with_vulncheck(
        self,
        findings: List[ScanFinding],
        include_canaries: bool = True
    ) -> List[VulnCheckIntelligence]:
        """
        Enrich findings with VulnCheck intelligence.

        Returns list of VulnCheckIntelligence objects containing:
        - exploit_intelligence
        - ransomware_families
        - botnets
        - canary_observations (if available)
        - exploit_chains
        - regulatory_impact (vuln_triggers_requirement edges)
        """
        # Extract unique CVE IDs
        cve_ids = list(set(f.cve_id for f in findings if f.cve_id))

        # Batch query exploit intelligence
        exploit_intel_map = self.vulncheck_repo.batch_get_exploit_intelligence(cve_ids)

        # Build enriched intelligence per CVE
        enriched = []
        for cve_id in cve_ids:
            intel = VulnCheckIntelligence(
                cve_id=cve_id,
                exploit_intelligence=exploit_intel_map.get(cve_id),
                ransomware_families=self.vulncheck_repo.get_ransomware_families_for_cve(cve_id),
                botnets=self.vulncheck_repo.get_botnets_for_cve(cve_id),
                canary_observations=self.canary_repo.get_canary_observations(cve_id) if include_canaries else [],
                exploit_chains=self.vulncheck_repo.get_exploit_chains_for_cve(cve_id),
                regulatory_impact=self.regulatory_edge_repo.get_triggered_requirements(cve_id),
            )
            enriched.append(intel)

        return enriched
```

---

### RegulatoryTriggerService

```python
class RegulatoryTriggerService(BaseGraphService):
    """Auto-generate vuln_triggers_requirement edges based on VulnCheck intelligence."""

    def __init__(self, db, cache, regulatory_edge_repo):
        super().__init__(db, cache)
        self.regulatory_edge_repo = regulatory_edge_repo

    def auto_generate_triggers(self, cve_id: str, exploit_intelligence: ExploitIntelligence):
        """
        Auto-generate regulatory triggers based on 4 high-confidence rules.

        Rules:
        1. Canary observed → Immediate (FDA, CRA, ISO)
        2. Actively exploited → 24h (FDA, CRA, ISO)
        3. Ransomware → 24h (FDA, CRA)
        4. VulnCheck KEV → 24h (FDA, CRA, ISO)
        """
        # Rule 1: Canary observed (highest confidence, immediate urgency)
        if exploit_intelligence.reported_exploited_by_vulncheck_canaries:
            self._create_trigger(
                cve_id,
                "fda_524b_5_2_4",
                trigger="canary_observed",
                urgency="immediate",
                actions=["update_vex", "notify_authority", "update_threat_model", "incident_report"],
                evidence=[{"source": "vulncheck_canaries", "evidence_type": "first_party_exploitation"}]
            )
            self._create_trigger(cve_id, "cra_article_11", trigger="canary_observed", urgency="immediate", ...)
            self._create_trigger(cve_id, "iso_27001_a_12_6_1", trigger="canary_observed", urgency="immediate", ...)

        # Rule 2: Actively exploited
        if exploit_intelligence.reported_exploited:
            self._create_trigger(cve_id, "fda_524b_5_2_4", trigger="actively_exploited", urgency="24h", ...)
            self._create_trigger(cve_id, "cra_article_11", trigger="actively_exploited", urgency="24h", ...)
            self._create_trigger(cve_id, "iso_27001_a_12_6_1", trigger="actively_exploited", urgency="immediate", ...)

        # Rule 3: Ransomware
        if exploit_intelligence.reported_exploited_by_ransomware:
            self._create_trigger(cve_id, "fda_524b_5_2_4", trigger="ransomware", urgency="24h", ...)
            self._create_trigger(cve_id, "cra_article_11", trigger="ransomware", urgency="24h", ...)

        # Rule 4: VulnCheck KEV
        if exploit_intelligence.in_vulncheck_kev:
            self._create_trigger(cve_id, "fda_524b_5_2_4", trigger="vulncheck_kev", urgency="24h", ...)
            self._create_trigger(cve_id, "cra_article_11", trigger="vulncheck_kev", urgency="24h", ...)
            self._create_trigger(cve_id, "iso_27001_a_12_6_1", trigger="vulncheck_kev", urgency="immediate", ...)

    def suggest_triggers(self, cve_id: str, exploit_intelligence: ExploitIntelligence):
        """
        Create suggested triggers for lower-confidence conditions.

        Suggestions (not auto-generated):
        - Botnet exploitation → 72h (CRA)
        - Weaponized exploit (no confirmed exploitation) → 30d (ISO)
        - POC exploit → next_review (ISO)
        """
        suggestions = []

        if exploit_intelligence.reported_exploited_by_botnets:
            suggestions.append({
                "cve_id": cve_id,
                "requirement": "cra_article_11",
                "trigger": "botnet",
                "urgency": "72h",
                "rationale": "Botnet exploitation (lower priority than ransomware)",
            })

        if exploit_intelligence.max_exploit_maturity == "weaponized" and not exploit_intelligence.reported_exploited:
            suggestions.append({
                "cve_id": cve_id,
                "requirement": "iso_27001_a_12_6_1",
                "trigger": "weaponized_exploit",
                "urgency": "30d",
                "rationale": "Weaponized exploit available but no confirmed exploitation",
            })

        if exploit_intelligence.max_exploit_maturity == "poc":
            suggestions.append({
                "cve_id": cve_id,
                "requirement": "iso_27001_a_12_6_1",
                "trigger": "poc_available",
                "urgency": "next_review",
                "rationale": "POC exploit available (informational only)",
            })

        # Store suggestions in suggested_regulatory_triggers collection
        self.db.collection("suggested_regulatory_triggers").import_bulk(suggestions, on_duplicate="replace")

        return suggestions

    def _create_trigger(self, cve_id, requirement_key, trigger, urgency, actions, evidence):
        """Helper to create regulatory trigger edge."""
        self.regulatory_edge_repo.create_regulatory_edge(
            cve_id=cve_id,
            requirement_key=requirement_key,
            trigger_condition=trigger,
            urgency=urgency,
            required_actions=actions,
            evidence_chain=evidence,
            auto_generated=True
        )
```

---

## API Endpoint Extension

### POST /v1/enrich (Extended from Phase 2)

**Request (Updated):**
```json
{
  "scan_session_id": "scan_sess_123",
  "include_threat_intel": true,
  "include_kev": true,
  "include_epss": true,
  "include_vulncheck_intelligence": true  // NEW
}
```

**Response (Extended `EnrichedFinding` Model):**
```python
class EnrichedFinding(BaseModel):
    """Scan finding enriched with vulnerability intelligence (Phase 2 + Phase 3)."""
    finding: ScanFinding

    # Phase 2 fields
    cve_details: Optional[Vulnerability] = None
    epss_score: Optional[EPSSHistory] = None
    kev_entry: Optional[KEVEntry] = None
    threat_intelligence: Optional[ThreatIntelligence] = None

    # NEW: Phase 3 VulnCheck fields
    exploit_intelligence: Optional[ExploitIntelligence] = None
    ransomware_families: List[RansomwareFamily] = Field(default_factory=list)
    botnets: List[Botnet] = Field(default_factory=list)
    canary_observations: List[CanaryObservation] = Field(default_factory=list)  # Pending verification
    exploit_chains: List[ExploitChain] = Field(default_factory=list)
    regulatory_impact: List[RegulatoryTrigger] = Field(default_factory=list)
```

**Endpoint Implementation (Modified from Phase 2):**
```python
@router.post("/enrich", response_model=EnrichResponse)
async def enrich_scan_findings(
    request: EnrichRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/enrich - Enrich scan findings with vulnerability intelligence.

    Phase 2 enrichment:
    - CVE details, EPSS, KEV, threat intelligence (CWE → CAPEC → ATT&CK)

    NEW: Phase 3 enrichment:
    - Exploit intelligence (maturity, timeline, boolean flags)
    - Ransomware/botnet attribution
    - Canary observations (highest-confidence exploitation data, pending verification)
    - Exploit chains (multi-CVE attack sequences)
    - Regulatory impact (triggered obligations)
    """
    # Phase 2 enrichment (existing)
    enrichment_service = EnrichmentService(db=get_reference_db(), cache=RedisCacheService())
    phase2_result = await enrichment_service.enrich_scan_session(
        customer_id=customer.id,
        scan_session_id=request.scan_session_id,
        include_threat_intel=request.include_threat_intel,
        include_kev=request.include_kev,
        include_epss=request.include_epss,
    )

    # NEW: Phase 3 enrichment
    if request.include_vulncheck_intelligence:
        vulncheck_service = VulnCheckEnrichmentService(
            db=get_reference_db(),
            cache=RedisCacheService(),
            vulncheck_repo=VulnCheckRepository(get_reference_db()),
            canary_repo=CanaryRepository(get_reference_db())
        )

        vulncheck_intel = await vulncheck_service.enrich_with_vulncheck(
            findings=[ef.finding for ef in phase2_result.enriched_findings],
            include_canaries=True  # Will gracefully handle if canaries unavailable
        )

        # Merge Phase 2 + Phase 3 enrichment
        vulncheck_map = {vi.cve_id: vi for vi in vulncheck_intel}

        for enriched_finding in phase2_result.enriched_findings:
            if enriched_finding.finding.cve_id in vulncheck_map:
                vc_intel = vulncheck_map[enriched_finding.finding.cve_id]
                enriched_finding.exploit_intelligence = vc_intel.exploit_intelligence
                enriched_finding.ransomware_families = vc_intel.ransomware_families
                enriched_finding.botnets = vc_intel.botnets
                enriched_finding.canary_observations = vc_intel.canary_observations
                enriched_finding.exploit_chains = vc_intel.exploit_chains
                enriched_finding.regulatory_impact = vc_intel.regulatory_impact

        # Update enrichment metadata with VulnCheck coverage
        phase2_result.enrichment_metadata.vulncheck_exploit_intelligence_coverage = (
            len([ef for ef in phase2_result.enriched_findings if ef.exploit_intelligence]) /
            len(phase2_result.enriched_findings) * 100
        )
        phase2_result.enrichment_metadata.ransomware_attribution_coverage = (
            len([ef for ef in phase2_result.enriched_findings if ef.ransomware_families]) /
            len(phase2_result.enriched_findings) * 100
        )
        phase2_result.enrichment_metadata.canary_observation_coverage = (
            len([ef for ef in phase2_result.enriched_findings if ef.canary_observations]) /
            len(phase2_result.enriched_findings) * 100
        )

    return phase2_result
```

---

## Implementation Plan

### Phase 3A: 12-16 Days (9 Agents, 6 Collections, 10 Edges)

**Stage 0-2:** Complete ✅ (Bootstrap, Investigation, Requirements)

**Stage 3:** Design Basis (This Document) - 1 day

**Stage 4:** Runtime Modeling - 1 day
- Create `future-state-runtime-call-stack.md`
- Model 9 agent execution flows
- Model POST /v1/enrich extension flow
- Model regulatory auto-generation flow

**Stage 5:** Review Gate - 1 day
- Round 1 & 2 reviews
- Confirm no blockers
- Unlock code edit permission

**Stage 6:** Implementation - 7-9 days
- Day 1-2: Schema creation (6 collections, 10 edges, indexes, graph definition)
- Day 3-5: 9 agents implementation (VulnCheckNVD2Agent, KEVAgent, ExploitsAgent, etc.)
- Day 6-7: 3 repositories (VulnCheckRepository, RegulatoryEdgeRepository, CanaryRepository)
- Day 8: 2 services (VulnCheckEnrichmentService, RegulatoryTriggerService)
- Day 9: Endpoint extension (POST /v1/enrich)
- **Canary verification:** Test `/v3/index/canaries` endpoint on Day 3, remove canary code if 403

**Stage 7:** Testing - 2-3 days
- 30 tests (9 agents + 3 repositories + 2 services + 1 endpoint + regulatory auto-generation)

**Stage 8:** Code Review - 1 day

**Stage 9:** Docs Sync - 0.5 days (API auto-documented)

**Stage 10:** Handoff - 0.5 days

**Total:** 12-16 days

---

**Design Status:** v1 Complete ✅
**Next Stage:** Stage 4 (Runtime Modeling)
