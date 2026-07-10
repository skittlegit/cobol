# Regulation source archive (T2.5 Phase 0)

Primary PDFs that every clause value, clause number, and old-side text in
`data/regulations/clauses.jsonl` must trace back to. Pinned by sha256 in
`MANIFEST.json` (written by `scripts/pin_regulations.py`).

## Phase 0 is manual — download these yourself

RBI's document host (`rbidocs.rbi.org.in`) is **CAPTCHA-walled to automated
fetches** — verified 2026-07-10: the PDF endpoint returns an HTML bot-challenge
(not `%PDF…`), and the Internet Archive mirror captured the same challenge page.
So Claude Code / any script cannot fetch these; download them by hand from
rbi.org.in (Master Directions / Notifications) and drop them here with the
**exact filenames** below, then run `python scripts/pin_regulations.py`.

| filename | document | why |
|---|---|---|
| `cc-dc-directions-2025.pdf` | RBI (Commercial Banks – CC/DC: Issuance and Conduct) Directions, 2025 (2025-11-28) | current anchor; confirm the secondary-mapped para 1–97 numbering |
| `cc-md-2022-as-issued.pdf` | Credit/Debit Card MD 2022, **as issued 2022-04-21** | P1/P2/P3 old sides (pre-amendment wording) |
| `cc-md-2022-consol-2024.pdf` | Same MD, consolidation "updated as on Mar 07, 2024" | 2024-state sides of P1/P2/P3 |
| `kyc-directions-2025.pdf` | RBI KYC Directions, 2025 (2025-11-28) | resolve the three `PROVISIONAL:` KYC clause_ids |
| `kyc-md-2016-final-consol.pdf` | KYC MD 2016, final pre-repeal consolidation | P4 new-side-in-lineage (10%), P5 (7 days) |
| `kyc-amend-2023-10-17.pdf` | Amendment circular of 2023-10-17 | documents P4's 15%→10% change |
| `kyc-amend-2024-11-06.pdf` | Amendment circular of 2024-11-06 | documents P5's CKYCR ≤7-day introduction |

If a document genuinely cannot be located (e.g. the as-issued 2022 PDF), set its
`MANIFEST.json` entry `"status": "unobtainable"` by hand — the pin script
preserves that, and downstream marks the affected pair *degraded* rather than
substituting a secondary source. Never substitute a non-RBI reproduction (e.g. a
taxguru/complinity copy) for a primary pin.

## After downloading

```bash
python scripts/pin_regulations.py     # writes/refreshes MANIFEST.json
pytest tests/test_sources.py -q        # verifies every pinned hash
```
