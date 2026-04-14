"""
complira_graph.cse.profile_generator
=======================================
5-agent profile generation via Claude for CSE simulation.

Generates Attacker, SOCAnalyst, DevSecOps, CISO, and Regulator profiles
in parallel using asyncio.gather with a Semaphore(3) concurrency limit
to avoid Claude rate limits.

Each profile is a JSON-serializable dict matching the agent_profiles[]
section of simulation_config.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import anthropic

from complira_graph.config import get_settings
from complira_graph.cse.graph_reader import CyberEntityNode

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

AGENT_TYPES = ["Attacker", "SOCAnalyst", "DevSecOps", "CISO", "Regulator"]
MAX_CONCURRENT_LLM_CALLS = 3
MAX_RETRIES = 3


class ProfileGenerationError(Exception):
    pass


class CyberAgentProfileGenerator:
    """Generates 5 agent profiles in parallel using Claude."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL_SONNET

    async def generate_all(self, entities: list[CyberEntityNode]) -> list[dict[str, Any]]:
        """Generate all 5 agent profiles. Returns list of 5 profile dicts."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        tasks = [
            self._generate_profile(agent_type, entities, semaphore)
            for agent_type in AGENT_TYPES
        ]
        try:
            profiles = await asyncio.gather(*tasks)
        except ProfileGenerationError:
            raise
        return list(profiles)

    async def _generate_profile(
        self,
        agent_type: str,
        entities: list[CyberEntityNode],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with semaphore:
            prompt = _build_profile_prompt(agent_type, entities)
            for attempt in range(MAX_RETRIES):
                try:
                    response = await asyncio.to_thread(
                        self._client.messages.create,
                        model=self._model,
                        max_tokens=1024,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = response.content[0].text
                    profile = _parse_profile_response(raw, agent_type)
                    log.info("cse_profile_generated", agent_type=agent_type, attempt=attempt + 1)
                    return profile
                except anthropic.RateLimitError:
                    wait = 2 ** attempt
                    log.warning("cse_profile_rate_limited", agent_type=agent_type, attempt=attempt + 1, wait_s=wait)
                    await asyncio.sleep(wait)
                except Exception as exc:
                    log.error("cse_profile_error", agent_type=agent_type, error=str(exc))
                    if attempt == MAX_RETRIES - 1:
                        raise ProfileGenerationError(f"Profile generation failed for {agent_type}: {exc}") from exc
                    await asyncio.sleep(1)

        raise ProfileGenerationError(f"Profile generation exhausted retries for {agent_type}")


def _build_profile_prompt(agent_type: str, entities: list[CyberEntityNode]) -> str:
    cve_ids = [e.entity_id for e in entities if e.entity_type == "cve"][:10]
    kev_ids = [e.entity_id for e in entities if e.entity_type == "cve" and e.is_kev][:5]
    components = [e.component_name for e in entities if e.entity_type == "component"][:5]

    context = (
        f"Attack surface: {len(cve_ids)} CVEs (KEV: {kev_ids or 'none'}), "
        f"components: {components or ['unknown']}."
    )

    role_descriptions = {
        "Attacker": (
            "an external threat actor targeting high-severity and KEV CVEs, "
            "using standard ATT&CK techniques (Initial Access, Execution, Lateral Movement, "
            "Privilege Escalation, Exfiltration). Goal: compromise maximum components."
        ),
        "SOCAnalyst": (
            "a SOC analyst monitoring for indicators of compromise, running detection rules, "
            "investigating alerts, and escalating to CISO when confirmed. Goal: detect and contain threats."
        ),
        "DevSecOps": (
            "a DevSecOps engineer responsible for patching CVEs, deploying security controls, "
            "and rotating credentials. Goal: reduce exploitable attack surface within SLA."
        ),
        "CISO": (
            "a CISO who acknowledges escalations, notifies the board on material incidents, "
            "and files CRA/NIS2 regulatory notifications when required. Goal: regulatory compliance + board comms."
        ),
        "Regulator": (
            "a regulatory compliance officer tracking CRA Article 14 notification deadlines, "
            "assessing penalty risk, and validating that notifications were filed within 24 hours. "
            "Goal: compliance posture assessment."
        ),
    }

    return f"""You are generating a simulation agent profile for a cybersecurity scenario.

Agent type: {agent_type}
Role: {role_descriptions[agent_type]}
{context}

Return a JSON object (no markdown, raw JSON only) with exactly these fields:
{{
  "agent_type": "{agent_type}",
  "role": "<one-sentence role description>",
  "tactics": ["<ATT&CK tactic 1>", "<ATT&CK tactic 2>", "<ATT&CK tactic 3>"],
  "constraints": ["<constraint 1>", "<constraint 2>"],
  "goals": ["<goal 1>", "<goal 2>"],
  "llm_context": "<2-3 sentence context string for this agent's decision-making style>"
}}"""


def _parse_profile_response(raw: str, agent_type: str) -> dict[str, Any]:
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        profile = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: return minimal valid profile
        log.warning("cse_profile_parse_fallback", agent_type=agent_type)
        profile = {
            "agent_type": agent_type,
            "role": f"{agent_type} simulation agent",
            "tactics": [],
            "constraints": [],
            "goals": [],
            "llm_context": f"Standard {agent_type} behaviour.",
        }

    profile.setdefault("agent_type", agent_type)
    return profile
