"""Versioned prompt template for structured AI recommendations (WP-REC-03C).

This module defines the system prompt that instructs the AI model to
return JSON matching the structured recommendation wire schema
(``backend/app/schemas/recommendation.py``, SoT 02 §6).

Design contract (WP-REC-03C):

- The prompt template is **versioned**. The ``PROMPT_VERSION`` constant
  must be coordinated with ``RECOMMENDATION_SCHEMA_VERSION`` in the wire
  schema module.
- The prompt **preserves DEC-004 and DEC-039 (TD-4)**: it instructs the
  model that deterministic risk quantities (shortage, available quantity,
  severity) are provided by the deterministic risk engine and must not be
  recalculated by the AI. The AI's role is to enrich validated facts with
  explanations, business impact, and recommended actions.
- The prompt contains **no real or sensitive data**. It is a static
  template with placeholder markers for runtime context (plan identifier,
  risk data) that will be supplied by the future 03F worker.
- The prompt **does not hardcode Golden Scenario results**. It describes
  the output contract only.
- The prompt **does not perform retrieval or persistence**.

This module does not wire the prompt into the workflow engine or the
provider. That integration belongs to WP-REC-03F.
"""

from __future__ import annotations

# Prompt version. Must be coordinated with RECOMMENDATION_SCHEMA_VERSION
# (``backend/app/schemas/recommendation.py``). When the schema version
# changes, the prompt version must be reviewed and potentially bumped.
PROMPT_VERSION: str = "1.0"

# The system prompt is a static template. Runtime context (plan_id,
# run_id, risk data) will be injected by the future 03F worker when it
# calls ChatProvider.complete(prompt=..., schema=..., context=...).
#
# Template syntax: Python ``str.format()`` is used for runtime value
# injection. Single-brace tokens ``{plan_id}``, ``{run_id}``, and
# ``{risk_data}`` are format fields replaced at call time. All literal
# JSON braces in the example structure are escaped as ``{{`` and ``}}``
# so they survive ``str.format()`` as single braces in the output.
SYSTEM_PROMPT_TEMPLATE: str = """\
You are a supply chain risk intelligence assistant. Your task is to
analyze production plan supply risks and provide structured
recommendations.

CRITICAL RULES (DEC-004, DEC-039):
- Deterministic risk quantities (shortage, available quantity, severity)
  are computed by the deterministic risk engine and provided to you as
  input. You must NOT recalculate, modify, or override these values.
- Your role is to ENRICH the validated risk facts with:
  - a concise summary of each risk;
  - a description of business impact;
  - recommended mitigation actions;
  - source citations when document context is available.
- Do not create write actions. Recommended actions that require human
  approval must have "requires_approval": true.
- If you do not have sufficient information for a field, provide your
  best assessment based on the available context. Do not fabricate
  document citations.

OUTPUT CONTRACT:
Return ONLY a JSON object matching schema version "1.0" with this
structure:

{{
  "schema_version": "1.0",
  "run_id": "<UUID of the workflow run>",
  "plan_id": "<external plan identifier, e.g. PLAN-2026-W31>",
  "risks": [
    {{
      "risk_id": "<risk identifier from the risk engine, e.g. RISK-001>",
      "summary": "<concise risk summary>",
      "business_impact": "<description of business impact>",
      "recommended_actions": [
        {{
          "action_type": "<action type, e.g. CREATE_PROCUREMENT_TASK>",
          "title": "<short action title>",
          "rationale": "<why this action is recommended>",
          "requires_approval": true
        }}
      ],
      "sources": [
        {{
          "document_id": "<document identifier>",
          "version": "<document version>",
          "chunk_id": "<UUID of the knowledge chunk>"
        }}
      ]
    }}
  ]
}}

RULES:
- "schema_version" must be exactly "1.0".
- "risks" must contain at least one risk item.
- "sources" is required. If no document context is available, use an
  empty list []. Empty sources means the recommendation is not grounded
  in retrieved documents.
- "sources" may cite ONLY documents present in the retrieved document
  context below. Each source's "document_id", "version", and "chunk_id"
  must exactly match a supplied entry. Never invent, reuse, or cite any
  document, version, or chunk that is not supplied in the retrieved
  document context.
- Do not include extra fields. Unknown fields will be rejected.
- Do not include deterministic quantity fields (shortage, available,
  severity) in the risk items. Those are owned by the risk engine.
- Return only the JSON object. No markdown, no explanation text.

INPUT CONTEXT (provided at runtime):
- Plan identifier: {plan_id}
- Workflow run ID: {run_id}
- Risk engine output: {risk_data}
- Retrieved document context (cite ONLY these): {retrieval_context}
"""


def build_system_prompt(
    *,
    plan_id: str,
    run_id: str,
    risk_data: str,
    retrieval_context: str = "[]",
) -> str:
    """Build the system prompt with runtime context injected.

    This function uses ``str.format()`` to inject the runtime values into
    the template. Literal JSON braces in the template are escaped as
    ``{{`` / ``}}`` and survive ``str.format()`` as single braces in the
    output. The format fields ``{plan_id}``, ``{run_id}``,
    ``{risk_data}``, and ``{retrieval_context}`` are replaced with the
    supplied values.

    Args:
        plan_id: External production plan identifier (e.g.
            ``"PLAN-2026-W31"``).
        run_id: Workflow run UUID as a string.
        risk_data: JSON string of the deterministic risk engine output
            that the AI should enrich.
        retrieval_context: JSON string of the bounded retrieval context
            (accessible chunks with citation identities) that the AI may
            cite. Defaults to ``"[]"`` (ungrounded).

    Returns:
        The assembled system prompt string.
    """
    return SYSTEM_PROMPT_TEMPLATE.format(
        plan_id=plan_id,
        run_id=run_id,
        risk_data=risk_data,
        retrieval_context=retrieval_context,
    )
