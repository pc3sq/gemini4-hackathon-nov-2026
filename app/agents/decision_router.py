import os
from google import genai

decision_client = genai.Client(
    api_key=os.environ.get("GEMINI_HACKATHON_API_KEY"),
    http_options={"api_version": "v1beta"},
)


async def fast_decision_triage(contract_input: str | bytes) -> dict:
    """
    Runs all 5 playbook checks + structural routing questions in a single ~200ms pass
    with 0 output tokens using gemini-decision-1.
    """
    questions = {
        "rule_01_cap_violation": {
            "type": "noul",
            "instructions": "Does this contract cap Vendor's aggregate liability to LESS than 12 months of total fees (including via a narrowed definition of Fees)?",
        },
        "rule_02_indemnity_capped": {
            "type": "noul",
            "instructions": "Are Vendor's IP infringement or data breach indemnification obligations subject to a general liability cap rather than uncapped or super-capped?",
        },
        "rule_03_slow_breach_notice": {
            "type": "noul",
            "instructions": "Is the security or data breach notification window longer than 48 hours or delayed until after forensic confirmation?",
        },
        "rule_04_url_modification": {
            "type": "noul",
            "instructions": "Can Vendor unilaterally modify binding contract terms via an online URL or hyperlink without a signed written amendment?",
        },
        "rule_05_long_renewal_notice": {
            "type": "noul",
            "instructions": "Does any Order Form or clause require more than 30 days prior notice to prevent auto-renewal?",
        },
        "has_override_complexity": {
            "type": "noul",
            "instructions": "Does the contract contain 'Notwithstanding' clauses, Order of Precedence conflicts, or trailing Exhibits/Schedules that modify earlier sections?",
        },
        "overall_risk_score": {
            "type": "score",
            "criteria": [
                "1: Standard customer-friendly agreement with 12+ month liability cap, uncapped IP/data indemnity, <=48h breach notice, no unilateral URL changes, and <=30d renewal notice.",
                "3: Moderate deviations such as 60-day renewal notice or minor ambiguity in fee definitions.",
                "5: Severe off-market traps including sub-12-month liability caps, capped indemnification, >48h breach windows, or unilateral URL term modifications.",
            ],
            "instructions": "Rate overall customer-side legal risk from 1 (standard/safe) to 5 (severe off-market traps).",
        },
    }

    response = await decision_client.aio.decisions.create(
        model="gemini-decision-1",
        input=contract_input,
        questions=questions,
    )

    results = {}
    escalate_to_agents = False

    for q_key, ans in response.answers.items():
        val = getattr(ans, "answer", getattr(ans, "score", getattr(ans, "value", None)))
        prob = getattr(ans, "probability", 0.0) or 0.0
        conf = getattr(ans, "confidence", 0.0) or 0.0

        results[q_key] = {
            "value": val,
            "probability": round(prob, 3),
            "confidence": round(conf, 3),
        }
        if q_key.startswith("rule_") and (val is True or conf < 0.85):
            escalate_to_agents = True
        if q_key == "has_override_complexity" and val is True:
            escalate_to_agents = True

    return {
        "escalate_to_managed_agents": escalate_to_agents,
        "decisions": results,
    }