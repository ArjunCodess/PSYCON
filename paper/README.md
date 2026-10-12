# BEHA paper and separate synopsis

The consent update records review of nine private signed discussion-participation sheets. The authors confirm recording/training permissions, applicable parental permission and prior approval in the complete records. This confirmation is distinguished from independent checking of the photographed evidence. See [the anonymized review](../docs/CONSENT_REVIEW.md). Signed photographs remain local and excluded from commits.

The latest compact-model update builds a fifteen-page paper and exactly two-page synopsis, with abstract lengths 275/232 words and resolved references/layout. Four/eight-feature models, cumulative ordinal classifiers and shallow ensembles produced 62.2% agreement, MAE 0.490 and 30.0% class sensitivity on the same 402 observations, still below the median reference in agreement/error. Fourteen fitted artifacts remain candidates; no independent final test or personalization benefit is established. Forty-one focused tests, both frontend scripts and one PostgreSQL report-comparison integration test passed. See [the current review record](REVIEW.md) for scope and assistance boundaries. The uncommitted presentation now contains complete text for all 25 content slides.

The current defensibility revision builds a fourteen-page paper and exactly two-page synopsis, with resolved references and no overflowing boxes. Both retrospective repair attempts are disclosed: MAE-oriented selection improves exact agreement to 60.9% but loses to the median reference and reduces class sensitivity; sensitivity-oriented selection achieves 56.5% agreement and fails to improve original class-average sensitivity. Neither is an independent final test. The final fitted artifacts remain exploratory candidates.

Twenty-nine focused model/report/packet tests and both frontend verification scripts pass. The new PostgreSQL workflow rerun stalled, and a separate training rerun completed one test before further waits; complete integration verification is unresolved. These fits ran natively because Docker's Linux daemon was unavailable. Current report output uses explicit measurements, cautious bounded generation and an untested prewritten goal exercise. See [the latest review record](REVIEW.md) for execution, assistance and approval-record boundaries; historical test counts below do not certify this patch.

[Paper PDF](main.pdf) and [two-page synopsis PDF](synopsis.pdf) frame PSYCON as research on contextual communication behavior, with software as the measurement tool. Sources are [main.tex](main.tex), [synopsis.tex](synopsis.tex), and [references.bib](references.bib). The paper leads with behavioral hypotheses, operational definitions, human observations, independent units, controls, and validity; engineering details follow as supporting methods and an appendix.

These are AI-assisted working drafts for author verification and independent writing, not certified submission-ready materials. The official [AI-use table](https://sspcdn.blob.core.windows.net/files/Documents/SEP/ISEF/2026/Rules/Generative-AI-Use-Table.pdf) rejects AI-written initial papers, plans, abstracts, conclusions, and starter bibliographies. Rewording this draft alone is not a certification that those requirements are met. The students must develop submission materials from their own research work and sources. See also the current [rules](https://www.societyforscience.org/isef/international-rules/) and [science judging criteria](https://www.societyforscience.org/isef/grand-award/criteria/). No poster is included.

## Build

With Python, matplotlib, PyMuPDF, and TeX tools `pdflatex`, `bibtex`, and `latexmk`, run from the repository root:

```powershell
python paper/build.py
```

The builder regenerates aggregate figures from the committed benchmark JSON, compiles both sources in a temporary directory, checks references and layout warnings, verifies the synopsis is exactly two pages, and copies the PDFs here. Intermediate files stay outside the repository. Upload this directory to Overleaf and select `main.tex` or `synopsis.tex` as the main document.

The initial October 12 build produced an 11-page paper and exactly two-page synopsis, with resolved citations and no overflowing boxes. Both firmware targets compiled, protocol typechecking and 20 tests passed, and both frontend behavior scripts passed. The available Python run passed 331 tests with five skips, excluding the three PostgreSQL-dependent instrument suites because Docker was unavailable. This does not claim a fresh complete integration or human-study validation. [Review record](REVIEW.md) records evidence and assistance boundaries.

Both use `article` and the `arxiv.sty` preprint style shown in the requested [Overleaf template](https://www.overleaf.com/latex/templates/style-and-template-for-preprints-arxiv-bio-arxiv/pkzcrhzcdxmc). Attribution and the upstream license are in [TEMPLATE.md](TEMPLATE.md) and [arxiv-LICENSE.txt](arxiv-LICENSE.txt).

## Evidence boundaries

- Human rater agreement, held-out A--T accuracy, and blinded report benefit remain pending; no synthetic score replaces them.
- The 85 benchmark slots span eleven recordings and are not unique participants. Ready-profile counts measure coverage, not psychological or identity accuracy.
- Ten private bundles contain 228 image-only pages; 76 v5.0 forms are imported separately from the legacy v4.0 rubric. Fourteen exploratory source-score models used 423 real labels, with no independent validation/test set. Missing human evidence remains missing; no private scan or individual response is published.
- The implemented A/B/C experiment changes history, evidence, and references together; a history-only ablation is needed to isolate history's effect.
- Archived WESAD metrics concern a different physiology task with a label-informed calm baseline; hardware is paused, wrist values are placeholders, and no tracked KiCad design exists.

School, city, and state names are omitted conservatively from the submission copy; the current portal should be checked rather than assuming an older anonymity guideline still applies. Funding, conflicts, recruitment counts, and approvals are not invented. The presentation at `docs/IRIS_PRESENTATION.md` has exactly 25 numbered content slides and is intentionally uncommitted.

The completed Docker source-score fit and aggregate target counts are documented in [the training release](../docs/report_assets/source-training-summary.json). Seven new eligibility/overlap tests and fourteen scored API predictions passed; this verifies execution, not behavioral accuracy. See the updated review record for remaining human-validation and clean-image-build dependencies.

The final training update built a 12-page paper and exactly two-page synopsis. Both abstracts remain below 300 words (233 and 232); all fourteen PDF pages were rendered and visually checked. The current PostgreSQL/eligibility run passed 63 tests in a dedicated disposable PostgreSQL 16 database, excluding the backup/restore test; both frontend verification scripts passed.

The grouped-analysis update builds a 13-page paper and exactly two-page synopsis; all fifteen pages were rendered and visually checked. The added aggregate figure separates training agreement from retrospective omitted-group performance, with zero independent final-test examples. Reproduce the diagnostics with `python -m research.analyze_source_training` using the local frozen snapshot and saved weights; committed aggregate results are in `docs/report_assets/source-cross-validation-summary.json`. The report-input compaction tests and existing LLM tests passed (11 tests), and an actual full-input local LLM run completed. Its output does not establish personalization benefit.
