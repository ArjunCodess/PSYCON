# Paper and two-page synopsis

[Paper PDF](main.pdf), [synopsis PDF](synopsis.pdf) and [25-slide content](../docs/IRIS_PRESENTATION.md) now use the 13 October maximum-defensible audit. The source-score pilot has 423 ratings from forty participant-session examples, nine recordings and five known connected groups. Historical predictions refit exactly. Compact achieves 62.19% agreement/0.490 MAE on the common 402 ratings; new nested pooling achieves 65.67%/0.453, exactly matching the mode reference and losing score-3 recall. No candidate is promoted and no independent final test supports 85%.

The later [pipeline autopsy](../docs/research/pipeline-autopsy-2026-10-13/full_pipeline_report.md) adds 51 feature-family/model diagnostics and a chronological-order regression fix. Its inner-selected challenger reaches 251/402 correct (62.44%, MAE 0.488) and is not promoted; the compact reference remains unchanged.

The [aggregate audit](../docs/research/maximum-defensible-2026-10-13/submission_results.md) records every comparison, both denominators, class behaviour and limitations. Private inputs and individual predictions remain under `.runtime`; public figures and metrics use aggregate data only. The earlier audiovisual coverage comparison and training-resubstitution scores describe separate evidence. Independent rater reliability, reviewed labels, a fresh identity-resolved test sample and blinded report/history benefit remain pending.

## Build

Run `python paper/build.py` from the repository root with matplotlib, PyMuPDF, latexmk, pdflatex and bibtex installed. The builder regenerates aggregate figures, checks references and overflowing boxes, verifies that the synopsis has exactly two pages, and publishes both PDFs only after successful builds. Sources are [main.tex](main.tex), [synopsis.tex](synopsis.tex) and [references.bib](references.bib). Upload this directory to Overleaf and select the intended main document.

Both documents use `article` with the preprint style attributed in [TEMPLATE.md](TEMPLATE.md) and [arxiv-LICENSE.txt](arxiv-LICENSE.txt). These remain AI-assisted working drafts for author verification. Approval/permission statements, references and student contributions require verification from the actual records; document compilation does not establish human-study validity. See [REVIEW.md](REVIEW.md) for dated evidence and assistance records. Earlier build/test counts are historical. No private scans, signatures, participant notes or faces are published, and no poster is included.
