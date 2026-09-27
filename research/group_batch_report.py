"""Build a source-linked comparison from completed per-method artifacts."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path('instance/group_batch')
DOC = Path('docs/group_discussions_full_report.md')
items = json.loads((ROOT / 'inventory.json').read_text())
methods = ('existing', 'nvidia', 'psycon')


def clock(seconds):
    seconds = round(seconds)
    return f'{seconds//60}:{seconds%60:02d}'


def fmt(value):
    return f'{value:.2f}' if isinstance(value, (int, float)) else '—'


summaries = {}
for item in items:
    stem = Path(item['file']).stem
    for method in methods:
        path = ROOT / stem / f'{method}-summary.json'
        summaries[item['file'], method] = json.loads(path.read_text()) if path.exists() else {'status': 'pending'}

rows = []
for item in items:
    for method in methods:
        summary = summaries[item['file'], method]
        rows.append({'recording': item['file'], 'method': method, 'status': summary['status'],
                     'duration_s': item['duration_s'], 'visible_faces': item['detected_faces'],
                     'ready_profiles': summary.get('ready_profiles'),
                     'assigned_s': summary.get('assigned_s'),
                     'unknown_s': summary.get('unknown_s'),
                     'overlap_s': summary.get('overlap_s'),
                     'failure_reason': summary.get('reason', '')})
with (ROOT / 'comparison.csv').open('w', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=rows[0])
    writer.writeheader()
    writer.writerows(rows)

profile_rows = []
segment_rows = []
for item in items:
    stem = Path(item['file']).stem
    for method in methods:
        summary = summaries[item['file'], method]
        if summary['status'] != 'complete':
            continue
        profile_rows.extend({'recording': item['file'], 'method': method,
                             'slot': profile['slot'], 'status': profile['status'],
                             'usable_s': profile['usable_s'],
                             'transcription_status': profile.get('transcription')}
                            for profile in summary['profiles'])
        detail = json.loads((ROOT / stem / f'{method}-detail.json').read_text())
        segment_rows.extend({'recording': item['file'], 'method': method,
                             'start_s': row['start_s'], 'end_s': row['end_s'],
                             'status': row['status'], 'slot': row.get('slot_number'),
                             'anonymous_cluster': row.get('cluster_label'),
                             'overlap_excluded_s': row.get('overlap_refused_s', 0),
                             'evidence_reason': (row.get('evidence') or {}).get('reason')}
                            for row in detail['rows'])
for filename, data, fields in (
    ('profiles.csv', profile_rows, ('recording', 'method', 'slot', 'status', 'usable_s', 'transcription_status')),
    ('segments.csv', segment_rows, ('recording', 'method', 'start_s', 'end_s', 'status', 'slot',
                                  'anonymous_cluster', 'overlap_excluded_s', 'evidence_reason')),
):
    with (ROOT / filename).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

lines = [
    '# Group discussion pipeline comparison',
    '',
    'This report compares the current **Existing**, **NVIDIA**, and **PSYCON** code paths on every video in `group_discussions/`. '
    'The methods share source-video PCM at 16 kHz and the numbered faces from each recording’s marked frame. '
    'The five 4K recordings use a synchronized 1920×1080, 25 fps video-only copy for visual scoring; source audio is unchanged, and the runner checks its duration against the decoded PCM within 0.2 seconds.',
    '',
    'A ready profile has at least three usable seconds under its method’s gates. Ready counts measure coverage, not verified attribution accuracy. '
    'Overlapping original audio can be included in playback, while profile and training measurements exclude it. '
    'Participant numbers are positions within each recording; they do not identify the same person across sessions.',
    '',
    '## Recording inventory and marked screenshots',
    '',
    '![Numbered marked frames for all recordings](../instance/group_batch/marked-contact-sheet.jpg)',
    '',
    '| Recording | Duration | Size GB | Visible faces | Marked frame |',
    '| --- | ---: | ---: | ---: | --- |',
]
for item in items:
    screenshot = f"../instance/group_batch/{Path(item['file']).stem}-marked.jpg"
    lines.append(f"| {item['file']} | {clock(item['duration_s'])} | {item['bytes']/1e9:.2f} | "
                 f"{item['detected_faces']} | [image](<{screenshot}>) |")

lines.extend(['', '## Comparison', '',
              '![Ready profiles and unknown clean speech by method](../instance/group_batch/method-comparison.png)',
              '',
              '| Recording | Faces | Existing ready | NVIDIA ready | PSYCON ready |',
              '| --- | ---: | ---: | ---: | ---: |'])
for item in items:
    values = []
    for method in methods:
        summary = summaries[item['file'], method]
        values.append(str(summary['ready_profiles']) if summary['status'] == 'complete' else summary['status'])
    lines.append(f"| {item['file']} | {item['detected_faces']} | " + ' | '.join(values) + ' |')

lines.extend(['', 'The folder contains 11 distinct video files. The `10.19.44 AM` WhatsApp file is byte-identical to the earlier root discussion video, so the earlier rehearsal covers that one folder recording. '
              'Three marked frames show seven people, and the other eight show eight. The runner keeps the detected count for each session instead of inventing an eighth face.',
              '', '### Aggregate run outcomes', '',
              '| Method | Complete runs | Failed runs | Ready profiles in complete runs | Assigned s | Unknown clean s | Excluded overlap s |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
for method in methods:
    complete = [summaries[item['file'], method] for item in items
                if summaries[item['file'], method]['status'] == 'complete']
    failures = sum(summaries[item['file'], method]['status'] == 'failed' for item in items)
    lines.append(f"| {method.upper()} | {len(complete)} | {failures} | "
                 f"{sum(s['ready_profiles'] for s in complete)} | "
                 f"{sum(s['assigned_s'] for s in complete):.2f} | "
                 f"{sum(s['unknown_s'] for s in complete):.2f} | "
                 f"{sum(s['overlap_s'] for s in complete):.2f} |")
lines.extend(['', 'These totals count every file in `group_discussions/` once. Ready counts measure how many numbered faces passed each method’s speech gate; '
              'they are not accuracy scores. Existing does not explicitly separate overlap, so its zero overlap total cannot be compared as an overlap detector result.',
              ''])
visible_slots = sum(item['detected_faces'] for item in items)
psycon_ready = sum(summaries[item['file'], 'psycon']['ready_profiles'] for item in items)
lines.extend([f'Across the 11 folder recordings, PSYCON produced {psycon_ready} ready profiles across '
              f'{visible_slots} visible person-session slots. Most recordings still have people with insufficient clean speech '
              'or unresolved identity, and only the repeated original discussion reached eight ready profiles. '
              'A review confirmation can resolve a supported unknown turn; it cannot manufacture three usable clean seconds for training.',
              ''])

lines.extend(['', '## Per-recording measurements', ''])
for item in items:
    stem = Path(item['file']).stem
    lines.extend([f"### {item['file']}", '',
                  f"Duration {clock(item['duration_s'])}; {item['detected_faces']} numbered faces. "
                  f"[Marked frame](<../instance/group_batch/{stem}-marked.jpg>) · "
                  f"[source video](<../group_discussions/{item['file']}>) · "
                  f"[shared PCM](<../instance/group_batch/{stem}/shared-16khz.wav>) · "
                  f"[timeline](<../instance/group_batch/{stem}/timeline.png>) · "
                  f"[review clips](<../instance/group_batch/{stem}/playback/manifest.json>)", '',
                  '| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |',
                  '| --- | --- | ---: | ---: | ---: | ---: | --- | --- |'])
    for method in methods:
        summary = summaries[item['file'], method]
        status = summary['status']
        usable = ', '.join(f"{p['slot']}:{fmt(p['usable_s'])}"
                           for p in summary.get('profiles', [])) or '—'
        detail = f"../instance/group_batch/{stem}/{method}-detail.json"
        lines.append(f"| {method.upper()} | {status} | {summary.get('ready_profiles', '—')} | "
                     f"{fmt(summary.get('assigned_s'))} | {fmt(summary.get('unknown_s'))} | "
                     f"{fmt(summary.get('overlap_s'))} | {usable} | "
                     f"[detail](<{detail}>) |")
        if status == 'failed':
            lines.extend(['', f"{method.upper()} failure: `{summary.get('reason')}`", ''])
    lines.append('')

lines.extend([
    '## Verification', '',
    '`python -m pytest tests -q --basetemp instance/group_batch_pytest_final -p no:cacheprovider` passed on this branch with six skips. '
    'The GPU batch ran the three method paths on each source recording; each method summary records completion or its explicit failure reason. '
    'The [validation result](../instance/group_batch/validation.json) checks the saved outputs and playback interval provenance.',
    '',
    '`IMG_3997.MOV` reports 832.668 seconds in its container, while its decoded PCM is 831.228 seconds and the visual copy is 831.120 seconds. '
    'The first strict check against container duration failed all three methods before inference. '
    'The runner now compares the visual copy to the PCM actually analyzed, within 0.2 seconds; all three completed on retry. '
    'The worker also emitted optional torchcodec and torchaudio backend warnings, but it processed the predecoded PCM and no final method run failed.',
    '',
    '## What the test establishes', '',
    'The scripts processed each file independently, using its own marked frame, source PCM, and method outputs. '
    'The screenshots and timelines show numbered face detections and where each method placed assigned, unknown, and overlap intervals. '
    'The playback manifests map each generated WAV back to its original source intervals. '
    'The full JSON records the per-turn evidence and profile measurements, including explicit unavailable fields.',
    '',
    'I reviewed the original video at sampled supporting turns for all eight people in the byte-identical earlier discussion recording. '
    'That review found one Community-1 cluster mixing voices that the per-turn face and voice checks separated, and one short participant with only 6.22 usable seconds whose voice similarity of 0.557 is close to the 0.55 gate. '
    'Those findings are documented in [the original-video rehearsal](psycon_discussion_rehearsal.md). '
    'The other recordings have model outputs and marked-frame screenshots but no speaker-by-word human labels; their profile counts must not be read as verified face attribution.',
    '',
    '## Method and evidence definitions', '',
    '**Existing** uses the deployed base worker’s Sherpa diarizer, energy visual windows, and the initial visual matcher; each per-file detail records the diarization engine and transcript. '
    '**NVIDIA** uses pinned Nemotron-3 streaming speaker channels and repeated visual votes. '
    '**PSYCON** uses pinned Community-1 regular and exclusive turns, TalkNet active-speaker checks, SFace identity, and SpeechBrain voice agreement. '
    'The detailed JSON files contain the anonymous turns, assigned and unknown intervals, visual observations, profiles, and evidence reasons.',
    'Pinned revisions and the worker’s GPU and access-token setup are in [the runtime record](psycon_group_runtime.md).',
    '',
    'The repeatable batch code is in [`research/group_batch_inventory.py`](../research/group_batch_inventory.py), '
    '[`research/group_batch_all.ps1`](../research/group_batch_all.ps1), and '
    '[`research/group_batch_run.py`](../research/group_batch_run.py). '
    'The export and visualization scripts in the same directory rebuild the WAV review clips, timeline images, chart, and this report from saved results. '
    'The batch skips completed method summaries, so a failed recording can be retried without rerunning the others.',
    'The [artifact validation](../instance/group_batch/validation.json) checks method counts, participant numbers, PCM boundaries, overlap exclusion, and generated WAV duration.',
    '',
    'The original videos establish what can be seen and heard; no manually annotated speaker-by-word ground truth exists for these recordings. '
    'A model’s ready profile is therefore a candidate for review, and an unassigned interval remains unknown. '
    'Sustained-vowel measures remain unavailable from discussion audio.',
    '',
    '[Machine-readable comparison](../instance/group_batch/comparison.csv) · '
    '[profiles](../instance/group_batch/profiles.csv) · '
    '[segments](../instance/group_batch/segments.csv)',
    '',
])
DOC.write_text('\n'.join(lines))
print(DOC, 'complete method runs', sum(s['status'] == 'complete' for s in summaries.values()),
      'of', len(summaries))
