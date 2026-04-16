# Future-State Runtime Call Stacks — org-data-kg-integration

**Version:** v1
**Design Basis:** `proposed-design.md` v1
**Last Updated:** 2026-03-31

---

## Use Case Index

| use_case_id | Source Type | Description |
| --- | --- | --- |
| UC-001 | Requirement | Device inventory ingestion (CrowdStrike + Tenable + Qualys + SentinelOne + AWS EC2) |
| UC-002 | Requirement | Active exploitation evidence (CrowdStrike + SentinelOne) |
| UC-003 | Requirement | Network exposure signals (CrowdStrike + AWS EC2) |
| UC-004 | Requirement | IAM/MFA control gap detection (Okta) |
| UC-005 | Requirement | Incident/ticket lifecycle ingestion (Jira + PagerDuty) |
| UC-006 | Requirement | Cross-layer AQL proof query (CRA Art.14 evidence) |
| UC-007 | Requirement | Nightly TTL cleanup flow |
| UC-DR-001 | Design-Risk | Connector run with CVE in tool data that is NOT in KG spine — must not create orphan node |
| UC-DR-002 | Design-Risk | Concurrent connector runs produce idempotent KG state |
| UC-DR-003 | Design-Risk | `exploited_by` traversal in VEX evidence service degrades gracefully when no edges exist |

---

## CS-001 — UC-001: Device Inventory Ingestion (CrowdStrike path)

**Entry point:** `CrowdStrikeConnector.run()` called from Prefect task in orchestrator
**Primary path:**

```
[Prefect Task]
  orchestrator/dag.py: OrgConnectorBatch.run_all(tenant_id, db)
    → CrowdStrikeConnector(db, tenant_id, data_path="mock_data_v2/crowdstrike_03_device_entities.json")
        .run()
          ↓
          .fetch()
            → open(self.data_path).read()
            → json.loads() → raw_response: dict (devices[])
          ↓
          .extract(raw_response)
            → for device in raw_response["resources"]:
                # Only compliance-relevant fields
                hostname = device["hostname"]
                internet_facing = device.get("internet_exposure", "no") == "yes"
                containment_status = device.get("status", {}).get("containment_status")
                compliance_tags = [t for t in device.get("tags", []) if t in COMPLIANCE_TAG_SET]
                public_ports = [n["local_port"] for n in device.get("network_accesses", [])]
                # Discard: mac_address, bios_manufacturer, config_ids, groups, external_ip
                signal = ComplianceSignal(
                    collection="devices",
                    document={
                        "_key": f"{tenant_id}_{hostname}",
                        "hostname": hostname,
                        "instance_id": None,    # filled by aws_ec2 connector via merge
                        "internet_facing": internet_facing,
                        "public_ports": public_ports,
                        "containment_status": containment_status,
                        "compliance_tags": compliance_tags,
                        "source_tools": ["crowdstrike"],
                        "tenant_id": tenant_id,
                        "ttl_expires": (NOW + timedelta(days=7)).isoformat(),
                        "collected_at": NOW.isoformat(),
                    }
                )
                yield signal
          ↓
          .upsert_kg(signals)
            → db.collection("devices").import_bulk(
                [s.document for s in device_signals],
                overwrite=True     # ← idempotent upsert, merges with existing
              )
              → UpsertResult(collection="devices", written=N)
```

**Fallback path (hostname missing):**
```
device["hostname"] is None
  → use device["device_id"] as hostname fallback
  → log warning: "hostname missing, using device_id as key"
  → continue (device node still written)
```

**Error path (API/file error):**
```
json.loads() raises JSONDecodeError
  → CrowdStrikeConnector.run() raises ConnectorError("parse failed: ...")
  → Prefect task marks task as FAILED
  → other connector tasks continue (Prefect handles per-task failure)
```

**State mutations:**
- `[DB write]` `devices` collection: upsert N device documents

---

## CS-002 — UC-001: Device Inventory — Tenable bridge (aws_instance_id merge)

**Entry point:** `TenableConnector.run()` after CrowdStrikeConnector completes

