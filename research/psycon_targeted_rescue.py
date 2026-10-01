"""Rescore unknown clean turns for faces missed by the first TalkNet pass."""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from backend.group import psycon


ROOT = Path('instance/group_batch')


def overlap(left, right):
    return max(0., min(left['end_s'], right['end_s']) -
               max(left['start_s'], right['start_s']))


def windows_for(detail, existing, nvidia, missing):
    seen = {observation['source_segment_id'] for observation in detail['observations']}
    candidates = [row for row in detail['rows']
                  if row['cluster_label'] is not None and not row.get('overlap_refused_s')
                  and row['end_s']-row['start_s'] >= .55]
    chosen = {}
    for slot in missing:
        voted = []
        for row in candidates:
            votes = [overlap(row, other) for source in (existing, nvidia)
                     for other in source['rows'] if other['status'] == 'assigned'
                     and other['slot_number'] == slot]
            best = max(votes, default=0.)
            if best >= .4:
                voted.append((best, row))
        for _, row in sorted(voted, key=lambda pair: pair[0], reverse=True)[:10]:
            chosen[row['id']] = row
    remaining = [row for row in sorted(candidates, key=lambda row: row['start_s'])
                 if row['status'] == 'unknown' and row['id'] not in chosen and row['id'] not in seen]
    if remaining:
        for index in np.linspace(0, len(remaining)-1, min(32, len(remaining)), dtype=int):
            row = remaining[int(index)]
            chosen[row['id']] = row
    selected = []
    for row in sorted(chosen.values(), key=lambda row: row['start_s'])[:80]:
        start, end = float(row['start_s']), float(row['end_s'])
        selected.append((row['cluster_label'], start, min(start+2., end), row['id']))
        if end-start >= 4.:
            selected.append((row['cluster_label'], end-2., end, row['id']))
    return selected[:100]


for item in json.loads((ROOT / 'inventory.json').read_text()):
    folder = ROOT / Path(item['file']).stem
    output = folder / 'psycon-rescue-observations-v2.json'
    if output.exists():
        print(item['file'], 'cached', flush=True)
        continue
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    missing = {profile['slot_number'] for profile in detail['profiles']
               if profile['status'] != 'ready'}
    if not missing:
        output.write_text(json.dumps({'missing_slots': [], 'windows': [], 'observations': []}))
        print(item['file'], 'all ready', flush=True)
        continue
    existing = json.loads((folder / 'existing-detail.json').read_text())
    nvidia = json.loads((folder / 'nvidia-detail.json').read_text())
    selected = windows_for(detail, existing, nvidia, missing)
    if not selected:
        output.write_text(json.dumps({'missing_slots': sorted(missing), 'windows': [],
                                      'observations': []}))
        print(item['file'], 'no unknown clean windows', flush=True)
        continue
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    visual = (folder / 'analysis-1920w-25fps.mp4' if
              item['width'] > 1920 or item['height'] > 1080 else
              Path('group_discussions') / item['file'])
    boxes = [{**face, 'rotation_degrees': item['rotation_degrees'],
              'frame_time_s': item['marked_frame_s']} for face in item['faces']]
    observations = psycon.active_observations(detail['rows'], boxes, visual, samples,
                                              windows=selected)
    output.write_text(json.dumps({'missing_slots': sorted(missing),
                                  'windows': selected, 'observations': observations}, indent=2))
    print(item['file'], len(selected), 'windows', len(observations), 'observations',
          sum(bool(observation.get('reliable')) for observation in observations),
          'reliable', flush=True)
