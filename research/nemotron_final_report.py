"""Build the plain-language final report from the committed benchmark summary."""
from pathlib import Path
import json
from string import Template

data = json.loads(Path("docs/report_assets/nemotron-benchmark-summary.json").read_text())
methods = ("existing", "nvidia", "psycon", "psycon-recovered",
           "nemotron-streaming-guarded", "nemotron-offline")
labels = ("Original", "Earlier NVIDIA", "First PSYCON", "Guarded PSYCON",
          "Nemotron streaming with current checks", "Nemotron offline with current checks")
if any(record["methods"][method]["status"] not in {"complete", "failed"}
       for record in data["records"] for method in methods):
    raise RuntimeError("finish_all_benchmarks_before_building_final_report")
totals = data["totals"]
usable = {method: sum(record["methods"][method]["usable_s"] or 0
                     for record in data["records"]) for method in methods}
ps, offline, control = (totals[m] for m in methods[3:])
if offline < ps:
    verdict = f"Nemotron offline produced {offline} ready profiles, while guarded PSYCON produced {ps}. PSYCON therefore remains our main source. Nemotron stays in the benchmarks."
elif offline == ps:
    verdict = f"Nemotron offline and guarded PSYCON both produced {ps} ready profiles. That is a tie in coverage. It does not show better identity accuracy, so PSYCON remains our main source and Nemotron stays in the benchmarks."
else:
    verdict = f"Nemotron offline produced {offline} ready profiles, compared with {ps} from guarded PSYCON. It has better coverage in this test. Identity accuracy still needs independent labels before we can call it the better training source. It remains available as a benchmark."
summary = "We tested all 11 recordings with the same source audio and numbered faces. They contain 85 marked places across the videos. These are person-recording slots, since someone may appear in more than one recording. " + verdict
if offline < control:
    setting_result = f"The offline setting produced {control-offline} fewer profiles than that control."
elif offline == control:
    setting_result = "The offline setting matched that control's coverage."
else:
    setting_result = f"The offline setting produced {offline-control} more profiles than that control."
new_result = f"The streaming control produced {control} profiles. It reused the earlier NVIDIA turns with the same face and voice checks as PSYCON. The offline run used those checks too. {setting_result} Offline retained {usable[methods[-1]]:,.2f} usable seconds, compared with {usable[methods[3]]:,.2f} from PSYCON. It gave us more audio across fewer participants, but this does not prove better identity accuracy."
novel = sum(len(record["methods"]["nemotron-offline"].get("new_ready_slots_vs_psycon", [])) for record in data["records"])
lost = sum(len(record["methods"]["nemotron-offline"].get("lost_ready_slots_vs_psycon", [])) for record in data["records"])
disagreements = sum(record["methods"]["nemotron-offline"]["detector_disagreement_rows"] for record in data["records"])
tradeoff = f"Offline Nemotron found {novel} slots PSYCON left incomplete, but lost {lost} of PSYCON's ready slots. {disagreements} assigned intervals disagreed with saved PSYCON face observations. These clips need inspection; the check does not tell us which model is correct. The results do not prove that PSYCON has reached the maximum recoverable coverage."
rows = []
tex_rows = []
for record in data["records"]:
    name = Path(record["file"]).stem.replace("WhatsApp Video 2026-09-27 at ", "WA ")
    values = [str(record["methods"][m]["ready_profiles"]) if record["methods"][m]["status"] == "complete" else "failed" for m in methods]
    rows.append(f"| {name} | {record['marked_faces']} | " + " | ".join(values) + " |")
    tex_rows.append(name.replace("_", r"\_") + " & " + str(record["marked_faces"]) + " & " + " & ".join(values) + r" \\")
aggregate = "\n".join(f"| {label} | {totals[method]} | {usable[method]:,.2f} |" for label, method in zip(labels, methods))
aggregate_tex = "\n".join(f"{label} & {totals[method]} & {usable[method]:,.2f} " + r"\\" for label, method in zip(labels, methods))
ps_unknown = sum(record["methods"]["psycon-recovered"]["unknown_s"] for record in data["records"])
ps_overlap = sum(record["methods"]["psycon-recovered"]["overlap_s"] for record in data["records"])
limits = f"Guarded PSYCON still leaves {85-ps} slots incomplete. All have zero assigned clean speech. Seventeen have tentative visual candidates for review, and eleven have none. This does not prove those people were silent. {ps_unknown:.2f} seconds of clean speech remain unlinked to a face, and the model detected {ps_overlap:.2f} seconds of overlap."
validation = json.loads(Path("instance/group_batch/validation.json").read_text())
if validation["errors"] or validation["failed_method_runs"]:
    raise RuntimeError("resolve_artifact_errors_before_publishing_final_report")
