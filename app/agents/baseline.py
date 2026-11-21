import os
from google import genai
from google.genai import types
from app.schemas import ContractAuditReport

client = genai.Client(api_key=os.environ.get("GEMINI_HACKATHON_API_KEY"))

PLAYBOOK_PROMPT = """
You are a commercial contracts attorney auditing an Enterprise SaaS MSA + DPA for a CUSTOMER.
Evaluate the contract strictly against these 5 rules. Return FAIL if the contract violates the rule, or PASS if compliant:

- RULE-01 (Liability Cap): Aggregate liability cap must be at least 12 months of fees paid/payable (watch out for narrowed 'Fees' definitions).
- RULE-02 (Indemnity Carve-Out): Vendor IP & Data Breach indemnification must be uncapped or have a 2x+ Super Cap (FAIL if capped at standard 1x fees).
- RULE-03 (Breach Notification): Security/data breach notification window must be 48 hours or less from discovery (FAIL if 72 hours or 'after confirmation').
- RULE-04 (Unilateral Modification): Vendor cannot unilaterally modify terms via hyperlink/URL without written consent (PASS if an override clause freezes URL terms).
- RULE-05 (Auto-Renewal Window): Non-renewal notice window must be 30 days or less (FAIL if 60 or 90 days in an Order Form).
"""


async def run_baseline_audit(contract_text: str) -> ContractAuditReport:
    """Single-shot baseline call."""
    response = await client.aio.models.generate_content(
        model="gemini-4-hydrogen",
        contents=[PLAYBOOK_PROMPT, f"CONTRACT TEXT:\n{contract_text}"],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ContractAuditReport,
            temperature=0.0,
        ),
    )
    return ContractAuditReport.model_validate_json(response.text)
