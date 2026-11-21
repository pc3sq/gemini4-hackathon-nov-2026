from typing import Literal
from pydantic import BaseModel, Field


class RuleVerdict(BaseModel):
    rule_id: Literal["RULE-01", "RULE-02", "RULE-03", "RULE-04", "RULE-05"]
    status: Literal["PASS", "FAIL"]
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[str] = Field(description="Exact section numbers and verbatim quotes supporting the verdict.")
    reasoning: str = Field(description="Explanation of how clauses interact, including any overrides or carve-outs.")


class ContractAuditReport(BaseModel):
    verdicts: list[RuleVerdict]
    detected_traps: list[str] = Field(description="List of Rule IDs that FAILED the customer-side playbook.")
    cured_exceptions: list[str] = Field(description="Any scary clauses found that were legally neutralized elsewhere.")


class WorkerExtraction(BaseModel):
    worker_name: str
    extracted_clauses: list[str] = Field(description="Relevant sections with section numbers and exact text.")
    potential_conflicts: list[str] = Field(description="Cross-references, overrides, or defined-term anomalies.")