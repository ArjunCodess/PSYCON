# Changes and rollback

Added `research/emergency_audit.py` for strict ID/scale validation, baseline replay, a single declared nested experiment, anonymized paired outputs, metrics and charts. Added `tests/research/test_emergency_audit.py` for consequential alignment, abstention, class and selection checks. Existing source labels, live models, prompts and data stores are unchanged. Candidate artifacts are saved separately, without activation. Preserve the existing compact implementation unless reviewed evidence justifies promotion.

Updated `README.md` to distinguish the approximately 64% reference result from model performance, disclose the unsuccessful new experiment and mode reference, and link the local audit outputs. No existing paper, synopsis, presentation or source-data file was overwritten by this audit.

Reproduce with `.runtime/venv/Scripts/python.exe -m research.emergency_audit --output <new-directory>`. The directory must be new, so previous research files cannot be overwritten. Frozen private snapshot and original model archive are required. This run uses native Python/scikit-learn; it is not a new Docker run, live database audit or new LLM inference experiment. Prior report-generation results are separate historical evidence.

Tests and completion checks are recorded in `test_results.txt` after execution. For rollback, revert only the commit containing these audit additions, retaining this output and the user's backup. No source-data rollback is needed because no source records were changed. Do not remove uncommitted user files or consent records.
