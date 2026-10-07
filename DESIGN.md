# PSYCON research interface

The primary audio-only workspace is `backend/templates/instrument.html`, served by `run_psycon.py web` at port 8001. It uses `backend/static/instrument.css` and `instrument.js`. Blinded reviews use a separate form with the same styles and no condition labels.

## Colors and typography

Charcoal `#222b25` carries the navigation. Content uses sand-neutral `#f3f1eb`, surface `#fbfaf6`, ink `#252c28`, muted text `#59635d`, deep green `#285c4c`, copper `#8c5437`, and danger `#9a352c`. Use Segoe UI / system sans for interface text and Consolas for timing and numeric provenance. Labels stay readable; state always includes text.

## Structure and interaction

Seven navigation destinations share a person selector and target communication-profile dropdown. Session inspection follows the pipeline, then exposes speaker mapping, transcript, context, measurements, evidence links, baseline, reference comparison, and interpretation. Every output is accessible independently of the LLM. Native audio players, dialogs, forms, tables, and focus rings preserve familiar behavior.

Layouts collapse below 760px into horizontal navigation and single-column content. Wide tables scroll inside their panels. Only brief control-state transitions use animation, with reduced-motion support. Charts have textual values available in adjacent tables or exports.

Session mapping, metadata editing, and manual event annotation use disclosure controls so reading evidence stays ahead of editing. Dialogs have named headings, native focus trapping, and sticky close controls. Tables and timelines are keyboard-scrollable; timeline intervals support Enter and Space. Research polling refreshes when run states change instead of replacing the reading view every eight seconds. Failed and superseded runs remain in an expandable audit history.

Mobile inputs use 16px text and controls have 44px touch targets. Long filenames, person names, source text, and reference labels wrap without widening the page. Blinded review uses numbered links to frozen cited excerpts and anonymous speaker labels; model and system labels remain concealed.

## Scientific presentation

Do not show a global communication score. Separate measured, estimated, reviewed partial, inferred, exploratory, and unavailable states. Render missing research metrics as `Not evaluated yet`. Compare person dimensions with reference dimensions and show the method, source, sample count, version, and limitations. Citing an existing evidence ID never becomes a claim of validated semantic support.

Legacy pages continue to use their earlier shared styles; their hardware/coaching navigation does not define this workspace.

## Verification

The seven primary views were exercised in the collaborative browser at 390px, 768px, and 1280px using isolated same-origin rendering frames. No page overflow or visible application errors occurred in those 21 checks. Session inspection, the evidence dialog, and blinded review were checked at 390px, including long claim selectors and source links. Visible research text passed a computed contrast check. Screenshot capture and native viewport resize were unavailable in this preview session, so these checks do not constitute a complete visual or assistive-technology audit.
