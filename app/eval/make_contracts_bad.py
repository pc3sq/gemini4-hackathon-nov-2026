import json
import random
import re
from pathlib import Path
from pydantic import BaseModel

RAW_DIR = Path("data/raw_contracts")
TEST_DIR = Path("data/test_suite")
TEST_DIR.mkdir(parents=True, exist_ok=True)


class GroundTruthLabel(BaseModel):
    test_id: str
    source_file: str
    injected_traps: list[str]
    cured_false_positives: list[str]
    notes: list[str]


MUTATIONS = {
    "RULE-01_HIDDEN_CAP_REDUCTION": {
        "rule_id": "RULE-01",
        "description": "Redefines 'Fees' in Definitions to exclude implementation & support fees, shrinking the 12-month cap.",
        "insert_location": "early",
        "text": (
            '\n\n1.14 "Applicable Fees" means solely the recurring base seat license charges actually received by Vendor '
            "in the three (3) months immediately preceding the event giving rise to liability, expressly excluding "
            "implementation, onboarding, support, and usage overage charges.\n"
        ),
    },
    "RULE-02_INDEMNITY_CAP_TRAP": {
        "rule_id": "RULE-02",
        "description": "Indemnity looks uncapped, but a buried clause in Limitation of Liability caps all indemnity obligations.",
        "insert_location": "late",
        "text": (
            "\n\n9.4 Notwithstanding any provision to the contrary in Section 8 (Indemnification), Vendor's aggregate "
            "cumulative liability for all indemnification claims, including third-party intellectual property infringement "
            "and data protection claims, shall be strictly subject to the general Liability Cap set forth in Section 9.1.\n"
        ),
    },
    "RULE-03_DPA_BREACH_DELAY": {
        "rule_id": "RULE-03",
        "description": "Appends a DPA Exhibit B imposing a 72-hour post-verification breach notification window.",
        "insert_location": "append",
        "text": (
            "\n\n--- EXHIBIT B: DATA PROCESSING & SECURITY ADDENDUM ---\n"
            "4.2 Security Incident Notification. Upon becoming aware of a confirmed Personal Data Breach, Vendor shall "
            "notify Customer within seventy-two (72) hours following completion of Vendor's internal forensic verification "
            "and impact scoping.\n"
        ),
    },
    "RULE-04_URL_MODIFICATION": {
        "rule_id": "RULE-04",
        "description": "Embeds unilateral right to update terms via hyperlink inside the Definitions section.",
        "insert_location": "early",
        "text": (
            '\n\n1.19 "Agreement" includes this MSA, any Order Forms, and the Online Service Terms published at '
            "https://example.com, which Vendor may modify from time to time in its sole "
            "discretion upon posting, with Customer's continued use constituting binding acceptance.\n"
        ),
    },
    "RULE-05_ORDER_FORM_RENEWAL": {
        "rule_id": "RULE-05",
        "description": "Appends an Order Form schedule imposing a 90-day non-renewal notice window.",
        "insert_location": "append",
        "text": (
            "\n\n--- SCHEDULE 1: INITIAL ORDER FORM ---\n"
            "Term & Renewal: Unless Customer delivers written notice of non-renewal via certified mail at least ninety (90) "
            "days prior to the expiration of the then-current Subscription Term, this Order Form shall automatically renew "
            "for successive twenty-four (24) month periods at Vendor's then-current list pricing.\n"
        ),
    },
}

CURED_TRAP = {
    "rule_id": "RULE-04",
    "description": "Contains URL terms reference, but a later override explicitly freezes terms as of the Effective Date.",
    "bait_text": (
        '\n\n2.8 Online Policies. Customer acknowledges the Acceptable Use Policy at https://example.com '
        "may be updated periodically by Vendor.\n"
    ),
    "cure_text": (
        "\n\n14.9 Order of Precedence & Freeze. Notwithstanding Section 2.8 or any hyperlinked policy, no unilateral "
        "modification to any online URL terms shall bind Customer without a bilateral written amendment signed by both parties.\n"
    ),
}


def inject_at_paragraph(doc_text: str, snippet: str, position: str) -> str:
    paragraphs = doc_text.split("\n\n")
    if len(paragraphs) < 6:
        return doc_text + snippet

    if position == "early":
        idx = max(2, int(len(paragraphs) * 0.15))
    elif position == "late":
        idx = max(4, int(len(paragraphs) * 0.80))
    else:
        return doc_text + snippet

    paragraphs.insert(idx, snippet.strip())
    return "\n\n".join(paragraphs)


def degrade_ocr_noise(text: str) -> str:
    lines = text.splitlines()
    noisy_lines = []
    for i, line in enumerate(lines):
        if i > 0 and i % 45 == 0:
            noisy_lines.append(f"\n--- CONFIDENTIAL | PAGE {i // 45 + 1} | EXECUTION VERSION ---\n")
        line = re.sub(r"\bliability\b", "liabi1ity", line, count=1) if random.random() < 0.15 else line
        noisy_lines.append(line)
    return "\n".join(noisy_lines)


def generate_test_suite(variants_per_contract: int = 3):
    raw_files = list(RAW_DIR.glob("*.txt"))
    if not raw_files:
        print(f"No raw contracts found in {RAW_DIR}. Run your scraper first!")
        return

    manifest = []
    mutation_keys = list(MUTATIONS.keys())

    for raw_file in raw_files:
        base_text = raw_file.read_text(encoding="utf-8")

        for v in range(variants_per_contract):
            test_id = f"{raw_file.stem}_var{v+1}"
            mutated_text = base_text
            injected_rules = []
            cured_rules = []
            notes = []

            chosen = random.sample(mutation_keys, k=random.randint(1, 3))
            for key in chosen:
                m = MUTATIONS[key]
                mutated_text = inject_at_paragraph(mutated_text, m["text"], m["insert_location"])
                injected_rules.append(m["rule_id"])
                notes.append(f"INJECTED [{m['rule_id']}]: {m['description']}")

            if "RULE-04" not in injected_rules and random.random() < 0.40:
                mutated_text = inject_at_paragraph(mutated_text, CURED_TRAP["bait_text"], "early")
                mutated_text = inject_at_paragraph(mutated_text, CURED_TRAP["cure_text"], "late")
                cured_rules.append(CURED_TRAP["rule_id"])
                notes.append(f"CURED TRAP [{CURED_TRAP['rule_id']}]: {CURED_TRAP['description']}")

            if random.random() < 0.50:
                mutated_text = degrade_ocr_noise(mutated_text)
                notes.append("NOISE: Applied scanned PDF OCR artifacts and mid-page headers.")

            (TEST_DIR / f"{test_id}.txt").write_text(mutated_text, encoding="utf-8")
            label = GroundTruthLabel(
                test_id=test_id,
                source_file=raw_file.name,
                injected_traps=sorted(list(set(injected_rules))),
                cured_false_positives=cured_rules,
                notes=notes,
            )
            (TEST_DIR / f"{test_id}.json").write_text(label.model_dump_json(indent=2), encoding="utf-8")
            manifest.append(label.model_dump())

    (TEST_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {len(manifest)} adversarial test cases in {TEST_DIR}/")


if __name__ == "__main__":
    random.seed(42)
    generate_test_suite(variants_per_contract=3)
    print()
    print("hello??")
    print()