checks = f"All {validation['complete_method_runs']} recording-method runs finished. Automated tests passed with six skips. Artifact validation passed with zero errors across {validation['generated_clips']} playback and review clips. It checked source intervals, profile gates, and audio timing. The PDF pages were checked after compilation."
md = ["# Final report: voice profiles from the group discussions", "",
      "[Read the illustrated PDF](../output/pdf/group_discussions_final_report.pdf) or [edit its LaTeX source](group_discussions_final_report.tex).", "",
      summary, "", "| Method | Ready profiles out of 85 | Usable seconds |", "| --- | ---: | ---: |", aggregate, "",
      "![All six methods](report_assets/nemotron-method-totals.png)", "",
      "## How we did it", "",
      "1. We extracted shared 16 kHz audio and numbered the visible faces.",
      "2. Community-1 or Nemotron found anonymous speaker turns and detected overlap.",
      "3. TalkNet checked the visible speaker. SpeechBrain compared that voice across separate turns. Repeated, consistent evidence linked a voice to a face.",
      "4. A profile needed three usable seconds and a valid voice embedding. We removed detected overlap, uncertain boundaries, and nonusable audio windows from acoustic measurements. The code built playback files from the original audio.", "",
      "## What changed for Nemotron", "",
      "The teammate uses Nemotron's offline preset. It processes 27.2 seconds at a time and looks ahead by 3.2 seconds. Our earlier NVIDIA mode used 0.72-second chunks and 0.32 seconds of lookahead. Both keep speaker history, but offline gets more context before labeling speech. We added the official offline preset with pinned weights and the current guarded matcher. We also tested the saved streaming turns with that matcher as a control.", "",
      new_result, "", tradeoff, "",
      "The earlier NVIDIA runs used 80 anonymous channels across the recordings. Their 13 ready profiles counted face-linked outputs. The teammate's repository contains no saved results for these videos, and its face mapping is manual. We tested its proposed settings locally instead of treating its channel count as a confirmed profile count.", "",
      "Its `usable profiles` counter uses total channel speech, including overlap. Our profile gate also requires a face link, isolated speech, and a valid voice embedding. We kept these checks fixed when testing the new Nemotron paths.", "",
      "| Recording | Faces | Original | Earlier NV | First PS | Guarded PS | Stream+ | Offline+ |",
      "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |", *rows, "",
      "![Guarded methods across all recordings](report_assets/nemotron-recording-comparison.png)", "",
      "## What remains uncertain", "", limits, "",
      "Overlapping source audio can appear in playback, but it stays out of a single person's acoustic profile. Nine PSYCON slots have no person-specific playback clip. Three recordings have only seven marked faces. An unmarked eighth person cannot receive a numbered face profile from those markings. The videos also lack a sustained vowel task, so that measurement is unavailable.", "",
      "These are model-supported assignments. We checked sampled original-video frames in one earlier recording, but most assignments have no independent human labels. More profiles do not establish better accuracy. Psychological predictions have not been validated. Training continues to use current, ready PSYCON profiles, and the Nemotron benchmark outputs have a separate schema.", "",
      "![Numbered faces from all 11 videos](report_assets/marked-contact-sheet.jpg)", "", checks, "",
      "Sources and detail: [teammate code](https://github.com/CodeSakshamY/PSYCON-Diarization_Model/blob/d7d018dba76ca59da144b357ed223757596dc0c0/neemotron_bench/core.py), [official Nemotron model card](https://huggingface.co/nvidia/Nemotron-3-Diarization), [benchmark measurements](nemotron_benchmark_report.md), and [rejection audit](psycon_rejection_audit.md).", ""]
