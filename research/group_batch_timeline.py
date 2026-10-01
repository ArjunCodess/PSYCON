"""Render assigned, unknown, and overlapping intervals for each method."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path('instance/group_batch')
items = json.loads((ROOT / 'inventory.json').read_text())
palette = plt.get_cmap('tab10')

for item in items:
    folder = ROOT / Path(item['file']).stem
    folder.mkdir(exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(14, 7.5), sharex=True, layout='constrained')
    for axis, method in zip(axes, ('existing', 'nvidia', 'psycon')):
        path = folder / f'{method}-detail.json'
        if path.exists():
            data = json.loads(path.read_text())
            for row in data['rows']:
                start, end = float(row['start_s']), float(row['end_s'])
                if end <= start:
                    continue
                if row.get('overlap_refused_s'):
                    y, color = -.2, '#d95c5c'
                elif row.get('status') == 'assigned' and row.get('slot_number'):
                    slot = int(row['slot_number'])
                    y, color = slot, palette((slot-1) % 10)
                else:
                    y, color = .4, '#a8adb3'
                axis.broken_barh([(start, end-start)], (y-.32, .55), facecolors=color,
                                 edgecolors='none')
            ready = data['summary'].get('ready_profiles', 0)
            axis.set_title(f'{method.upper()} — {ready} ready profiles', loc='left', fontsize=11)
        else:
            summary_path = folder / f'{method}-summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
            label = summary.get('status', 'pending')
            axis.set_title(f'{method.upper()} — {label}', loc='left', fontsize=11)
        axis.set_ylim(-.8, item['detected_faces']+.7)
        axis.set_yticks([0] + list(range(1, item['detected_faces']+1)))
        axis.set_yticklabels(['unknown / overlap'] + [f'P{slot}' for slot in range(1, item['detected_faces']+1)])
        axis.grid(axis='x', alpha=.2)
    axes[-1].set_xlim(0, item['duration_s'])
    axes[-1].set_xlabel('Time in source recording (seconds)')
    fig.suptitle(item['file'], fontsize=13)
    fig.legend(handles=[Patch(color='#a8adb3', label='unknown clean'),
                        Patch(color='#d95c5c', label='overlap excluded')],
               loc='upper right', ncols=2)
    fig.savefig(folder / 'timeline.png', dpi=150)
    plt.close(fig)
    print(item['file'], 'timeline', flush=True)
