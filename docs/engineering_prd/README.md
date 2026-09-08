# PSYCON Engineering PRD

Publication-quality, double-column LaTeX conversion of the PSYCON Engineering
Design Document, styled to resemble a biomedical-engineering / PubMed-indexed
journal paper (e.g., IEEE Transactions on Biomedical Engineering). The
document is organized into five `\part`s: **Volume 1 — Project Foundation**
(Chapters 1–8), **Volume 2 — Manufacturing, Mechanical Design & Future
Roadmap** (Chapter 9), **Volume 3 — Reference Documentation**
(Chapters 10–16), **Volume 4 — Research Methodology, Ethics & Competition
Documentation** (Chapters 17–23), and **Volume 5 — Appendices, Reference
Material & Project Closure** (Chapters 24–34, the final chapter).

## Project Structure

```
docs/engineering_prd/
├── main.tex                    # Document driver: title, abstract, chapter includes
├── preamble.tex                 # All packages, page geometry, custom environments
├── references.bib               # Verified core component, ethics, and WESAD references
├── chapters/
│   ├── chapter1_overview.tex        # Ch. 1 — Project Overview
│   ├── chapter2_srs.tex             # Ch. 2 — System Requirements Specification
│   ├── chapter3_architecture.tex    # Ch. 3 — Overall System Architecture
│   ├── chapter4_hardware.tex        # Ch. 4 — Complete Hardware Design
│   ├── chapter5_electrical.tex      # Ch. 5 — Electrical Design & Complete Wiring
│   ├── chapter6_firmware.tex        # Ch. 6 — Firmware Architecture & Software Design
│   ├── chapter7_ai_pipeline.tex     # Ch. 7 — AI Pipeline, Backend Architecture & ML Design
│   ├── chapter8_integration.tex     # Ch. 8 — System Integration, Verification, Validation & Deployment (end of Volume 1)
│   ├── chapter9_manufacturing.tex   # Ch. 9 — Manufacturing, PCB Design & Mechanical Engineering (start of Volume 2)
│   ├── chapter10_bom.tex            # Ch. 10 — Complete Bill of Materials (start of Volume 3)
│   ├── chapter11_gpio.tex           # Ch. 11 — Complete GPIO Assignment
│   ├── chapter12_wiring_rules.tex   # Ch. 12 — Wiring Rules
│   ├── chapter13_calibration.tex    # Ch. 13 — Calibration Summary
│   ├── chapter14_test_log.tex       # Ch. 14 — Test Log Template
│   ├── chapter15_risk_register.tex  # Ch. 15 — Risk Register
│   ├── chapter16_deliverables.tex   # Ch. 16 — Project Deliverables (end of Volume 3)
│   ├── chapter17_research_methodology.tex  # Ch. 17 — Research Methodology (start of Volume 4)
│   ├── chapter18_data_management.tex       # Ch. 18 — Data Management
│   ├── chapter19_ethics_privacy.tex        # Ch. 19 — Ethics & Privacy
│   ├── chapter20_statistical_analysis.tex  # Ch. 20 — Statistical Analysis Plan
│   ├── chapter21_competition_docs.tex      # Ch. 21 — Competition Documentation
│   ├── chapter22_demonstration_plan.tex     # Ch. 22 — Demonstration Plan
│   ├── chapter23_limitations.tex           # Ch. 23 — Project Limitations (end of Volume 4)
│   ├── chapter24_reference_index.tex       # Ch. 24 — Datasheet & Reference Index (start of Volume 5)
│   ├── chapter25_comm_protocol.tex         # Ch. 25 — Communication Protocol
│   ├── chapter26_firmware_ref.tex          # Ch. 26 — Firmware Architecture (reference summary)
│   ├── chapter27_backend_architecture.tex  # Ch. 27 — Backend Software Architecture
│   ├── chapter28_test_procedures.tex       # Ch. 28 — Complete Test Procedures
│   ├── chapter29_maintenance_schedule.tex  # Ch. 29 — Maintenance Schedule
│   ├── chapter30_troubleshooting.tex       # Ch. 30 — Troubleshooting Guide
│   ├── chapter31_glossary.tex              # Ch. 31 — Glossary
│   ├── chapter32_revision_history.tex      # Ch. 32 — Revision History
│   ├── chapter33_final_checklist.tex       # Ch. 33 — Final Project Checklist
│   └── chapter34_conclusion.tex            # Ch. 34 — Conclusion (end of document)
├── figures/                     # (reserved for exported/rasterized figures, if any)
└── sections/                    # (reserved for future non-chapter sections, e.g. appendices)
```

As you provide additional chapters, each will be added as its own file under
`chapters/` and included in `main.tex` via `\input{chapters/...}`, preserving
a clean, modular, one-file-per-chapter structure.

## How to Compile

### Overleaf
1. Upload/zip the entire `docs/engineering_prd/` folder and create a new Overleaf project from it.
2. Set the compiler to **pdfLaTeX** and the bibliography backend to **Biber**
   (Overleaf → Menu → Settings → check "Biber" is selected; this is Overleaf's default
   when `biblatex` is detected).
3. Click Recompile. Overleaf will run pdfLaTeX → Biber → pdfLaTeX → pdfLaTeX automatically.

