"""Sweep voice evidence gates on all recordings with held-out visual turns."""
from __future__ import annotations

import copy
import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group import psycon
from backend.group.voice import assigned_audio_for_slot


ROOT = Path('instance/group_batch')
VOICE = (.35, .42, .48, .55, .60, .65)
SUPPORT = (.45, .50, .55, .60, .65, .70)


def fresh_rows(original):
    rows = copy.deepcopy(original)
    for row in rows:
        overlap = bool(row.get('overlap_refused_s'))
        row['status'] = 'unknown'
        row['slot_number'] = None
        row['confidence'] = 0.
        row['evidence'] = {'version': psycon.MATCHING_VERSION,
                           'reason': 'overlapping_speakers' if overlap else 'speaker_unmapped',
                           'clusters': row.get('evidence', {}).get('clusters',
                                       [row['cluster_label']] if row['cluster_label'] else [])}
    return rows


def link(original, observations, embeddings, slots, voice, support):
    rows = fresh_rows(original)
    psycon.link_faces(rows, observations, embeddings, slots,
                      threshold=voice, support_threshold=support)
    return rows


def reliable_labels(observations):
    by_row = {}
    for item in observations:
        if (not item.get('reliable') or not item.get('face_identity_verified') or
                item['score'] < .85 or item['score']-item['competing_score'] < .3):
            continue
        by_row.setdefault(item['source_segment_id'], set()).add(item['slot_number'])
    return {row_id: next(iter(slots)) for row_id, slots in by_row.items() if len(slots) == 1}


inventory = json.loads((ROOT / 'inventory.json').read_text())
cases = []
for item in inventory:
    folder = ROOT / Path(item['file']).stem
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    with np.load(folder / 'psycon-turn-embeddings.npz') as cache:
        embeddings = dict(zip(cache['ids'].tolist(), cache['vectors']))
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    labels = reliable_labels(detail['observations'])
    cases.append((item, detail, embeddings, samples, labels))

outcomes = []
for voice in VOICE:
    for support in SUPPORT:
        aggregate = {'voice_threshold': voice, 'support_threshold': support,
                     'ready_profiles': 0, 'assigned_s': 0., 'held_out_assigned': 0,
                     'held_out_correct': 0, 'held_out_wrong': 0,
                     'per_recording': []}
        for item, detail, embeddings, samples, labels in cases:
            observations = detail['observations']
            slots = set(range(1, item['detected_faces']+1))
            full = link(detail['rows'], observations, embeddings, slots, voice, support)
            usable = {slot: len(assigned_audio_for_slot(samples, 16000, full, slot)[0])/16000
                      for slot in slots}
            ready = sum(seconds >= 3 for seconds in usable.values())
            assigned = sum(row['end_s']-row['start_s'] for row in full
                           if row['status'] == 'assigned')
            aggregate['ready_profiles'] += ready
            aggregate['assigned_s'] += assigned
            aggregate['per_recording'].append({'file': item['file'], 'ready': ready,
                                               'usable_s_by_slot': {str(k): round(v, 2)
                                                                    for k, v in usable.items()},
                                               'assigned_s': round(assigned, 2)})
            ordered = sorted(labels, key=lambda row_id: next(
                row['start_s'] for row in detail['rows'] if row['id'] == row_id))
            for fold in range(3):
                held_ids = {row_id for index, row_id in enumerate(ordered) if index % 3 == fold}
                training = [obs for obs in observations
                            if obs['source_segment_id'] not in held_ids]
                held = link(detail['rows'], training, embeddings, slots, voice, support)
                for row in held:
                    if row['id'] not in held_ids or row['status'] != 'assigned':
                        continue
                    aggregate['held_out_assigned'] += 1
                    if row['slot_number'] == labels[row['id']]:
                        aggregate['held_out_correct'] += 1
                    else:
                        aggregate['held_out_wrong'] += 1
        aggregate['assigned_s'] = round(aggregate['assigned_s'], 2)
        outcomes.append(aggregate)
        print(voice, support, aggregate['ready_profiles'], aggregate['assigned_s'],
              aggregate['held_out_correct'], aggregate['held_out_wrong'], flush=True)

(ROOT / 'psycon-threshold-sweep.json').write_text(json.dumps(outcomes, indent=2))
baseline = next(item for item in outcomes if item['voice_threshold'] == .55
                and item['support_threshold'] == .65)
expected = sum(json.loads((ROOT / Path(item['file']).stem / 'psycon-summary.json').read_text())['ready_profiles']
               for item in inventory)
if baseline['ready_profiles'] != expected:
    raise RuntimeError(f'baseline_replay_mismatch:{baseline["ready_profiles"]}!={expected}')
print('baseline reproduced', expected, 'ready profiles')