```
TenableConnector(db, tenant_id, data_path="tenable_01_assets.json").run()
  .fetch() → raw_assets: list
  .extract(raw_assets)
    → for asset in raw_assets:
        aws_instance_id = asset.get("aws_instance_id")  # ← cross-tool bridge
        hostname = asset["fqdn"][0] if asset.get("fqdn") else None
        acr_score = asset.get("acr_score")
        compliance_tags = [t["value"] for t in asset.get("tags", []) if t["category"] in COMPLIANCE_CATEGORIES]
        yield ComplianceSignal(
            collection="devices",
            document={
                "_key": f"{tenant_id}_{hostname}",
                "instance_id": aws_instance_id,    # ← fills gap from CS connector
                "source_tools_add": ["tenable"],   # merged via overwrite=True
                "ttl_expires": ..., "collected_at": ..., "tenant_id": tenant_id,
            },
            edges=[{
                "collection": "device_has_vulnerability",
                "_from_key":  f"{tenant_id}_{hostname}",
                # _to filled for each vuln in tenable_02_vulnerabilities
            }]
        )
  .upsert_kg(signals)
    → db.collection("devices").import_bulk(overwrite=True)   # merges instance_id
    → [DB write] device_has_vulnerability edges batch-inserted
```

**State mutations:**
- `[DB write]` `devices`: merges `instance_id` into existing device docs
- `[DB write]` `device_has_vulnerability` edges: one per (device, CVE) from Tenable findings

---

## CS-003 — UC-002: Active Exploitation Evidence (CrowdStrike detections)

**Entry point:** `CrowdStrikeConnector.run()` reading detection entities

```
CrowdStrikeConnector(db, tenant_id, data_path="crowdstrike_05_detection_entities.json").run()
  .fetch() → raw: {"resources": [detection, ...]}
  .extract(raw)
    → for detection in raw["resources"]:
        device_hostname = detection["device"]["hostname"]
        containment = detection["device"]["filesystem_containment_status"]

        for behavior in detection.get("behaviors", []):
            cve_id = behavior.get("cve_id")           # "CVE-2023-38408"
            technique_id = behavior.get("technique_id")  # "T1190"
            tactic = behavior.get("tactic")
            ioc_value = behavior.get("ioc_value")
            ioc_type = behavior.get("ioc_type")

            if cve_id:
                # Check CVE exists in spine before writing edge
                # [DB read] vulnerabilities collection: FILTER doc.cve_id == cve_id
                if not spine_cve_exists(db, cve_id):
                    log.warning(f"CVE {cve_id} not in spine — skipping exploited_by edge")
                    continue   # ← UC-DR-001: no orphan node created

                det_doc = ComplianceSignal(
                    collection="threat_detections",
                    document={
                        "_key": f"{tenant_id}_{detection['detection_id']}",
                        "detection_id": detection["detection_id"],
                        "cve_id": cve_id,
                        "technique_id": technique_id,
                        "tactic": tactic,
                        "ioc_value": ioc_value,
                        "ioc_type": ioc_type,
                        "severity": behavior.get("severity", "unknown"),
                        "status": detection.get("status", "new"),
                        "provider": "crowdstrike",
                        "tenant_id": tenant_id,
                        "ttl_expires": (NOW + timedelta(hours=48)).isoformat(),
                        "collected_at": NOW.isoformat(),
                    },
                    edges=[{
                        "collection": "exploited_by",
                        "_from": f"vulnerabilities/{cve_id}",
                        "_to":   f"threat_detections/{tenant_id}_{detection['detection_id']}",
                        "is_exploited": True,
                        "is_isolated":  containment == "contained",
                        "alert_count":  1,
                        "provider":     "crowdstrike",
                        "source_type":  "deterministic",
                        "tenant_id":    tenant_id,
                        "ttl_expires":  (NOW + timedelta(hours=48)).isoformat(),
                        "collected_at": NOW.isoformat(),
                    }]
                )
                yield det_doc
  .upsert_kg(signals)
    → [DB write] threat_detections: import_bulk(overwrite=True)
    → [DB write] exploited_by edges: import_bulk(overwrite=True)
```

**Fallback (behavior has no cve_id):**
```
behavior.get("cve_id") is None
  → skip exploited_by edge
  → threat_detections node written without CVE link (for IOC tracking)
```

**State mutations:**
- `[DB write]` `threat_detections`: N detection documents with 48h TTL
- `[DB write]` `exploited_by` edges: vulnerability → detection with TTL

---

## CS-004 — UC-003: Network Exposure (CrowdStrike)

**Extracted inline during CS-001 (device_entities pass):**

