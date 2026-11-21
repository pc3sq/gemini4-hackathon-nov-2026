import asyncio
import os
from google import genai
from google.genai import types
from app.schemas import WorkerExtraction

client = genai.Client(api_key=os.environ.get("GEMINI_HACKATHON_API_KEY"))

WORKER_PROMPTS = {
    "Definition_Mapper": (
        "Extract ALL capitalized defined terms related to 'Fees', 'Charges', 'Agreement', 'Service Terms', "
        "'Confidential Information', or 'Customer Data'. Flag any definitions that incorporate external URLs "
        "or exclude implementation/support fees from total fees."
    ),
    "Liability_Indemnity_Auditor": (
        "Extract every clause governing Limitation of Liability, Liability Caps, Super Caps, and Indemnification. "
        "Explicitly trace whether Indemnification obligations are carved out from the general Liability Cap or "
        "subject to it via 'Notwithstanding' clauses."
    ),
    "DPA_and_Schedules_Specialist": (
        "Inspect all Exhibits, Addendums, DPAs, and Order Forms (especially at the end of the document). "
        "Extract exact Data Breach notification timelines (hours/days and trigger event) and Auto-Renewal notice windows."
    ),
    "Precedence_and_Override_Scanner": (
        "Find every 'Order of Precedence', 'Notwithstanding', 'Entire Agreement', or 'Amendment' clause across "
        "the entire document. Identify any clause that neutralizes, freezes, or overrides an earlier restriction."
    ),
}


async def _run_single_worker(worker_name: str, instruction: str, contract_text: str) -> WorkerExtraction:
    response = await client.aio.models.generate_content(
        model="gemini-4-hydrogen",
        contents=[
            f"Role: {worker_name}\nTask: {instruction}\nQuote exact section numbers and verbatim text.",
            contract_text,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=WorkerExtraction,
            temperature=0.0,
        ),
    )
    return WorkerExtraction.model_validate_json(response.text)


async def dispatch_workers(contract_text: str) -> list[WorkerExtraction]:
    """Run all 4 specialized sub-agents concurrently."""
    tasks = [
        _run_single_worker(name, prompt, contract_text)
        for name, prompt in WORKER_PROMPTS.items()
    ]
    return await asyncio.gather(*tasks)
