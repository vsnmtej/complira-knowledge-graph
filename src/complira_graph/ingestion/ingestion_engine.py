"""
IngestionEngine — tool-agnostic finding normalisation pipeline.

Entry point: IngestionEngine.process(tool_name, raw_file, scan_run_id, tenant_id)
Returns:     List[IngestionBundle]

The 9 normalisation steps are invariant across all tools.
Per-tool variation is expressed entirely through ToolAdapter configuration in
adapter_registry.py. Adding a new tool = one new registry entry; no engine changes.

Bundle routing:
  "scan_findings"      → EvidenceFindingRepository.upsert_batch()
  "detected_controls"  → EvidenceDetectedControlRepository.upsert_batch()
  "component_has_vuln" → EvidenceEdgeService.create_component_has_vuln_edges()
  "audit_log"          → EvidenceRunRepository.append_audit_log()
"""

from __future__ import annotations

import hashlib
import json
import re
import logging
from dataclasses import dataclass, field
from itertools import chain as _chain
from typing import Any, Optional

from complira_graph.ingestion.adapter_registry import ADAPTER_REGISTRY, ToolAdapter

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public output type
# ---------------------------------------------------------------------------

@dataclass
class IngestionBundle:
    """
    Unit of work returned by IngestionEngine.process().

    collection: target ArangoDB collection (routing signal for service layer)
    document:   normalised document ready for import_bulk
    edges:      planned edge dicts (_to resolved later by EvidenceEdgeService)
    """
    collection: str
    document: dict
    edges: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Path traversal helpers (no external deps — jmespath not available)
# ---------------------------------------------------------------------------

def _get_field(obj: Any, path: str) -> Any:
    """
    Dot-separated + bracket-indexed field path traversal. No wildcards.

    Examples:
      "check_result.result"                              → obj["check_result"]["result"]
      "file_line_range[0]"                               → obj["file_line_range"][0]
      "SourceMetadata.Data.Git.file"                     → deep nested key
      "locations[0].physicalLocation.region.startLine"   → mixed
    """
    if obj is None or not path:
        return None

    parts: list = []
    for segment in path.split("."):
        if "[" in segment:
            base, _, rest = segment.partition("[")
            if base:
                parts.append(base)
            idx_str = rest.rstrip("]")
            if idx_str.lstrip("-").isdigit():
                parts.append(int(idx_str))
        else:
            parts.append(segment)

    current = obj
    for part in parts:
        if current is None:
            return None
        if isinstance(part, int):
            current = (
                current[part]
                if isinstance(current, (list, tuple)) and 0 <= part < len(current)
                else None
            )
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _extract_list(data: Any, path: str) -> list:
    """
    Extract a flat list of items from nested data using a simplified path.

    Supported patterns:
      "matches"              simple top-level key → list value
      "results.failed_checks" dot-path to a list
      "site[*].alerts[*]"   two-level array expansion (flatten)
      "runs[*].results[*]"  same
      "categories.*[]"      flatten all dict values at resolved path
    """
    if not path:
        return data if isinstance(data, list) else ([data] if data is not None else [])

    # ".*[]" suffix — flatten all dict values
    if ".*[]" in path:
        parent_path = path[: path.index(".*[]")]
        parent = _get_field(data, parent_path) if parent_path else data
        if isinstance(parent, dict):
            return list(
                _chain.from_iterable(
                    v if isinstance(v, list) else [v]
                    for v in parent.values()
                    if v is not None
                )
            )
        return []

    # "[*]." in path — array expansion with tail
    if "[*]." in path:
        idx = path.index("[*].")
        head = path[:idx]           # e.g. "site"
        tail = path[idx + 4:]       # e.g. "alerts[*]" or "results"
        arr = _get_field(data, head)
        if not isinstance(arr, list):
            return []
        result: list = []
        for item in arr:
            result.extend(_extract_list(item, tail))
        return result

    # Path ends with "[*]" (no further tail)
    if path.endswith("[*]"):
        arr = _get_field(data, path[:-3])
        return arr if isinstance(arr, list) else []

    # Simple dot-path to a list value
    val = _get_field(data, path)
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


