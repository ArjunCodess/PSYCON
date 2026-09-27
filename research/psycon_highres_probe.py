"""Compare shortlisted TalkNet windows at the original 4K resolution."""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from backend.group import psycon


ROOT = Path('instance/group_batch')
for item in json.loads((ROOT / 'inventory.json').read_text()):
    if item['width'] <= 1920:
        continue
    folder = ROOT / Path(item['file']).stem
    output = folder / 'psycon-highres-observations.json'
    if output.exists():
        print(item['file'], 'cached', flush=True)
        continue
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    rescue = json.loads((folder / 'psycon-rescue-observations-v2.json').read_text())
    missing = {profile['slot_number'] for profile in detail['profiles']
               if profile['status'] != 'ready'}
    scored = []
    for observation in rescue['observations']:
        score = max((face['score'] for face in observation.get('face_scores', [])
                     if face['slot_number'] in missing and face['face_identity_verified']),
                    default=0.)
        scored.append((score, observation))
    selected = []
    ids = set()
    for _score, observation in sorted(scored, key=lambda pair: pair[0], reverse=True):
        row_id = observation['source_segment_id']
        if row_id in ids:
            continue
        ids.add(row_id)
        selected.append((observation['cluster_label'], observation['start_s'],
                         observation['end_s'], row_id))
        if len(selected) >= 12:
            break
    if not selected:
        output.write_text(json.dumps({'windows': [], 'observations': []}))
        continue
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    boxes = [{**face, 'rotation_degrees': item['rotation_degrees'],
              'frame_time_s': item['marked_frame_s']} for face in item['faces']]
    observations = psycon.active_observations(detail['rows'], boxes,
                                              Path('group_discussions') / item['file'],
                                              samples, windows=selected)
    output.write_text(json.dumps({'windows': selected, 'observations': observations}, indent=2))
    print(item['file'], len(selected), 'high-res windows', len(observations),
          'observations', flush=True)
