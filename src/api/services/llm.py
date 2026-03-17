"""
LLM Service for vulnerability enrichment with Claude (Anthropic).

Provides:
- CVE deep analysis with exploitation scenarios
- Attack path explanation with likelihood scoring
- Compliance mapping with gap analysis
- Caching and rate limiting
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import anthropic
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from api.core.config import get_cloud_settings
from api.core.cache import RedisCacheService

logger = structlog.get_logger()


class ClaudeLLMService:
    """
    Claude API integration for intelligent vulnerability analysis.

    Features:
    - Structured JSON output with validation
    - Automatic retry with exponential backoff
    - Response caching (24h TTL for analyses)
    - Token usage tracking and cost estimation
    """

    def __init__(self):
        """Initialize Claude client with API key from settings."""
        settings = get_cloud_settings()
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        self.cache = RedisCacheService()
        self.model = "claude-3-5-sonnet-20241022"  # Latest Sonnet model
        self.max_tokens = 4096
        self.temperature = 0.3  # Lower for consistency

        logger.info(
            "ClaudeLLMService initialized",
            model=self.model,
            max_tokens=self.max_tokens
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Call Claude API with retry logic.

        Args:
            system_prompt: System instructions for Claude
            user_prompt: User message with task
            response_schema: Optional JSON schema for structured output

        Returns:
            Parsed JSON response from Claude

        Raises:
            anthropic.APIError: If API call fails after retries
        """
        try:
            logger.debug(
                "Calling Claude API",
                model=self.model,
                system_prompt_length=len(system_prompt),
                user_prompt_length=len(user_prompt)
            )

            # Build messages
            messages = [
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]

            # Add JSON schema instruction if provided
            if response_schema:
                messages[0]["content"] += f"\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(response_schema, indent=2)}"

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=messages
            )

            # Extract text content
            content = response.content[0].text

            # Parse JSON response
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse Claude response as JSON",
                    error=str(e),
                    content_preview=content[:500]
                )
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                    result = json.loads(content)
                else:
                    raise

            # Log token usage
            usage = response.usage
            logger.info(
                "Claude API call successful",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_cost_estimate=self._estimate_cost(usage.input_tokens, usage.output_tokens)
            )

            return result

        except anthropic.APIError as e:
            logger.error(
                "Claude API error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate API call cost in USD.

        Claude 3.5 Sonnet pricing (as of 2024):
        - Input: $0.003 per 1K tokens
        - Output: $0.015 per 1K tokens
        """
        input_cost = (input_tokens / 1000) * 0.003
        output_cost = (output_tokens / 1000) * 0.015
        return round(input_cost + output_cost, 6)

    async def analyze_vulnerability(
        self,
        cve_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep analysis of CVE with exploitation scenarios and mitigations.

        Args:
            cve_id: CVE identifier (e.g., CVE-2024-1234)
            context: Dictionary containing:
                - description: CVE description
                - cvss_score: CVSS v3 score
                - cvss_vector: CVSS vector
                - severity: Severity level
                - cwe_list: List of CWE IDs
                - epss_score: EPSS probability
                - in_kev: Boolean for KEV catalog
                - exploit_count: Number of known exploits
                - attack_techniques: List of ATT&CK techniques
                - threat_groups: List of threat groups

        Returns:
            Dictionary with structured analysis:
                - exploitation_difficulty: 1-5 scale (1=trivial, 5=expert)
                - real_world_impact: Description of actual impact
                - mitigation_priority: CRITICAL/HIGH/MEDIUM/LOW
                - recommended_actions: List of concrete steps
                - compliance_impact: Framework-specific impacts
                - llm_confidence: Confidence score 0-1
        """
        # Check cache first
        cache_key = f"llm:cve_analysis:{cve_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug("Cache hit for CVE analysis", cve_id=cve_id)
            return cached

        # Build system prompt
        system_prompt = """You are an expert cybersecurity analyst specializing in vulnerability assessment and risk prioritization.

Your task is to analyze CVE vulnerabilities and provide actionable intelligence for security teams.

Focus on:
1. **Practical exploitation difficulty** - Consider real-world attack scenarios
2. **Business impact** - Explain consequences in business terms
3. **Actionable mitigations** - Concrete steps, not just "patch it"
4. **Compliance implications** - Which regulations care about this?

Be direct and precise. Avoid generic advice."""

        # Build user prompt with context
        user_prompt = f"""Analyze **{cve_id}** with the following context:

**CVE Details:**
- Description: {context.get('description', 'Not available')}
- CVSS Score: {context.get('cvss_score', 'Unknown')} ({context.get('severity', 'Unknown')})
- CVSS Vector: {context.get('cvss_vector', 'Not available')}

**Weakness:**
- CWE: {', '.join(context.get('cwe_list', [])) or 'Not specified'}

**Threat Intelligence:**
- EPSS Score: {context.get('epss_score', 'Unknown')} (probability of exploitation in next 30 days)
- In CISA KEV Catalog: {"YES - actively exploited in the wild" if context.get('in_kev') else "No"}
- Known Exploits: {context.get('exploit_count', 0)}
- ATT&CK Techniques: {', '.join(context.get('attack_techniques', [])) or 'None mapped'}
- Threat Groups: {', '.join(context.get('threat_groups', [])) or 'None identified'}

Provide your analysis in the following JSON format:

{{
  "exploitation_difficulty": <1-5 integer>,
  "exploitation_difficulty_rationale": "<brief explanation>",
  "real_world_impact": "<2-3 sentences explaining what attacker can actually do>",
  "mitigation_priority": "<CRITICAL|HIGH|MEDIUM|LOW>",
  "recommended_actions": [
    "<specific action 1>",
    "<specific action 2>",
    "<specific action 3>"
  ],
  "compliance_impact": {{
    "FDA_524B": "<impact on medical device compliance or 'Not applicable'>",
    "EU_CRA": "<impact on EU Cyber Resilience Act or 'Not applicable'>",
    "NIST_800_53": "<relevant control families or 'Not applicable'>",
    "ISO_27001": "<relevant controls or 'Not applicable'>"
  }},
  "llm_confidence": <0.0-1.0 float indicating confidence in analysis>
}}

Focus on actionable intelligence. Be specific."""

        # Define response schema
        response_schema = {
            "type": "object",
            "properties": {
                "exploitation_difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
                "exploitation_difficulty_rationale": {"type": "string"},
                "real_world_impact": {"type": "string"},
                "mitigation_priority": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                "recommended_actions": {"type": "array", "items": {"type": "string"}},
                "compliance_impact": {
                    "type": "object",
                    "properties": {
                        "FDA_524B": {"type": "string"},
                        "EU_CRA": {"type": "string"},
                        "NIST_800_53": {"type": "string"},
                        "ISO_27001": {"type": "string"}
                    }
                },
                "llm_confidence": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": [
                "exploitation_difficulty",
                "real_world_impact",
                "mitigation_priority",
                "recommended_actions",
                "compliance_impact",
                "llm_confidence"
            ]
        }

        # Call Claude
        result = await self._call_claude(system_prompt, user_prompt, response_schema)

        # Add metadata
        result["cve_id"] = cve_id
        result["analyzed_at"] = datetime.utcnow().isoformat()
        result["model"] = self.model

        # Cache result (24 hours)
        await self.cache.set(cache_key, result, ttl=86400)

        logger.info(
            "CVE analysis completed",
            cve_id=cve_id,
            mitigation_priority=result.get("mitigation_priority"),
            exploitation_difficulty=result.get("exploitation_difficulty")
        )

        return result

    async def trace_attack_path(
        self,
        cve_id: str,
        graph_path: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Explain attack path with likelihood scoring.

        Args:
            cve_id: CVE identifier
            graph_path: List of graph nodes in path:
                [
                    {"stage": "vulnerability", "node": "CVE-2024-1234", ...},
                    {"stage": "weakness", "node": "CWE-89", ...},
                    {"stage": "attack_pattern", "node": "CAPEC-66", ...},
                    {"stage": "technique", "node": "T1190", ...},
                    {"stage": "threat_groups", "nodes": ["APT28"], ...}
                ]

        Returns:
            Enriched attack path with likelihoods and explanations
        """
        # Check cache
        cache_key = f"llm:attack_path:{cve_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug("Cache hit for attack path", cve_id=cve_id)
            return cached

        system_prompt = """You are an expert in cyber threat intelligence and attack chain analysis.

Your task is to analyze attack paths from vulnerabilities to threat actors and explain:
1. **Likelihood at each stage** - Probability this path will be followed
2. **Real-world relevance** - Are threat actors actually using this path?
3. **Defensive priorities** - Which stage to defend most aggressively

Be precise with likelihood estimates based on threat intelligence."""

        # Format graph path for prompt
        path_description = "\n".join([
            f"**{stage['stage'].upper()}**: {stage.get('node') or stage.get('nodes')} - {stage.get('description', 'No description')}"
            for stage in graph_path
        ])

        user_prompt = f"""Analyze this attack path starting from **{cve_id}**:

{path_description}

For each stage in the attack path, provide:
1. **Likelihood score** (0.0-1.0) that an attacker will successfully progress through this stage
2. **Explanation** of why this likelihood applies
3. **Defensive recommendation** for this specific stage

Consider:
- EPSS scores and KEV status for initial exploitation likelihood
- Historical threat group behavior
- Attack technique prevalence in the wild

Respond in JSON format:

{{
  "attack_path": [
    {{
      "stage": "<stage name>",
      "node": "<node identifier>",
      "likelihood": <0.0-1.0>,
      "likelihood_rationale": "<brief explanation>",
      "defensive_priority": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "recommended_defense": "<specific defensive action>"
    }}
  ],
  "overall_risk_score": <0.0-1.0 float>,
  "key_chokepoint": "<which stage to defend most aggressively>",
  "llm_confidence": <0.0-1.0>
}}"""

        result = await self._call_claude(system_prompt, user_prompt)

        # Add metadata
        result["cve_id"] = cve_id
        result["analyzed_at"] = datetime.utcnow().isoformat()

        # Cache (6 hours - threat landscape changes)
        await self.cache.set(cache_key, result, ttl=21600)

        logger.info(
            "Attack path analysis completed",
            cve_id=cve_id,
            overall_risk_score=result.get("overall_risk_score")
        )

        return result

    async def map_to_compliance(
        self,
        findings: List[Dict[str, Any]],
        frameworks: List[str]
    ) -> Dict[str, Any]:
        """
        Map scan findings to compliance controls with gap analysis.

        Args:
            findings: List of findings with CVE IDs and context
            frameworks: List of framework names (e.g., ["NIST_800_53", "FDA_524B"])

        Returns:
            Control mappings with gap analysis
        """
        # Simplified prompt for compliance mapping
        system_prompt = """You are a compliance expert specializing in cybersecurity frameworks.

Map vulnerabilities to compliance controls and identify gaps."""

        # Format findings
        findings_summary = "\n".join([
            f"- {f.get('cve_id', 'Unknown CVE')}: {f.get('severity', 'Unknown')} severity, affects {f.get('component', 'unknown component')}"
            for f in findings[:20]  # Limit to first 20 to avoid token limits
        ])

        user_prompt = f"""Map these findings to compliance frameworks {', '.join(frameworks)}:

{findings_summary}

Total findings: {len(findings)}

For each framework, provide:
1. **Applicable controls** with finding counts
2. **Coverage percentage** (what % of controls have findings)
3. **Gap analysis** (which controls are missing evidence)

Respond in JSON format."""

        result = await self._call_claude(system_prompt, user_prompt)

        logger.info(
            "Compliance mapping completed",
            frameworks=frameworks,
            findings_count=len(findings)
        )

        return result
