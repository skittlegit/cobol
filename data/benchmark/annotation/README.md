# Independent annotation round

`real_curated_blinded.jsonl` is the shared 51-row evidence pack for the human
primary annotation and Claude verification passes. Its adjacent manifest pins
the candidate IDs and the gold-only fields that must remain absent.

Each review role writes a separate JSONL file with one
`IndependentAnnotation` object per candidate. The model is defined in
`src/cobol_archaeologist/benchmark/annotation.py`. Included rows carry a full
`DriftPrediction`; excluded or unresolved rows carry no prediction. Both files
must:

- contain every manifest candidate exactly once;
- use one distinct, non-placeholder role `annotator_id`;
- record the completion timestamp before final review; and
- be produced without existing gold, mutation metadata, judge output, model
  predictions, or unrecorded changes to the other pass.

Do not commit partially completed pass files as evidence. After both locked
passes exist, generate the pre-final-review agreement report and retain both
original passes alongside the final-review change log. T5.1 is complete only
when that measured evidence and the human final decisions exist.
