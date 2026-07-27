# Independent annotation round

`real_curated_blinded.jsonl` is the shared 51-row evidence pack for both
qualified annotators. Its adjacent manifest pins the candidate IDs and the
gold-only fields that must remain absent.

Each annotator writes a separate JSONL file with one
`IndependentAnnotation` object per candidate. The model is defined in
`src/cobol_archaeologist/benchmark/annotation.py`. Included rows carry a full
`DriftPrediction`; excluded or unresolved rows carry no prediction. Both files
must:

- contain every manifest candidate exactly once;
- use one distinct, non-placeholder `annotator_id`;
- record the completion timestamp before either pass is disclosed; and
- be produced without existing gold, mutation metadata, judge output, model
  predictions, or the other annotator's decisions.

Do not commit partially completed pass files as evidence. After both locked
passes exist, generate the pre-adjudication agreement report and retain both
original passes alongside the adjudication change log. T5.1 remains open until
that measured evidence exists.