### Local compilation (TeX Live)
```bash
pdflatex -interaction=nonstopmode main.tex
biber main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

This project was last compiled with MiKTeX 25.12 using pdfLaTeX and Biber,
with **zero errors, zero undefined references, and zero
overfull boxes** after the full four-pass sequence above, across all
40 pages, 34 chapters, and 5 volumes. This is the complete PSYCON Engineering Design
Document.

## Current implementation note

Week 5 has an implemented metadata, synchronized-dataset, participant-split, model-comparison, and reporting path, but no completed psychologist marksheet dataset or matching PSYCON participant recordings. Week 6 adds evidence records, five ordered physical stage gates, backend failure scenarios, timed simulated stress tooling, validation reports, calibration procedures, and risk-evidence rules. No physical measurements have been supplied, so the Week 6 exit gate remains open; `docs/validation/WEEK_6_RUNBOOK.md` defines the required handoff.

## Design Conventions Used

- **Layout:** `article` class, `twocolumn`, A4, 10pt base font, `geometry`-controlled margins.
- **Full-width elements:** system architecture diagrams and wide tables use
  `figure*` / span-safe tables so they are never cramped into a single column
  (per the readability rule — see `fig:system-architecture` in Chapter 1).
- **Diagrams:** all diagrams are native TikZ (no raster/ASCII art), using a
  consistent color/shape legend: sensors (gray), controllers (orange),
  power (green), host/analysis (violet).
- **Tables:** `booktabs` + `tabularx` for clean rules and automatic column
  wrapping; captions/labels are cross-referenced with `cleveref`.
- **Custom callout environments** (defined in `preamble.tex`, usable in any
  chapter file):
  - `engnote` — Engineering Note
  - `warningbox` — Warning
  - `researchnote` — Research Note
  - `designnote` — Design Note
  - `assumptionbox` — Assumption
  - `validationbox` — Validation
  - `requirementbox` — Requirement
  - `futureworkbox` — Future Work
  - `observationbox` — Observation

  Usage example:
  ```latex
  \begin{assumptionbox}
  Text describing an unverified engineering assumption.
  \end{assumptionbox}
  ```

  Two custom list styles are also available for checklist-style content:
  - `checklist` — pending items, marked with ☐ (`\begin{checklist}...\end{checklist}`)
  - `donelist` — completed items, marked with a green ✓ (`\begin{donelist}...\end{donelist}`)
- **Bibliography:** `biblatex` + `biber`, numeric-compact style. The bibliography contains verified manufacturer documents for the named core components plus ICMR, WHO, and WESAD sources. Exact purchased-board, protection-device, cell, electrode, connector, and enclosure references remain open.
- **Content fidelity:** all technical content from the source document is
  preserved, and dated implementation notes are appended where repository
  evidence changed. Confirmed vs. pending-validation engineering status is kept
  explicit (see `validationbox` / `requirementbox` in Chapter 1).

## Status

| Chapter | Status |
|---|---|
| **Volume 1: Project Foundation** | |
| 1 — Project Overview | ✅ Converted |
| 2 — System Requirements Specification | ✅ Converted |
| 3 — Overall System Architecture | ✅ Converted |
| 4 — Complete Hardware Design | ✅ Converted |
| 5 — Electrical Design & Complete Wiring | ✅ Converted |
| 6 — Firmware Architecture & Software Design | ✅ Converted |
| 7 — AI Pipeline, Backend Architecture & ML Design | ✅ Converted |
| 8 — System Integration, Verification, Validation & Deployment | ✅ Converted |
| **Volume 2: Manufacturing, Mechanical Design & Future Roadmap** | |
| 9 — Manufacturing, PCB Design & Mechanical Engineering | ✅ Converted |
| **Volume 3: Reference Documentation** | |
| 10 — Complete Bill of Materials | ✅ Converted |
| 11 — Complete GPIO Assignment | ✅ Converted |
| 12 — Wiring Rules | ✅ Converted |
| 13 — Calibration Summary | ✅ Converted |
| 14 — Test Log Template | ✅ Converted |
| 15 — Risk Register | ✅ Converted |
| 16 — Project Deliverables | ✅ Converted |
| **Volume 4: Research Methodology, Ethics & Competition Documentation** | |
| 17 — Research Methodology | ✅ Converted |
| 18 — Data Management | ✅ Converted |
| 19 — Ethics & Privacy | ✅ Converted |
| 20 — Statistical Analysis Plan | ✅ Converted |
| 21 — Competition Documentation | ✅ Converted |
| 22 — Demonstration Plan | ✅ Converted |
| 23 — Project Limitations | ✅ Converted |
| **Volume 5: Appendices, Reference Material & Project Closure** | |
| 24 — Datasheet & Reference Index | ✅ Converted |
| 25 — Communication Protocol | ✅ Converted |
| 26 — Firmware Architecture (reference summary) | ✅ Converted |
| 27 — Backend Software Architecture | ✅ Converted |
| 28 — Complete Test Procedures | ✅ Converted |
| 29 — Maintenance Schedule | ✅ Converted |
| 30 — Troubleshooting Guide | ✅ Converted |
| 31 — Glossary | ✅ Converted |
| 32 — Revision History | ✅ Converted |
| 33 — Final Project Checklist | ✅ Converted |
| 34 — Conclusion | ✅ Converted |

**The complete PSYCON Engineering Design Document is now fully converted** —
all 34 chapters across 5 volumes, 40 pages, compiling cleanly with zero
errors and zero overfull boxes. If further chapters, appendices, or a
revised volume follow, paste them and they will be converted and appended
in the same style, maintaining consistent numbering, cross-references, and
the shared preamble/environments defined here.