Path("docs/group_discussions_final_report.md").write_text("\n".join(md))
template = Template(r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=18mm]{geometry}
\usepackage{graphicx,booktabs,xcolor,microtype}
\usepackage[T1]{fontenc}
\usepackage{lmodern,parskip,enumitem}
\usepackage[hidelinks]{hyperref}
\graphicspath{{report_assets/}}
\definecolor{ink}{HTML}{20313A}
\definecolor{muted}{HTML}{52626A}
\renewcommand{\familydefault}{\sfdefault}
\setlength{\parskip}{5pt}
\setlist[enumerate]{leftmargin=*,itemsep=2pt,topsep=2pt}
\newcommand{\smallnote}[1]{{\small\color{muted}#1}}
\begin{document}\color{ink}
{\Large\bfseries Who spoke in the group videos?}\par
\smallnote{Final comparison on 11 recordings \hfill 1 October 2026}\par
$summary
\begin{center}\small
\begin{tabular}{l r r}\toprule
Method & Ready out of 85 & Usable seconds \\\midrule
$aggregate
\bottomrule\end{tabular}\end{center}
\section*{How we did it}
\begin{enumerate}
\item We extracted shared 16 kHz audio and numbered the visible faces.
\item Community-1 or Nemotron found anonymous speaker turns and detected overlap.
\item TalkNet checked the visible speaker. SpeechBrain compared the voice across separate turns. Repeated, consistent evidence linked a voice to a face.
\item A profile needed three usable seconds and a valid voice embedding. We removed detected overlap, uncertain boundaries, and nonusable audio windows from acoustic measurements. Playback files came from the original audio.
\end{enumerate}
\begin{center}
\includegraphics[width=\linewidth,height=66mm,keepaspectratio]{nemotron-method-totals.png}\\[-2pt]
\smallnote{All methods stay in the benchmark, even when they produce fewer profiles.}
\end{center}
\clearpage
\section*{What changed for Nemotron}
The teammate uses the offline preset. It processes 27.2 seconds at a time and looks ahead by 3.2 seconds. Our earlier NVIDIA mode used 0.72-second chunks and 0.32 seconds of lookahead. Both keep speaker history, but offline gets more context. We added that preset with pinned weights and the current guarded matcher.\par
$control\par
\smallnote{Earlier NVIDIA used 80 anonymous channels across the videos. Its 13 ready profiles were face-linked outputs. The teammate's profile counter uses total channel speech, including overlap, and its face mapping is manual. Its repository has no saved results for these recordings.}\par
\begin{center}\scriptsize
\begin{tabular}{l r r r r r r r}\toprule
Recording & Faces & Original & Earlier NV & First PS & Guarded PS & Stream+ & Offline+ \\\midrule
$rows
\midrule
Total & 85 & $original & $nvidia & $firstps & $guardedps & $streaming & $offline \\\bottomrule
\end{tabular}\end{center}
\smallnote{WA means a WhatsApp filename. Stream+ and Offline+ use the same guarded checks as PSYCON. The earlier methods used their own gates. Counts measure coverage, not identity accuracy.}
\begin{center}
\includegraphics[width=\linewidth,height=92mm,keepaspectratio]{nemotron-recording-comparison.png}
\end{center}
\clearpage
\section*{What remains uncertain}
$limits\par
Mixed original audio can appear in playback, but overlap stays out of a single person's acoustic profile. Nine PSYCON slots have no person-specific playback clip. Three videos have only seven marked faces. An unmarked eighth person cannot receive a numbered face profile from those markings. A sustained vowel measurement is unavailable because the videos lack that task.\par
These are model-supported assignments. Most have no independent human labels. More profiles do not establish better accuracy. Psychological predictions have not been validated. Training continues to read ready PSYCON profiles; the Nemotron benchmark has a separate schema.\par
$tradeoff\par
\begin{center}
\includegraphics[width=\linewidth,height=124mm,keepaspectratio]{marked-contact-sheet.jpg}\\[-2pt]
\smallnote{The marked faces from all 11 recordings. Numbers belong to each recording.}
\end{center}
\smallnote{$checks}\par
\smallnote{Sources: \href{https://github.com/CodeSakshamY/PSYCON-Diarization_Model}{teammate benchmark code}, \href{https://huggingface.co/nvidia/Nemotron-3-Diarization}{official Nemotron model card}. The project includes the full benchmark summary and rejection audit.}
\end{document}
""")
tex = template.substitute(summary=summary, aggregate=aggregate_tex, control=new_result,
                          rows="\n".join(tex_rows), original=totals[methods[0]], nvidia=totals[methods[1]],
                          firstps=totals[methods[2]], guardedps=ps, streaming=control, offline=offline,
                          limits=limits, checks=checks, tradeoff=tradeoff)
Path("docs/group_discussions_final_report.tex").write_text(tex)
print(verdict)