```
CrowdStrikeConnector.extract(raw_device_entities)
  → for device in raw["resources"]:
      internet_facing = device.get("internet_exposure", "no") == "yes"
      network_accesses = device.get("network_accesses", [])
      public_ports = [n["local_port"] for n in network_accesses if n.get("local_port")]

      yield ComplianceSignal(
          collection="devices",     # device node (already CS-001)
          document={...},
          edges=[{
              "collection":     "network_exposure",
              "_from":          f"devices/{tenant_id}_{hostname}",
              "_to":            f"devices/{tenant_id}_{hostname}",   # self-edge
              "internet_facing": internet_facing,
              "public_ports":   public_ports,
              "provider":       "crowdstrike",
              "tenant_id":      tenant_id,
              "ttl_expires":    (NOW + timedelta(days=7)).isoformat(),
              "collected_at":   NOW.isoformat(),
          }]
      )
  → [DB write] network_exposure edges: import_bulk(overwrite=True)
```

**State mutations:**
- `[DB write]` `network_exposure` edge per device with `internet_facing` + `public_ports`

---

## CS-005 — UC-004: IAM/MFA Control Gap Detection (Okta)

**Entry point:** `OktaConnector.run()` reading users + roles + factors + mfa_policy

```
OktaConnector(db, tenant_id, data_paths={
    "users":      "okta_01_users.json",
    "roles":      "okta_02_roles.json",
    "factors":    "okta_03_factors.json",
    "mfa_policy": "okta_04_mfa_policy.json",
}).run()
  .fetch() → { users: [...], roles_by_user: {...}, factors_by_user: {...}, policy: {...} }
  .extract(raw)
    policy_required = {
        "okta_otp": raw["policy"]["settings"]["factors"]["okta_otp"]["enroll"]["self"] == "REQUIRED",
        "okta_push": raw["policy"]["settings"]["factors"]["okta_push"]["enroll"]["self"] == "REQUIRED",
    }
    framework_req_id = "FDA_524B_4_2"   # from policy description mapping

    for user in raw["users"]:
        user_id = user["id"]
        user_email = user["profile"]["login"]
        enrolled = raw["factors_by_user"].get(user_id, [])
        enrolled_types = {f["factorType"] for f in enrolled if f["status"] == "ACTIVE"}

        for required_type, is_required in policy_required.items():
            if is_required and required_type not in enrolled_types:
                # GAP FOUND
                yield ComplianceSignal(
                    collection="access_events",
                    document={
                        "_key": f"{tenant_id}_{user_id}_mfa_enrollment",
                        "user_id":    user_id,
                        "user_email": user_email,
                        "control_type":   "mfa_enrollment",
                        "control_status": "not_enrolled",
                        "framework_requirement_id": framework_req_id,
                        "policy_name": raw["policy"]["name"],
                        "tenant_id":   tenant_id,
                        "collected_at": NOW.isoformat(),
                    },
                    edges=[{
                        "collection": "user_lacks_control",
                        "_from":      f"access_events/{tenant_id}_{user_id}_mfa_enrollment",
                        "_to":        f"regulatory_requirements/{framework_req_id}",
                        "gap_type":   "mfa_not_enrolled",
                        "framework":  "FDA_524B",
                        "article":    "4.2",
                        "tenant_id":  tenant_id,
                        "collected_at": NOW.isoformat(),
                    }]
                )
  .upsert_kg(signals)
    → [DB write] access_events: import_bulk(overwrite=True)
    → [DB write] user_lacks_control edges: import_bulk(overwrite=True)
```

**Decision gate:** `required_type not in enrolled_types` triggers gap signal
**State mutations:**
- `[DB write]` `access_events`: one doc per user+control_type gap
- `[DB write]` `user_lacks_control` edges: access_event → regulatory_requirement

---

## CS-006 — UC-005: Incident/Ticket Lifecycle (Jira + PagerDuty)

**Jira path:**
```
JiraConnector(db, tenant_id, data_path="jira_02_issues.json").run()
  .extract(raw)
    for issue in raw["issues"]:
        cve_id = issue.get("fields", {}).get("customfield_10100")  # e.g. "CVE-2023-38408"
        hostname = issue["fields"].get("customfield_10101")
        labels = issue["fields"].get("labels", [])
        regulatory_labels = [l for l in labels if l in REGULATORY_LABEL_SET]
        priority = issue["fields"]["priority"]["name"]
        status = issue["fields"]["status"]["name"]

        yield ComplianceSignal(
            collection="incidents",
            document={
                "_key":              f"{tenant_id}_jira_{issue['key']}",
                "source":            "jira",
                "incident_id":       issue["key"],
                "cve_id":            cve_id,
                "hostname":          hostname,
                "regulatory_labels": regulatory_labels,
                "priority":          priority,
                "status":            status,
                "sla_deadline":      _compute_cra_deadline(issue["fields"]["created"])
                                     if "cra-article-14" in regulatory_labels else None,
                "tenant_id":         tenant_id,
                "collected_at":      NOW.isoformat(),
            }
        )
```

