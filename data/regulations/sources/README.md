# Regulation source archive (T2.5)

Primary RBI PDFs that every clause value, clause number, and old-side text in
`data/regulations/clauses.jsonl` must trace back to. Each is pinned by sha256 in
`MANIFEST.json` (written by `scripts/pin_regulations.py`).

| filename | document | doc_role |
|---|---|---|
| `cc-dc-directions-2025.pdf` | RBI (Commercial Banks – CC/DC: Issuance and Conduct) Directions, 2025 (RBI/DOR/2025-26/155, 2025-11-28) | current anchor |
| `cc-md-2022-as-issued.pdf` | Credit/Debit Card MD 2022, as issued 2022-04-21 (DoR.AUT.REC.No.27) | P1/P2/P3 old sides |
| `cc-md-2022-consol-2024.pdf` | Same MD, "Updated as on March 07, 2024" | 2024-state sides |
| `kyc-directions-2025.pdf` | RBI (Commercial Banks – KYC) Directions, 2025 (RBI/DOR/2025-26/169, 2025-11-28) | KYC current anchor |
| `kyc-md-2016-final-consol.pdf` | KYC MD 2016, consolidated through 2025 (pre-repeal) | P4/P5 lineage new sides |
| `kyc-md-2016-consol-pre-2023-10.pdf` | KYC MD 2016, archived by Wayback on 2022-09-01 (consolidated through 2018-07-12) | P4 old 15% side; P5 old-side absence |
| `kyc-amend-2023-10-17.pdf` | Amendment to KYC MD, 2023-10-17 (DOR.AML.REC.44) — the 7-page **annexure** `MDKYC17102023_Annexure.pdf` (not the covering letter) | P4's change event (see note: descriptive, doesn't quote 15%/10%) |
| `kyc-amend-2024-11-06.pdf` | Amendment to KYC MD, 2024-11-06 (DOR.AML.REC.49) | P5's CKYCR ≤7-day |

> All 8 pinned. The 2023-10-17 amendment annexure describes the BO-partnership
> change but does not quote the 15%/10% figures. Source #8 supplies P4's **old
> 15% side** and P5's old-side absence; 10% is in
> `kyc-md-2016-final-consol.pdf`.

## Maintenance

```bash
python scripts/pin_regulations.py     # (re)write MANIFEST.json
python scripts/pin_regulations.py --check   # verify hashes only
pytest tests/test_sources.py -q
```

Re-pinning a file whose bytes changed is a hard error (provenance break). If a
document is ever confirmed unobtainable, set its `MANIFEST.json` entry
`"status": "unobtainable"` by hand — the pin script preserves it, and downstream
marks the affected pair *degraded* rather than substituting a non-RBI copy.
