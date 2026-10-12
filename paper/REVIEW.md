# Evidence and review record

Reviewed on October 12, 2026, against main revision `8b126b7` after a fast-forward pull of 44 commits. The initial documentation audit was followed by a live canonical-database audit, transactional overlap application, and exploratory Docker source-score fitting. No new human experiment or missing participant observation was invented.

## Behavioral claim boundaries

| Statement | Evidence | What it does not establish |
| --- | --- | --- |
| Eleven recordings and 85 marked slots | Committed benchmark summary, one row per original recording | Unique participants, recruitment coverage, consent, or independent identity truth |
| Nineteen author-supplied cross-recording identity links; 66 provisional identity components; six provisional recording components | Corrected handwritten notes transcribed in `docs/research/PARTICIPANT_OVERLAP.json`; slot bounds and connected components checked against benchmark counts | A confirmed count of 66 unique people, six statistically independent groups, word-level attribution truth, consent, or live database updates |
| Guarded PSYCON 57; guarded Nemotron modes 51 each | Totals rechecked against per-recording counts; usable durations rechecked against the same JSON | Behavioral accuracy, identity accuracy, significant superiority, or active instrument validation |
| Ten local scans, 228 pages, no extractable text | Read-only PDF inventory; one visually inspected source sheet states 5.0 | All sheets' rubric equivalence, checked transcription, training eligibility, or unique sample size |
| Deployed rubric 4.0; S unavailable and visual-only T excluded | `backend/instrument/forms.py` and `datasets.py`, tracked marksheet/guide | A fully validated psychological measure or complete modality coverage |
| Current A/B/C comparison is bundled | `backend/instrument/research.py` packets and configuration | An isolated causal benefit of personal history |
| Supervised snapshots do not automatically include report history | `datasets.py` frozen features versus `profiles.py` report summaries | A tested historical predictor |
| Archived WESAD 13,698 windows, 15 subjects | Processed CSV and saved model metrics rechecked | Untouched held-out-subject performance, because calm baselines use labelled pre-split windows |
| Hardware remains future work | Firmware and engineering sources; no tracked KiCad files | Sensor calibration, validated assemblies, physiological/behavioral outcomes |

## Code and document scope

The source inventory covers the canonical instrument, group and coaching modules, shared ML utilities, research scripts, validation tools, protocol implementations, firmware, frontend/templates, tests, launchers, and deployment configuration. Detailed checks focused on the source-derived rubric, eligibility, source/person grouping, estimator and metrics, report packets, prior-history rules, audio attribution, durable jobs, original-media registration, and historical benchmark/physiology artifacts. Current and historical workflows are separated in the README and paper.

## Build and verification

- `python paper/build.py` produced an 11-page paper and a two-page synopsis. Final logs had no unresolved citations/references or overflowing boxes. All thirteen document pages were rendered and visually inspected.
- Aggregate count and duration totals match the committed JSON; the graph is regenerated from those counts without accessing participant media.
- Main and synopsis abstracts contain 217 and 225 whitespace-separated words respectively, below the IRIS portal's 300-word maximum. The synopsis has six content blocks including its abstract.
- Presentation headings are exactly 1 through 25; opening team/title and closing-thanks slides are excluded. The Markdown file is intentionally uncommitted.
- Python checks passed 331 tests with five optional skips. The three PostgreSQL-dependent instrument modules, totaling 57 collected tests, were excluded because Docker was unavailable. No complete current integration rerun is claimed.
- TypeScript checking and 20 protocol tests passed. Both frontend report/training behavior scripts passed. Ear and wrist PlatformIO builds succeeded; compilation is not physical verification.
- Git whitespace validation passed after marking PDF artifacts binary. Private scans and the user's prior feature work are outside these commits.

## Source and assistance record

The authoring requests were to update the repository README and paper, create a separate two-page synopsis with the specified Overleaf preprint style, build the PDFs, prepare about 25 presentation slides, and commit the documentation while leaving presentation content uncommitted. The follow-up requested BEHA framing using the Society for Science science-project criteria and explicitly excluded a poster.

AI assisted the code/evidence inventory, proposed prose, bibliography discovery/formatting, diagrams, Python figure/build code, verification, and document preparation. This log does not claim that the prose, reference selection, conclusions, or proposed future experiments are student-independent work. They remain working material to verify against student notebooks and source reading. The official AI-use guidance prohibits several of these uses in initial competition submissions; disclosure or cosmetic rewriting alone does not certify compliance.

Sources checked include the [science judging criteria](https://www.societyforscience.org/isef/grand-award/criteria/), [AI-use table](https://sspcdn.blob.core.windows.net/files/Documents/SEP/ISEF/2026/Rules/Generative-AI-Use-Table.pdf), [human-participant rules](https://www.societyforscience.org/isef/international-rules/human-participants/), [IRIS 2026 portal](https://register.irisnationalfair.org/), requested [Overleaf template](https://www.overleaf.com/latex/templates/style-and-template-for-preprints-arxiv-bio-arxiv/pkzcrhzcdxmc), and the primary/model/software sources recorded in the bibliography. Foundational behavior/measurement references are intentionally older works, not presented as recent findings.

The students must establish their own literature engagement, actual approvals and permission records, recruitment/sample-size information, funding/conflicts, and detailed division of work before producing submission materials. Current fair instructions take precedence over older anonymity guidance. No school/location identifiers, private answers, faces, or consent signatures are included in these outputs.

## Completed source-score training release

The live audit found 76 imported v5.0 forms, 2,432 answers (750 numeric / 1,662 N/O / 20 missing), and no strict behaviorally eligible labels. Missing opportunity, confidence, structured evidence, independent review, and 1,120 answer-row reviewer-provenance fields remain unavailable. Existing mapping status is not independent human identity validation. Permission is user-attested and does not prove prior ethics approval.

Applied nineteen supplied links to 34 participant records representing fifteen known people; eight empty linked seats were added, giving 84 participant-session records. Retained known-source development roles and source ancestry were audited. No raw score, missing answer, consent, or independent review was fabricated. Derived lineage was invalidated when appropriate.

Docker run `b207e378-0698-47f7-bdd4-d50e9ebbb982` completed against frozen source snapshot `c8374764-9afe-4145-bd4c-434f2cdd49fa`. It retained forty examples / nine recordings / five known groups / 488 numeric scores, excluded 1,944 answer rows, and fitted fourteen targets using 423 labels. Fixed C=1.0 and seed 42 were used without a validation search; all examples are training. Every model is explicitly exploratory and active with acknowledged limitations. Fourteen scored API predictions were verified. The private model bundle and public aggregate release were exported from the actual database/artifacts. No held-out accuracy or behavioral effect is available.

Seven focused eligibility/overlap tests passed. The Docker image lacks pytest; host tests and actual Docker fit/API inference are distinct checks. Startup uses the installed instrument image with `--no-build`; the missing `psycon-week4-worker:latest` base prevents a clean image rebuild here. These limitations supersede the initial Docker-unavailable status above. The existing feature stash and private scans remain untouched, and presentation content remains uncommitted.

Final verification: 63 PostgreSQL workflow/training and eligibility/overlap tests passed in a dedicated disposable PostgreSQL 16 database, with the backup/restore test excluded. Both frontend verification scripts passed. The final build produced twelve paper pages and two synopsis pages with resolved references and no overflowing boxes; all fourteen pages were rendered and visually checked. Abstract lengths are 233 and 232 words. Presentation headings remain exactly 1?25. The web health endpoint is passing on the restarted Docker services. Browser automation failed to reach the page, so no new live browser interaction check is claimed.