**PagerDuty path:**
```
PagerDutyConnector(db, tenant_id, data_path="pagerduty_02_incidents.json").run()
  .extract(raw)
    for incident in raw["incidents"]:
        # Extract CVE from title: "CVE-2023-38408 ... CRA Art.14 ..."
        cve_match = re.search(r"CVE-\d{4}-\d{4,}", incident["title"])
        cve_id = cve_match.group(0) if cve_match else None
        regulatory_labels = _extract_regulatory_labels(incident["title"])
        priority = incident.get("priority", {}).get("name", "unknown")
        sla_deadline = _compute_cra_deadline(incident["created_at"])
                       if "cra-article-14" in regulatory_labels else None

        yield ComplianceSignal(
            collection="incidents",
            document={
                "_key":              f"{tenant_id}_pagerduty_{incident['id']}",
                "source":            "pagerduty",
                "incident_id":       incident["id"],
                "cve_id":            cve_id,
                "hostname":          None,     # PD doesn't directly carry hostname
                "regulatory_labels": regulatory_labels,
                "priority":          priority,
                "status":            incident["status"],
                "sla_deadline":      sla_deadline,
                "tenant_id":         tenant_id,
                "collected_at":      NOW.isoformat(),
            },
            edges=[...]   # device_triggers_incident if hostname resolvable
        )
```

**State mutations:**
- `[DB write]` `incidents`: Jira + PagerDuty incident documents

---

## CS-007 — UC-006: Cross-Layer AQL Proof Query

**Entry point:** `deployment_reality_queries.cra_article14_evidence(db, cve_id, tenant_id)`

```
deployment_reality_queries.py:
  def cra_article14_evidence(db, cve_id: str, tenant_id: str) -> list[dict]:
    aql = """
      FOR vuln IN vulnerabilities
          FILTER vuln.cve_id == @cve_id

          FOR eb IN exploited_by                       // ← deployment layer
              FILTER eb._from == vuln._id
              FILTER eb.is_exploited == true
              FILTER eb.tenant_id == @tenant_id
              FILTER eb.ttl_expires > DATE_NOW()       // ← TTL guard

              LET det = DOCUMENT(eb._to)               // threat_detection node
              LET dev_key = CONCAT(@tenant_id, "_", det.hostname)

              FOR ne IN network_exposure               // ← deployment layer
                  FILTER ne._from == CONCAT("devices/", dev_key)
                  FILTER ne.internet_facing == true
                  FILTER ne.tenant_id == @tenant_id

              FOR reg IN OUTBOUND vuln maps_to_requirement  // ← spine layer
                  FILTER reg.framework == "EU_CRA"
                  FILTER reg.article == "14"

              LET inc = (
                  FOR i IN incidents
                      FILTER i.cve_id == @cve_id
                      FILTER i.tenant_id == @tenant_id
                      FILTER "cra-article-14" IN i.regulatory_labels
                      SORT i.collected_at DESC
                      LIMIT 1
                      RETURN i
              )[0]

              RETURN {
                  cve_id:             vuln.cve_id,
                  host:               det.hostname,
                  internet_facing:    ne.internet_facing,
                  technique_id:       det.technique_id,
                  ioc_value:          det.ioc_value,
                  blast_radius_score: vuln.blast_radius_score,
                  cra_deadline:       inc.sla_deadline,
                  regulatory_action:  reg.required_action,
                  evidence_sources:   [eb.provider, ne.provider, inc.source]
              }
    """
    cursor = db.aql.execute(aql, bind_vars={"cve_id": cve_id, "tenant_id": tenant_id})
    return list(cursor)
```

**Decision gate:** TTL guard `eb.ttl_expires > DATE_NOW()` — stale edges return no rows
**Expected result for CVE-2023-38408 / MedPulse:** one row with `host=pump-api-prod-01`, `internet_facing=true`, `cra_deadline=<ISO>`, `regulatory_action=<CRA Art.14 text>`

**Fallback (no exploited_by edges):** Query returns empty list — caller handles gracefully

---

## CS-008 — UC-007: Nightly TTL Cleanup Flow

**Entry point:** Prefect scheduled flow `ttl_cleanup.run_ttl_cleanup(db)`

