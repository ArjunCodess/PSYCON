# PSYCON research interface

The primary audio-only workspace is `backend/templates/instrument.html`, served by `run_psycon.py web` at port 8001. It uses `backend/static/instrument.css` and `instrument.js`. Blinded reviews use a separate form with the same styles and no condition labels.

## Colors and typography

Charcoal `#222b25` carries the navigation. Content uses green-neutral `#f1f2ee`, surface `#fcfcf9`, ink `#252c28`, muted text `#59635d`, deep green `#285c4c`, copper `#8c5437`, and danger `#9a352c`. Use locally hosted Geist for interface text and Geist Mono only for timestamps, precise numeric data, code, and model provenance. The pinned official font files, license, source URLs, and SHA-256 hashes are in `backend/static/fonts`. Labels stay readable; state always includes text.

## Structure and interaction

Seven navigation destinations share a person selector and target communication-profile dropdown. Session inspection uses Overview, Transcript, Measurements, and Analysis sections. Session and section URLs survive refresh and browser navigation. The audio element stays mounted when switching sections, preserving playback position. Processing records, speaker mapping, metadata, and exports remain in Overview; measurements and generated interpretations have separate reading spaces. Every output is accessible independently of the LLM. Native audio players, dialogs, forms, tables, and focus rings preserve familiar behavior.

Layouts collapse below 760px into horizontal navigation and single-column content. Wide tables scroll inside their panels. Only brief control-state transitions use animation, with reduced-motion support. Charts have textual values available in adjacent tables or exports.

Session mapping, metadata editing, and manual event annotation use disclosure controls so reading evidence stays ahead of editing. Dialogs have named headings, native focus trapping, and sticky close controls. Tables and timelines are keyboard-scrollable; timeline intervals support Enter and Space. Research polling refreshes when run states change instead of replacing the reading view every eight seconds. Failed and superseded runs remain in an expandable audit history.

Mobile inputs use 16px text and controls have 44px touch targets. Long filenames, person names, source text, and reference labels wrap without widening the page. Blinded review uses numbered links to frozen cited excerpts and anonymous speaker labels; model and system labels remain concealed.

## Scientific presentation

Do not show a global communication score. Separate measured, estimated, reviewed partial, inferred, exploratory, and unavailable states. Render missing research metrics as `Not evaluated yet`. Compare person dimensions with reference dimensions and show the method, source, sample count, version, and limitations. Citing an existing evidence ID never becomes a claim of validated semantic support.

Legacy pages continue to use their earlier shared styles; their hardware/coaching navigation does not define this workspace.

## Verification

The seven primary views were exercised in the collaborative browser at 390px, 768px, and 1280px using isolated same-origin rendering frames. No page overflow or visible application errors occurred in those 21 checks. Session inspection, the evidence dialog, and blinded review were checked at 390px, including long claim selectors and source links. Visible research text passed a computed contrast check. Screenshot capture and native viewport resize were unavailable in this preview session, so these checks do not constitute a complete visual or assistive-technology audit.

## Evidence workbench update

The dashboard is scoped to original videos in the `Group discussion videos - full audio pipeline` dataset, excluding earlier audio imports and technical smoke runs. Its analyzed duration includes completed sessions only. Actual processing and failed states appear with a direct review action. A next-step prompt leads to a completed recording or personal-history setup.

Recordings can be searched by filename, context, or dataset and filtered by processing status and dataset. Search text and filters persist while using the session list. Transcript search filters retained excerpts without changing the underlying evidence. Notices can be dismissed. Polling avoids replacing completed session views when an unrelated job changes and pauses while audio is playing or a form is being edited.

Geist assets are sourced from [Vercel's official repository](https://github.com/vercel/geist-font) at the revision recorded in the local font manifest, with the supplied SIL Open Font License retained. Font requests are local; no third-party font service is used.

The update was inspected in desktop screenshots with Geist confirmed as the loaded interface font. Session-section switching retained the same audio element and its playback position; transcript search handled an empty result. A check against the live session database confirmed that the dashboard excludes every recording outside the original-video dataset. JavaScript syntax and whitespace checks passed, and the full Python suite passed with 344 tests and five optional integration skips. The preview client failed after a native viewport-resize attempt, so the earlier responsive checks above have not been repeated for this update.

## Speaker report reading flow

The Report section opens the selected speaker's latest completed full PSYCON interpretation inline. It leads with the summary, then separates observed behavior, possible interpretation, confidence, and a suggested adjustment. Expand supporting moments to read exact saved quotes and play the recording at their timestamps. Scope and uncertainty remain accessible. Research condition labels, model configuration, raw JSON, and run history live in secondary disclosures.

Queued and running reports disable duplicate generation and preserve an earlier completed report. Failed and outdated attempts never become current report content. Changing the selected speaker restores keyboard focus and reuses the session audio element. Speaker selection appears only where it changes the displayed measurements or report.

The isolated frontend checks cover source links, text escaping, current-report selection, and empty, pending, updating, failed, stale, and unavailable states. Live data rendering and JavaScript syntax checks passed. An isolated desktop render in the collaborative preview loaded Geist, displayed the four real saved observations, and had no horizontal overflow. The preview then disconnected; screenshots, mobile layout, and live playback checks could not be completed for this update.
