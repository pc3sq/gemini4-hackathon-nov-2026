import asyncio
import json
from pathlib import Path
import fitz  # PyMuPDF for PDF text extraction
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse

from app.agents.baseline import run_baseline_audit
from app.agents.orchestrator import run_hybrid_managed_audit

app = FastAPI(title="5-Sigma Legal Contract Auditor")


def extract_document_text(filename: str, raw_bytes: bytes) -> str:
    """Extracts plain text from uploaded .pdf or .txt/.htm files."""
    if filename.lower().endswith(".pdf"):
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        pages = [page.get_text("text") for page in doc]
        return "\n\n".join(pages)
    return raw_bytes.decode("utf-8", errors="ignore")


@app.get("/", response_class=HTMLResponse)
async def serve_spa():
    return Path("static/index.html").read_text(encoding="utf-8")


@app.post("/api/analyze-stream")
async def analyze_stream(file: UploadFile = File(...)):
    raw_bytes = await file.read()
    filename = file.filename or "contract.txt"
    contract_text = extract_document_text(filename, raw_bytes)

    async def event_generator():
        yield f"data: {json.dumps({'step': 'orchestrator', 'msg': f'Extracted {len(contract_text):,} chars from {filename}. Running System 1 Decisions Gate...'})}\n\n"

        # Run Hybrid System (Decisions API -> Gemini 4 Agents) & Single-Model Baseline concurrently
        (hybrid_report, trace_logs, escalated), baseline_report = await asyncio.gather(
            run_hybrid_managed_audit(contract_text),
            run_baseline_audit(contract_text),
        )

        # Stream each trace step (System 1 Gate + any System 2 Sub-Agents that were triggered)
        for trace in trace_logs:
            worker_name = trace["worker_name"]
            conflicts = trace.get("potential_conflicts", [])
            clauses = trace.get("extracted_clauses", [])
            msg = "; ".join(conflicts) if conflicts else (clauses[0] if clauses else "No conflicts flagged.")
            yield f"data: {json.dumps({'step': 'worker', 'name': worker_name, 'finding': msg})}\n\n"
            await asyncio.sleep(0.15)

        route_label = "Escalated to Gemini 4 Sub-Agents" if escalated else "Fast-Path (Decisions API Only)"
        final_payload = {
            "step": "done",
            "route": route_label,
            "managed_score": f"{5 - len(hybrid_report.detected_traps)}/5 Passed (Caught: {', '.join(hybrid_report.detected_traps) or 'None'})",
            "baseline_score": f"{5 - len(baseline_report.detected_traps)}/5 Passed (Caught: {', '.join(baseline_report.detected_traps) or 'None'})",
            "cured_exceptions": hybrid_report.cured_exceptions,
            "verdicts": [v.model_dump() for v in hybrid_report.verdicts],
        }
        yield f"data: {json.dumps(final_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/eval-results")
async def get_eval_results():
    results_file = Path("data/eval_results.json")
    if results_file.exists():
        return json.loads(results_file.read_text(encoding="utf-8"))
    return {
        "error": "No benchmark results found yet. Run `make eval` to populate data/eval_results.json."
    }