```
orchestrator/ttl_cleanup.py:
  @flow(name="ttl-cleanup")
  def run_ttl_cleanup(db):

    @task
    def expire_deployment_edges(db):
        # Delete all deployment-layer edges past TTL
        for edge_coll in ["exploited_by", "device_has_vulnerability",
                          "network_exposure", "device_triggers_incident"]:
            result = db.aql.execute(f"""
                FOR e IN {edge_coll}
                    FILTER e.ttl_expires < DATE_NOW()
                    REMOVE e IN {edge_coll}
                    RETURN OLD._key
            """)
            expired_keys = list(result)
            log.info(f"{edge_coll}: expired {len(expired_keys)} edges")

    @task
    def expire_deployment_vertices(db):
        # Delete device + threat_detection nodes past TTL
        for coll in ["devices", "threat_detections"]:
            db.aql.execute(f"""
                FOR doc IN {coll}
                    FILTER doc.ttl_expires < DATE_NOW()
                    REMOVE doc IN {coll}
            """)

    @task
    def flag_vex_for_refresh(db):
        # Mark VEX docs whose CVE just lost all exploited_by edges
        db.aql.execute("""
            FOR vex IN scan_findings
                FILTER vex.vex_excluded == false
                LET vuln_id = CONCAT("vulnerabilities/", vex.cve_id)
                LET live_exploits = (
                    FOR eb IN exploited_by
                        FILTER eb._from == vuln_id
                        FILTER eb.ttl_expires > DATE_NOW()
                        LIMIT 1
                        RETURN 1
                )[0]
                FILTER live_exploits == null     // no live exploit edges
                UPDATE vex WITH { requires_refresh: true } IN scan_findings
        """)

    expire_deployment_edges(db)
    expire_deployment_vertices(db)
    flag_vex_for_refresh(db)
```

**State mutations:**
- `[DB write]` Delete expired edges from 4 edge collections
- `[DB write]` Delete expired vertex docs from 2 collections
- `[DB write]` Update `requires_refresh=true` on affected VEX scan_findings

---

## CS-DR-001 — UC-DR-001: CVE Not in Spine — No Orphan Node

```
CrowdStrikeConnector.extract() encounters behavior.cve_id = "CVE-FAKE-0000"

→ spine_cve_exists(db, "CVE-FAKE-0000"):
    db.aql.execute("FOR v IN vulnerabilities FILTER v.cve_id == @cve LIMIT 1 RETURN 1",
                   bind_vars={"cve": "CVE-FAKE-0000"})
    → returns []

→ log.warning("CVE CVE-FAKE-0000 not in spine — skipping exploited_by edge")
→ no threat_detections document written for this behavior
→ no exploited_by edge written
→ no new vulnerability document created (strictly forbidden)
→ device node still written (hostname/internet_facing data is valid)
→ UpsertResult.errors appended: "skipped CVE-FAKE-0000: not in spine"
```

---

## CS-DR-002 — UC-DR-002: Concurrent Connector Runs — Idempotent

```
Run 1: CrowdStrikeConnector writes devices/{tenant}_pump-api-prod-01 at T=0
Run 2: CrowdStrikeConnector writes same document at T=5min (fresher data)

→ Both runs call db.collection("devices").import_bulk(overwrite=True)
→ ArangoDB last-write-wins: Run 2 document survives with updated collected_at + ttl_expires
→ No duplicate documents created
→ Edge collections: same overwrite=True behavior
→ UpsertResult.written counts are both N (not additive)
```

---

## CS-DR-003 — UC-DR-003: VEX Evidence Service — No exploited_by Edges

**Existing flow in `vex_evidence_queries.py` after modification (C-015):**

```
VEXEvidenceService.collect_evidence(cve_id, component_purl, customer_id)
  → [DB read] Tier 1 evidence: existing spine traversal unchanged
  → [DB read] exploited_by traversal (NEW):
      db.aql.execute("""
          FOR eb IN exploited_by
              FILTER eb._from == CONCAT("vulnerabilities/", @cve_id)
              FILTER eb.tenant_id == @tenant_id
              FILTER eb.ttl_expires > DATE_NOW()
              RETURN { is_exploited: eb.is_exploited, provider: eb.provider }
      """, bind_vars={...})
      → if no rows: exploitation_evidence = []   // ← graceful empty
      → if rows: exploitation_evidence = [{"is_exploited": True, "provider": "crowdstrike"}]

  → GraphEvidence.exploitability.exploitation_confirmed = len(exploitation_evidence) > 0
  → (cwe_mappings still required for Tier 1 — exploited_by is additive signal only)
```

**Key constraint:** `exploited_by` traversal failure does NOT break existing Tier 1 gate. It is an additive enrichment. The `ValidationError: At least one CWE mapping required` bug is NOT affected.
