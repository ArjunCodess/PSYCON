"""Render the threshold study and current per-recording recovery results."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path('instance/group_batch')
DOC = Path('docs/psycon_recovery_report.md')
items = json.loads((ROOT / 'inventory.json').read_text())
methods = ('existing', 'nvidia', 'psycon', 'psycon-recovered')
summaries = {}
for item in items:
    folder = ROOT / Path(item['file']).stem
    for method in methods:
        summaries[item['file'], method] = json.loads((folder / f'{method}-summary.json').read_text())

fig, ax = plt.subplots(figsize=(14, 6.5))
positions = np.arange(len(items))
colors = ('#a9a9a9', '#5f8294', '#c48343', '#446b50')
for index, method in enumerate(methods):
    ax.barh(positions + (index-1.5)*.19,
            [summaries[item['file'], method]['ready_profiles'] for item in items],
            height=.175, label=method.replace('-', ' ').title(), color=colors[index])
ax.set_yticks(positions, [Path(item['file']).stem.replace('WhatsApp Video 2026-09-27 at ', 'WA ')
                          for item in items], fontsize=9)
ax.invert_yaxis()
ax.set_xlabel('Training-ready numbered voice profiles')
ax.set_xlim(0, 8.5)
ax.set_xticks(range(9))
ax.grid(axis='x', alpha=.2)
ax.set_axisbelow(True)
ax.legend(ncol=4, loc='lower center', bbox_to_anchor=(.5, 1.01), frameon=False)
fig.tight_layout()
fig.savefig(ROOT / 'psycon-recovery-comparison.png', dpi=170)
plt.close(fig)

totals = {method: sum(summaries[item['file'], method]['ready_profiles'] for item in items)
          for method in methods}
visible = sum(item['detected_faces'] for item in items)
recovered = totals['psycon-recovered'] - totals['psycon']
recovered_clips = [clip for item in items
                   for clip in json.loads((ROOT / Path(item['file']).stem /
                                           'playback/manifest.json').read_text())
                   if clip['method'] == 'psycon-recovered']
review_clips = sum(clip['clip_kind'] == 'tentative_review' for clip in recovered_clips)
lines = [
    '# PSYCON recovery across group discussions', '',
    f'The guarded second pass produced {totals["psycon-recovered"]}/{visible} training-ready numbered profiles across {len(items)} recordings, up {recovered} from the initial PSYCON pass. The remaining {visible-totals["psycon-recovered"]} visible person-slots need further video confirmation or usable isolated speech. Three recordings have seven marked faces, so the inventory has 85 visible slots rather than 88.', '',
    '![Ready profiles by recording and method](../instance/group_batch/psycon-recovery-comparison.png)', '',
    '## Threshold decision', '',
    'The cached-model grid tested 36 voice/support pairs, then 36 visual/voice/support second-pass settings. Lowering voice similarity to 0.42 alone reached at most 44 ready profiles and produced up to three conflicts against held-out high-confidence visual turns. A guarded second pass with TalkNet score gates 0.70/0.60, SpeechBrain turn similarity 0.65, and support agreement 0.45 reached 57 ready profiles with zero conflicts in that same weak-label check. It also requires two distinct source turns at least two seconds apart, a 0.05 voice margin against another face, and no contradictory reliable face on a promoted row. These labels come from the detector itself, so zero conflicts is not a human accuracy estimate.', '',
    'The original 4K frames were rescored in sampled windows from all five 4K recordings. Adding those observations did not improve this guarded count, and some top-face scores changed, so the runtime continues to use its synchronized 1920-wide analysis copy. The targeted extra TalkNet windows also did not improve the guarded count. Both probes are saved for later review.', '',
    '## Per-recording result', '',
    '| Recording | Faces | Existing | NVIDIA | Initial PSYCON | Recovered PSYCON | Unready slots | Unknown clean s | Overlap s |',
    '| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |',
]
for item in items:
    name = item['file']
    stem = Path(name).stem
    current = summaries[name, 'psycon-recovered']
    unready = ', '.join(str(profile['slot']) for profile in current['profiles']
                      if profile['status'] != 'ready') or 'none'
    lines.append(f'| {name} | {item["detected_faces"]} | '
                 f'{summaries[name, "existing"]["ready_profiles"]} | '
                 f'{summaries[name, "nvidia"]["ready_profiles"]} | '
                 f'{summaries[name, "psycon"]["ready_profiles"]} | '
                 f'{current["ready_profiles"]} | {unready} | '
                 f'{current["unknown_s"]:.2f} | {current["overlap_s"]:.2f} |')
lines.extend(['',
    '## Evidence and limits', '',
    f'The code generated {len(recovered_clips)} PSYCON playback or review WAVs from the shared PCM; {review_clips} are tentative review clips and the rest have assigned speech. Nine numbered slots have no defensible person-specific WAV. Each [recovered detail](../instance/group_batch/IMG_3962/psycon-recovered-detail.json) records the exact assigned source intervals, visual observations, voice similarity, and profile measurements. Every recording has a corresponding recovered detail and [playback manifest](../instance/group_batch/IMG_3962/playback/manifest.json). A tentative review clip is marked `tentative_review`; it cannot train a profile until a reviewer confirms the numbered face from the original video. Mixed overlap may appear in assigned playback when a nearby clean turn supports the cluster, while overlap stays out of feature extraction.', '',
    'The [full comparison report](group_discussions_full_report.md) contains the marked-frame screenshots, timelines, initial implementation, NVIDIA, and initial PSYCON results. Their original data remain separate for comparison. The [original-video rehearsal](psycon_discussion_rehearsal.md) covers sampled manual checks on one recording. The other ten recordings lack human speaker-by-word labels, so their recovered profiles remain model-supported candidates rather than validated identities.', '',
    'The replay used saved outputs from pinned Community-1, TalkNet, and per-turn SpeechBrain inference on all 11 videos, then ran the current production matching and profile computation on the shared PCM. The full prior GPU batch completed all 33 method runs. `python -m pytest tests -q --basetemp instance/group_batch_pytest_final_recovery -p no:cacheprovider` passed with six skips. [Artifact validation](../instance/group_batch/validation.json) checks source PCM bounds, profiles, and playback WAV durations.', '',
])
DOC.write_text('\n'.join(lines), encoding='utf-8')
print(DOC, totals, 'visible', visible)
