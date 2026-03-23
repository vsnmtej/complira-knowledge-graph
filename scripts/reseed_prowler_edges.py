"""
Re-run ViolationMappingPipeline for all MedCore Prowler scan runs.

Finds scan runs with tools_invoked containing "prowler" for the MedCore tenant,
then re-triggers the full post-ingest pipeline (force=True) so the new
direct-ref edge wiring picks up the nist_control_refs / hipaa_refs fields.

Usage:
    PYTHONPATH=src python scripts/reseed_prowler_edges.py
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

from arango import ArangoClient
from complira_graph.ingestion.pipeline_coordinator import PipelineCoordinator

ARANGO_URL = "http://localhost:8529"
DB_NAME = "complira_ref"
DB_USER = "root"
DB_PASS = "openSesame"


def main() -> None:
    client = ArangoClient(hosts=ARANGO_URL)
    db = client.db(DB_NAME, username=DB_USER, password=DB_PASS)

    # Find prowler scan runs
    cursor = db.aql.execute(
        """
        FOR r IN scan_runs
            FILTER "prowler" IN r.tools_invoked
            RETURN {scan_run_id: r._key, tenant_id: r.tenant_id, status: r.status}
        """
    )
    runs = list(cursor)

    if not runs:
        print("No prowler scan runs found.")
        sys.exit(0)

    coordinator = PipelineCoordinator(db)

    for run in runs:
        scan_run_id = run["scan_run_id"]
        tenant_id = run["tenant_id"]
        status = run["status"]
        print(f"  Re-running pipeline: scan_run_id={scan_run_id} tenant={tenant_id} status={status}")
        coordinator.run_post_ingest_pipeline(scan_run_id, tenant_id, force=True)
        print(f"  Done: scan_run_id={scan_run_id}")

    print(f"\nRe-seeded {len(runs)} prowler scan run(s).")


if __name__ == "__main__":
    main()
