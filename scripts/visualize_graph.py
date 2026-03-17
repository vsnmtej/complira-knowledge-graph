"""
Interactive graph visualization using pyvis.

Generates HTML visualizations of CVE enrichment paths.
"""

from complira_graph.db import get_db
from pyvis.network import Network
import structlog

logger = structlog.get_logger()


def visualize_cve_enrichment(cve_id: str, output_file: str = "cve_graph.html"):
    """
    Visualize the full enrichment path for a CVE.

    CVE → CWE → CAPEC → ATT&CK → Controls → Regulatory
    """
    db = get_db()

    # Normalize CVE ID
    cve_key = cve_id.replace("-", "_").upper()

    logger.info(f"Visualizing enrichment path for {cve_id}...")

    # Query to get full enrichment graph
    query = """
    LET cve_doc = DOCUMENT("vulnerabilities", @cve_key)

    // Get all connected nodes
    LET nodes = (
        // CVE node
        RETURN {id: cve_doc._key, label: cve_doc.cve_id, type: "cve", group: 0}
    )

    // Get CWE weaknesses
    LET cwe_nodes = (
        FOR v IN 1..1 OUTBOUND cve_doc has_weakness
            RETURN {id: v._key, label: v.cwe_id, type: "cwe", group: 1, title: v.name}
    )

    // Get CAPEC patterns
    LET capec_nodes = (
        FOR cwe IN 1..1 OUTBOUND cve_doc has_weakness
            FOR v IN 1..1 INBOUND cwe capec_relates_to_cwe
                RETURN DISTINCT {id: v._key, label: v.capec_id, type: "capec", group: 2, title: v.name}
    )

    // Get ATT&CK techniques
    LET attack_nodes = (
        FOR cwe IN 1..1 OUTBOUND cve_doc has_weakness
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                FOR v IN 1..1 OUTBOUND capec capec_maps_to_attack
                    RETURN DISTINCT {id: v._key, label: v.technique_id, type: "attack", group: 3, title: v.name}
    )

    // Get NIST controls
    LET control_nodes = (
        FOR cwe IN 1..1 OUTBOUND cve_doc has_weakness
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
                    FOR v IN 1..1 OUTBOUND attack technique_mitigated_by_control
                        RETURN DISTINCT {id: v._key, label: v.control_id, type: "control", group: 4, title: v.title}
    )

    // Get regulatory requirements
    LET reg_nodes = (
        FOR v IN 1..1 OUTBOUND cve_doc violates_requirement
            RETURN DISTINCT {id: v._key, label: v.requirement_id, type: "regulatory", group: 5, title: v.title}
    )

    // Get all edges
    LET cve_to_cwe = (
        FOR v, e IN 1..1 OUTBOUND cve_doc has_weakness
            RETURN {from: e._from, to: e._to, label: "has_weakness"}
    )

    LET cwe_to_capec = (
        FOR cwe IN 1..1 OUTBOUND cve_doc has_weakness
            FOR v, e IN 1..1 INBOUND cwe capec_relates_to_cwe
                RETURN {from: e._from, to: e._to, label: "relates_to"}
    )

    LET capec_to_attack = (
        FOR cwe IN 1..1 OUTBOUND cve_doc has_weakness
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                FOR v, e IN 1..1 OUTBOUND capec capec_maps_to_attack
                    RETURN {from: e._from, to: e._to, label: "maps_to"}
    )

    LET attack_to_control = (
        FOR cwe IN 1..1 OUTBOUND cve_doc has_weakness
            FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
                    FOR v, e IN 1..1 OUTBOUND attack technique_mitigated_by_control
                        RETURN {from: e._from, to: e._to, label: "mitigated_by"}
    )

    LET cve_to_reg = (
        FOR v, e IN 1..1 OUTBOUND cve_doc violates_requirement
            RETURN {from: e._from, to: e._to, label: "violates"}
    )

    RETURN {
        nodes: UNION(nodes, cwe_nodes, capec_nodes, attack_nodes, control_nodes, reg_nodes),
        edges: UNION(cve_to_cwe, cwe_to_capec, capec_to_attack, attack_to_control, cve_to_reg)
    }
    """

    result = list(db.aql.execute(query, bind_vars={"cve_key": cve_key}))

    if not result or not result[0]['nodes']:
        logger.error(f"CVE {cve_id} not found or has no enrichment data")
        return None

    data = result[0]

    # Create pyvis network
    net = Network(
        height="800px",
        width="100%",
        bgcolor="#222222",
        font_color="white",
        directed=True
    )

    # Set physics options for better layout
    net.set_options("""
    {
        "physics": {
            "barnesHut": {
                "gravitationalConstant": -30000,
                "centralGravity": 0.3,
                "springLength": 200
            },
            "minVelocity": 0.75
        }
    }
    """)

    # Color scheme by node type
    colors = {
        "cve": "#ff4444",      # Red
        "cwe": "#ff9944",      # Orange
        "capec": "#ffdd44",    # Yellow
        "attack": "#44ff44",   # Green
        "control": "#4444ff",  # Blue
        "regulatory": "#ff44ff" # Purple
    }

    # Build a map of node types to collection names
    collection_map = {
        "cve": "vulnerabilities",
        "cwe": "weaknesses",
        "capec": "attack_patterns",
        "attack": "attack_techniques",
        "control": "oscal_controls",
        "regulatory": "regulatory_requirements"
    }

    # Add nodes
    for node in data['nodes']:
        # Build full node ID (collection/key)
        collection = collection_map.get(node['type'], f"{node['type']}s")
        node_id = f"{collection}/{node['id']}"

        net.add_node(
            node_id,
            label=node['label'],
            title=node.get('title', node['label']),
            color=colors.get(node['type'], "#888888"),
            size=20 if node['type'] == 'cve' else 15
        )

    # Add edges
    for edge in data['edges']:
        net.add_edge(
            edge['from'],
            edge['to'],
            label=edge.get('label', ''),
            arrows='to'
        )

    # Save to HTML file
    net.show(output_file)
    logger.info(f"✅ Graph saved to {output_file}")
    logger.info(f"Open in browser: file://{output_file}")

    # Print stats
    logger.info(f"Graph Statistics:")
    logger.info(f"  Nodes: {len(data['nodes'])}")
    logger.info(f"  Edges: {len(data['edges'])}")
    logger.info(f"  Node types: {set(n['type'] for n in data['nodes'])}")

    return output_file