# ---------------------------------------------------------------------------
# IngestionEngine
# ---------------------------------------------------------------------------

class IngestionEngine:
    """
    Tool-agnostic finding normalisation pipeline.

    All 9 steps read configuration from the ToolAdapter dict — no tool-specific
    branches exist in engine code.
    """

    def process(
        self,
        tool_name: str,
        raw_file: bytes,
        scan_run_id: str,
        tenant_id: str,
        project_id: Optional[str] = None,
    ) -> list[IngestionBundle]:
        """
        Normalise raw scanner output into a list of IngestionBundles.

        Malformed individual findings are skipped with a log entry; the overall
        run is not aborted. Raises ValueError for unknown tool_name.
        """
        adapter = ADAPTER_REGISTRY.get(tool_name)
        if adapter is None:
            raise ValueError(f"No adapter registered for tool: {tool_name!r}")

        raw_findings = self._parse(adapter, raw_file)

        bundles: list[IngestionBundle] = []
        for raw in raw_findings:
            try:
                bundle = self._process_one(adapter, raw, scan_run_id, tenant_id, tool_name)
                if bundle is not None:
                    bundles.append(bundle)
            except Exception:
                log.exception(
                    "ingestion_engine.finding_failed",
                    tool=tool_name,
                    scan_run_id=scan_run_id,
                )
        return bundles

    # ------------------------------------------------------------------
    # Step 1: Parse
    # ------------------------------------------------------------------

    def _parse(self, adapter: ToolAdapter, raw_file: bytes) -> list[dict]:
        fmt = adapter["parse_format"]

        if fmt == "json_array":
            data = json.loads(raw_file)
            return data if isinstance(data, list) else []

        if fmt == "json_lines":
            findings: list[dict] = []
            for line in raw_file.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if line:
                    try:
                        findings.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("ingestion_engine.json_lines.skip_malformed")
            return findings

        if fmt == "json_object":
            data = json.loads(raw_file)
            doc_context = self._extract_doc_context(adapter, data)

            multi_root: list[str] = adapter.get("multi_root") or []  # type: ignore[assignment]
            if multi_root:
                result: list[dict] = []
                for root_path in multi_root:
                    for item in _extract_list(data, root_path):
                        item = dict(item)
                        if doc_context:
                            item.update(doc_context)
                        result.append(item)
                return result

            parse_root: Optional[str] = adapter.get("parse_root")  # type: ignore[assignment]
            if parse_root:
                items = _extract_list(data, parse_root)
                if doc_context:
                    for item in items:
                        item.update(doc_context)
                return items

            return [data]

        if fmt == "sarif":
            data = json.loads(raw_file)
            findings_sarif: list[dict] = []
            for run in data.get("runs", []):
                for result in run.get("results", []):
                    findings_sarif.append(result)
            return findings_sarif

        raise NotImplementedError(
            f"parse_format={fmt!r} not yet implemented (xml/csv/graphql are future scope)"
        )

    def _extract_doc_context(self, adapter: ToolAdapter, data: dict) -> dict:
        """
        Read document-level fields for '@' prefix injections (e.g. '@check_type').
        Keys retain the '@' prefix so _map_fields can recognise them.
        """
        context: dict = {}
        for src_path in adapter.get("field_map", {}):
            if src_path.startswith("@"):
                field_name = src_path[1:]
                value = data.get(field_name)
                if value is not None:
                    context[src_path] = value
        return context

    # ------------------------------------------------------------------
    # _process_one — runs steps 2-9 for a single raw finding
    # ------------------------------------------------------------------

    def _process_one(
        self,
        adapter: ToolAdapter,
        raw: dict,
        scan_run_id: str,
        tenant_id: str,
        tool_name: str,
    ) -> Optional[IngestionBundle]:

        # Step 2: Route (determines target collection)
        collection = self._route(adapter, raw)

        # Step 3: Fingerprint (deterministic, before field normalisation)
        fingerprint = self._fingerprint(adapter, raw)

        # Step 4: Map fields → produces staging + canonical fields
        doc = self._map_fields(adapter, raw)

        # Step 5: Classify severity
        doc["severity"] = self._classify_severity(adapter, raw, doc)

        # Step 6: Extract CWE
        cwe_ids, cwe_source = self._extract_cwe(adapter, raw, doc)
        doc["cwe_ids"] = cwe_ids
        if cwe_source:
            doc["cwe_source"] = cwe_source

        # Step 7: Redact secrets
        self._redact(adapter, doc)

        # Remove internal staging fields (prefixed with '_')
        for k in [k for k in list(doc) if k.startswith("_")]:
            doc.pop(k)

        # Step 8: Validate
        self._validate(doc)

        # Attach canonical ingestion metadata
        doc["fingerprint"] = fingerprint
        doc["_key"] = fingerprint
        doc["scan_run_id"] = scan_run_id
        doc["tenant_id"] = tenant_id
        doc["tool"] = tool_name
        doc.setdefault("finding_type", adapter["default_finding_type"])

        # Collection-specific defaults
        if collection == "detected_controls":
            doc.setdefault("triage_status", "compliant")
            doc.setdefault("control_type", "iac_check")
        elif collection == "scan_findings":
            doc.setdefault("triage_status", "open")

        # audit_log entries: strip finding-only fields, keep compact
        if collection == "audit_log":
            audit_entry = {
                k: v for k, v in doc.items()
                if k in {
                    "_key", "check_id", "check_name", "file_path", "resource_address",
                    "iac_framework", "bc_check_id", "severity", "tool",
                    "scan_run_id", "tenant_id", "fingerprint",
                }
            }
            return IngestionBundle(collection="audit_log", document=audit_entry, edges=[])

        # Step 9: Plan edges (scan_findings only — detected_controls/component_has_vuln
        # edges are managed by EvidenceEdgeService, not planned here)
        edges = self._plan_edges(adapter, doc, collection)

        return IngestionBundle(collection=collection, document=doc, edges=edges)

    # ------------------------------------------------------------------
    # Step 2: Route
    # ------------------------------------------------------------------

    def _route(self, adapter: ToolAdapter, raw: dict) -> str:
        result_state_field: Optional[str] = adapter.get("result_state_field")  # type: ignore[assignment]
        if result_state_field:
            state = _get_field(raw, result_state_field)
            collection = adapter["result_routing"].get(state)
            if collection:
                return collection
        return adapter["result_routing"].get("*", "scan_findings")

    # ------------------------------------------------------------------
    # Step 3: Fingerprint
    # ------------------------------------------------------------------

    def _fingerprint(self, adapter: ToolAdapter, raw: dict) -> str:
        parts = [
            str(_get_field(raw, fp_field) or "")
            for fp_field in adapter["fingerprint_fields"]
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

    # ------------------------------------------------------------------
    # Step 4: Map fields
    # ------------------------------------------------------------------

    def _map_fields(self, adapter: ToolAdapter, raw: dict) -> dict:
        doc: dict = {}
        for src_path, canonical in adapter.get("field_map", {}).items():
            if src_path.startswith("@"):
                # Document-level injection: pre-injected by _parse into raw
                value = raw.get(src_path)
            else:
                value = _get_field(raw, src_path)

            if value is None:
                continue
            doc[canonical] = value
        return doc

    # ------------------------------------------------------------------
    # Step 5: Classify severity
    # ------------------------------------------------------------------

    def _classify_severity(
        self, adapter: ToolAdapter, raw: dict, doc: dict
    ) -> Optional[str]:
        raw_sev = doc.get("severity") or raw.get("severity")
        sev_map = adapter["severity_map"]
        if raw_sev in sev_map:
            return sev_map[raw_sev]
        # None key is the fallback (e.g. Checkov without --bc-api-key)
        return sev_map.get(None)

    # ------------------------------------------------------------------
    # Step 6: Extract CWE
    # ------------------------------------------------------------------

    def _extract_cwe(
        self, adapter: ToolAdapter, raw: dict, doc: dict
    ) -> tuple[list[str], Optional[str]]:
        cwe_source = adapter.get("cwe_source", "absent")

        if cwe_source == "tool_direct":
            cwe_raw = doc.get("_cwe_raw")
            if cwe_raw is None:
                return [], None
            cwe_ids = self._normalise_cwe_values(cwe_raw)
            return cwe_ids, ("tool_direct" if cwe_ids else None)

        if cwe_source == "extracted":
            pattern = adapter.get("cwe_extract_pattern")
            if not pattern:
                return [], None
            combined = " ".join(
                filter(
                    None,
                    [
                        str(doc.get("message") or ""),
                        str(doc.get("description") or ""),
                        str(doc.get("_cwe_raw") or ""),
                        str(doc.get("_cwe_int") or ""),
                    ],
                )
            )
            matches = re.findall(pattern, combined)
            cwe_ids = []
            for m in matches:
                m = str(m)
                if m.startswith("CWE-"):
                    cwe_ids.append(m)
                elif m.isdigit():
                    cwe_ids.append(f"CWE-{m}")
            seen: set = set()
            deduped = [c for c in cwe_ids if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]
            return deduped, ("extracted" if deduped else None)

        # absent
        return [], None

    @staticmethod
    def _normalise_cwe_values(raw: Any) -> list[str]:
        """Convert various CWE representations to canonical 'CWE-N' strings."""
        if isinstance(raw, int):
            return [f"CWE-{raw}"]
        items = raw if isinstance(raw, list) else [raw]
        result = []
        for item in items:
            s = str(item).strip()
            if s.startswith("CWE-"):
                result.append(s)
            elif s.isdigit():
                result.append(f"CWE-{s}")
        return result

    # ------------------------------------------------------------------
    # Step 7: Redact secrets
    # ------------------------------------------------------------------

    def _redact(self, adapter: ToolAdapter, doc: dict) -> None:
        if not adapter.get("secret_raw_field"):
            return
        raw_secret = doc.pop("_secret_raw", None)
        if raw_secret:
            h = hashlib.sha256(str(raw_secret).encode()).hexdigest()[:8]
            doc["secret_redacted"] = f"[REDACTED:{h}]"

    # ------------------------------------------------------------------
    # Step 8: Validate
    # ------------------------------------------------------------------

    def _validate(self, doc: dict) -> None:
        cve_id = doc.get("cve_id")
        if cve_id and not re.match(r"^CVE-\d{4}-\d{4,}$", cve_id, re.IGNORECASE):
            doc.setdefault("tool_vuln_id", cve_id)
            doc.pop("cve_id")
            log.debug("ingestion_engine.cve_id.demoted_to_tool_vuln_id", extra={"cve_id": cve_id})

    # ------------------------------------------------------------------
    # Step 9: Plan edges
    # ------------------------------------------------------------------

    def _plan_edges(
        self, adapter: ToolAdapter, doc: dict, collection: str
    ) -> list[dict]:
        """
        Build edge planning dicts for EvidenceEdgeService to resolve and persist.

        Only scan_findings get finding_triggers_req edge plans.
        component_has_vuln and detected_control edges are created by EvidenceEdgeService
        from the document contents, not planned here.
        """
        if collection != "scan_findings":
            return []

        req_src: str = adapter.get("req_mapping_source", "none")  # type: ignore[assignment]
        if req_src == "none":
            return []

        # Dynamic override: checkov_native declared but all deterministic fields absent
        # (open-source Checkov without --bc-api-key → no bc_check_id)
        if req_src == "checkov_native":
            det_fields: list = adapter.get("deterministic_req_fields") or []  # type: ignore[assignment]
            if det_fields and all(doc.get(f) is None for f in det_fields):
                req_src = "llm_reg_mapper"

        fingerprint = doc.get("fingerprint", "")
        return [
            {
                "collection": "finding_triggers_req",
                "_from": f"scan_findings/{fingerprint}",
                "_to": None,  # resolved by EvidenceEdgeService._resolve_req_edge()
                "source": req_src,
                "bc_check_id": doc.get("bc_check_id"),
                "confidence": None,
            }
        ]
