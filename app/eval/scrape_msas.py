import os
import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# SEC Fair-Access Policy requires a descriptive User-Agent (Name/App + Email)
HEADERS = {
    "User-Agent": "5SigmaLegalHackathon/1.0 (contact@example.com)",
    "Accept-Encoding": "gzip, deflate",
}

OUTPUT_DIR = Path("./data/raw_contracts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"


def search_edgar_msas(limit: int = 20) -> list[dict]:
    """Query SEC EFTS for Exhibit 10 Master Services Agreements."""
    params = {
        "q": '"Master Services Agreement" "Limitation of Liability" "Indemnification"',
        "forms": "10-K,10-Q,8-K",
        "startdt": "2022-01-01",
        "enddt": "2026-11-01",
    }
    resp = requests.get(EFTS_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    hits = resp.json().get("hits", {}).get("hits", [])

    contracts = []
    for hit in hits:
        src = hit.get("_source", {})
        # Filter specifically for Exhibit 10 material contracts
        file_type = src.get("file_type", "")
        if not file_type.startswith("EX-10"):
            continue

        ciks = src.get("ciks", [])
        adsh = src.get("adsh", "").replace("-", "")
        # The _id format in EFTS is "<accession_number>:<filename>"
        doc_filename = hit.get("_id", "").split(":")[-1]

        if ciks and adsh and doc_filename:
            print()
            print()
            print(f"what is ciks: ")
            print(ciks)
            # breakpoint()
            cik_num = str(int(ciks[0]))
            doc_url = f"https://sec.gov/Archives/edgar/data/{cik_num}/{adsh}/{doc_filename}"
            contracts.append({
                "company": src.get("display_names", ["Unknown"]),
                "file_type": file_type,
                "date": src.get("file_date", ""),
                "url": doc_url,
                "filename": f"{cik_num}_{adsh}_{doc_filename}",
            })
        if len(contracts) >= limit:
            break
        if len(contracts) >= limit:
            break

    return contracts


def download_and_clean(contract: dict) -> Path | None:
    """Download HTML exhibit from EDGAR and normalize to clean plain text."""
    try:
        print(contract["url"])
        resp = requests.get(contract["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "table"]):
            # Keep tables if they hold fee schedules, or strip layout tables
            if tag.name in ("script", "style"):
                tag.decompose()

        raw_text = soup.get_text(separator="\n")
        # Normalize excessive whitespace while preserving paragraph breaks
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
        clean_text = "\n\n".join(line for line in lines if line)

        # Skip tiny stub filings (< 8,000 chars) that are just cover sheets
        if len(clean_text) < 8000:
            print(f"Skipping stub ({len(clean_text)} chars): {contract['url']}")
            return None

        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", contract["filename"]) + ".txt"
        out_path = OUTPUT_DIR / safe_name
        out_path.write_text(clean_text, encoding="utf-8")
        print(f"Saved [{len(clean_text):,} chars] -> {out_path.name}")
        return out_path

    except Exception as e:
        print(f"Failed {contract['url']}: {e}")
        return None


if __name__ == "__main__":
    print("Searching SEC EDGAR for Exhibit 10 MSAs...")
    found = search_edgar_msas(limit=10)
    print(f"Found {len(found)} candidate Exhibit 10 filings. Downloading...")
    print()
    print(found)
    print()
    saved_count = 0
    for item in found:
        if download_and_clean(item):
            saved_count += 1
        time.sleep(0.25)  # Stay well below SEC's 10 req/sec limit

    print(f"\nDone! Downloaded {saved_count} real-world MSAs into {OUTPUT_DIR}/")