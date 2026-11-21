import json
import os
from google import genai
from google.genai import types
from app.schemas import ContractAuditReport, RuleVerdict
from app.agents.workers import dispatch_workers
from app.agents.baseline import PLAYBOOK_PROMPT
from app.agents.decision_router import fast_decision_triage

client = genai.Client(api_key=os.environ.get("GEMINI_HACKATHON_API_KEY"))

RULE_MAP = {
    "rule_01_cap_violation": "RULE-01",
    "rule_02_indemnity_capped": "RULE-02",
    "rule_03_slow_breach_notice": "RULE-03",
    "rule_04_url_modification": "RULE-04",
    "rule_05_long_renewal_notice": "RULE-05",
}

ORCHESTRATOR_SYSTEM = """
You are the Lead Managing Partner (Orchestrator) synthesizing findings from 4 specialized contract review sub-agents
alongside preliminary signals from the fast triage classifier.

Perform multi-hop legal reasoning across the extracted evidence:
1. CROSS-CHECK DEFINITIONS: If Definition_Mapper found that 'Applicable Fees' only covers 3 months of base fees, apply that definition when evaluating RULE-01's 12-month liability cap.
2. RESOLVE OVERRIDES (PREVENT FALSE POSITIVES): If Precedence_and_Override_Scanner found a 'Notwithstanding' clause that freezes online URL terms or cures a restriction, mark the rule PASS and list it under `cured_exceptions`.
3. EXHIBIT SUPREMACY: If DPA_and_Schedules_Specialist found a 72-hour breach window in Exhibit B or a 90-day renewal notice in Schedule 1, those govern over generic body text—mark the rule FAIL.
"""


def _build_fast_path_report(triage: dict) -> ContractAuditReport:
    verdicts = []
    detected_traps = []
    decisions = triage["decisions"]

    for q_key, rule_id in RULE_MAP.items():
        ans = decisions[q_key]
        is_violation = bool(ans["value"])
        if is_violation:
            detected_traps.append(rule_id)
        verdicts.append(
            RuleVerdict(
                rule_id=rule_id,
                status="FAIL" if is_violation else "PASS",
                confidence=ans["confidence"],
                citations=["Fast-Path Triage (High-Confidence Classification)"],
                reasoning=f"Decisions API classified with {ans['confidence']*100:.1f}% confidence (prob={ans['probability']}).",
            )
        )

    return ContractAuditReport(
        verdicts=verdicts,
        detected_traps=sorted(detected_traps),
        cured_exceptions=[],
    )


async def run_decisions_only_audit(contract_text: str) -> ContractAuditReport:
    """Evaluates the Decisions API standalone (System 1 only) for benchmarking."""
    triage = await fast_decision_triage(contract_text)
    return _build_fast_path_report(triage)


async def run_hybrid_managed_audit(contract_text: str) -> tuple[ContractAuditReport, list[dict], bool]:
    """
    System 1 -> System 2 Hybrid Router:
    1. Runs gemini-decision-1 (~200ms, 0 output tokens).
    2. If all rules are high-confidence PASS with no override complexity, returns immediately.
    3. Otherwise, escalates to parallel Gemini 4 Hydrogen workers + Gemini 4 Neon orchestrator.
    """
    triage = await fast_decision_triage(contract_text)
    trace_logs = [
        {
            "worker_name": "System1_Decisions_Gate",
            "extracted_clauses": [f"Risk Score: {triage['decisions']['overall_risk_score']['value']}/5"],
            "potential_conflicts": [
                f"{RULE_MAP[k]}: flagged={v['value']} (conf={v['confidence']})"
                for k, v in triage["decisions"].items()
                if k in RULE_MAP and (v["value"] is True or v["confidence"] < 0.85)
            ],
        }
    ]

    if not triage["escalate_to_managed_agents"]:
        return _build_fast_path_report(triage), trace_logs, False

    worker_results = await dispatch_workers(contract_text)
    trace_logs.extend([w.model_dump() for w in worker_results])

    evidence_bundle = json.dumps(trace_logs, indent=2)
    response = await client.aio.models.generate_content(
        model="gemini-4-neon",
        contents=[
            ORCHESTRATOR_SYSTEM,
            PLAYBOOK_PROMPT,
            f"TRIAGE & SUB-AGENT EXTRACTED EVIDENCE:\n{evidence_bundle}",
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ContractAuditReport,
            temperature=0.0,
        ),
    )
    report = ContractAuditReport.model_validate_json(response.text)
    return report, trace_logs, True