def sample_queries():
    """Print sample AQL queries for ArangoDB Web UI."""

    queries = {
        "1. CVE Enrichment Path (CVE-2024-2508)": """
// Visualize full enrichment for a specific CVE
FOR v, e, p IN 1..5 OUTBOUND "vulnerabilities/CVE_2024_2508"
    has_weakness, capec_relates_to_cwe, capec_maps_to_attack, technique_mitigated_by_control, violates_requirement
    LIMIT 50
    RETURN {vertex: v, edge: e, path: p}
        """,

        "2. CWE → CAPEC → ATT&CK Chain": """
// Show attack progression from weakness to technique
FOR cwe IN weaknesses
    FILTER cwe.cwe_id == "CWE-79"
    FOR v, e, p IN 1..3 ANY cwe
        capec_relates_to_cwe, capec_maps_to_attack
        LIMIT 20
        RETURN {vertex: v, edge: e}
        """,

        "3. ATT&CK Technique → Controls": """
// Show which controls mitigate a specific technique
FOR v, e IN 1..1 OUTBOUND "attack_techniques/t1059"
    technique_mitigated_by_control
    RETURN {technique: "T1059", control: v.control_id, title: v.title}
        """,

        "4. Regulatory Compliance View": """
// Show all CVEs violating a specific requirement
FOR e IN violates_requirement
    FILTER e._to == "regulatory_requirements/CRA_ANNEX_I_1_1"
    LET cve = DOCUMENT(e._from)
    LIMIT 10
    RETURN {
        cve: cve.cve_id,
        severity: e.severity,
        framework: e.framework
    }
        """,

        "5. Top 10 Most Connected CWEs": """
// Find CWEs with most CVE connections
FOR cwe IN weaknesses
    LET cve_count = LENGTH(FOR v IN 1..1 INBOUND cwe has_weakness RETURN 1)
    FILTER cve_count > 0
    SORT cve_count DESC
    LIMIT 10
    RETURN {cwe: cwe.cwe_id, name: cwe.name, cve_count: cve_count}
        """
    }

    print("=" * 80)
    print("Sample AQL Queries for ArangoDB Web UI Graph Viewer")
    print("=" * 80)
    print()
    print("Copy these queries into the ArangoDB Web UI:")
    print("http://localhost:8529 → GRAPHS → Queries tab")
    print()

    for title, query in queries.items():
        print(f"\n{'='*80}")
        print(f"{title}")
        print('='*80)
        print(query.strip())

    print("\n" + "="*80)


if __name__ == '__main__':
    import sys

    # Print sample queries
    sample_queries()

    # Generate interactive visualization for CVE-2024-2508
    print("\n\nGenerating interactive visualization...")
    visualize_cve_enrichment("CVE-2024-2508", "cve_2024_2508_graph.html")
