"""Counter-analysis prompts for challenging synthesis conclusions.

Provides alternative explanations and identifies weaknesses in the current analysis.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are a devil's advocate reviewing an investigation synthesis.
Your job is to challenge the current conclusion and find weaknesses.

CRITICAL: Be genuinely skeptical. Look for:
1. Alternative explanations that could fit the same evidence
2. Gaps in the causal chain that weren't proven
3. Evidence that was ignored or underweighted
4. Assumptions that weren't validated

DO NOT rubber-stamp the conclusion. Actively search for problems.

REQUIRED FIELDS:

1. alternative_explanations: 1-5 other explanations that could fit the evidence
   - Each must be specific and plausible
   - Example: "The NULL spike could also be caused by a schema migration that
     added a new nullable column, not an ETL failure"

2. weaknesses: 1-5 specific weaknesses in the current analysis
   - Point to specific gaps or unproven assumptions
   - Example: "The analysis assumes the ETL job failure caused the NULLs, but
     didn't verify that the NULLs started exactly when the job failed"

3. confidence_adjustment: Float from -0.5 to 0.5
   - Negative = the conclusion is weaker than claimed
   - Positive = the conclusion is actually stronger (rare)
   - 0.0 = no adjustment needed
   - Example: -0.15 if there are minor gaps in the causal chain

4. recommendation: One of "accept", "investigate_more", or "reject"
   - "accept": Conclusion is solid despite minor issues
   - "investigate_more": Significant gaps that need more evidence
   - "reject": Conclusion is likely wrong or unsupported

Be constructive but rigorous. The goal is to improve analysis quality."""


def build_system() -> str:
    """Build counter-analysis system prompt.

    Returns:
        The system prompt.
    """
    return SYSTEM_PROMPT


def build_user(
    synthesis: dict[str, Any],
    evidence: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> str:
    """Build counter-analysis user prompt.

    Args:
        synthesis: The current synthesis/conclusion.
        evidence: All collected evidence.
        hypotheses: The hypotheses that were tested.

    Returns:
        Formatted user prompt.
    """
    # Format hypotheses
    hypotheses_text = "\n".join(
        f"- {h.get('id', 'unknown')}: {h.get('title', 'Unknown')}" for h in hypotheses
    )

    # Format evidence
    evidence_text = "\n\n".join(
        f"""### {e.get("hypothesis_id", "unknown")}
- Supports: {e.get("supports_hypothesis", "unknown")}
- Confidence: {e.get("confidence", 0.0)}
- Interpretation: {e.get("interpretation", "N/A")[:200]}"""
        for e in evidence
    )

    # Format synthesis
    root_cause = synthesis.get("root_cause", "Unknown")
    confidence = synthesis.get("confidence", 0.0)
    causal_chain = synthesis.get("causal_chain", [])
    chain_text = " -> ".join(causal_chain) if causal_chain else "Not provided"

    return f"""## Current Synthesis (Challenge This)

**Root Cause**: {root_cause}
**Confidence**: {confidence}
**Causal Chain**: {chain_text}

## Hypotheses Tested
{hypotheses_text}

## Evidence Collected
{evidence_text}

Challenge this synthesis. Find alternative explanations, weaknesses, and gaps."""
