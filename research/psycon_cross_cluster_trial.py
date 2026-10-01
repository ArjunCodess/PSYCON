"""Test cross-cluster voice rescue against held-out active-speaker turns."""
from __future__ import annotations

import copy
import json
import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group import psycon
from backend.group.voice import assigned_audio_for_slot


ROOT = Path('instance/group_batch')
SUPPORT = (.50, .55, .60, .65)
PROPAGATE = (.55, .60, .65, .70)


def fresh(original):
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


def norm(vector):
    vector = np.asarray(vector, dtype=float)
    length = np.linalg.norm(vector)
    return vector/length if length > 0 else vector


def rescue(rows, observations, embeddings, slots, support, propagate):
    by_row = {row['id']: row for row in rows}
    per_slot = defaultdict(list)
    per_row = defaultdict(set)
    for item in observations:
        if (item.get('reliable') and item.get('face_identity_verified') and
                item.get('source_segment_id') in embeddings and
                item.get('slot_number') in slots):
            per_row[item['source_segment_id']].add(item['slot_number'])
            per_slot[item['slot_number']].append(item)
    centers = {}
    support_ids = {}
    for slot, items in per_slot.items():
        clean = [item for item in items if len(per_row[item['source_segment_id']]) == 1]
        agreed = psycon._consistent_support(clean, embeddings, support)
        if agreed is None:
            continue
        chosen, center, _cohesion = agreed
        ids = [item['source_segment_id'] for item in chosen]
        source_turns = {by_row[row_id].get('source_turn_index') for row_id in ids}
        if len(source_turns) < 2 or sum(by_row[row_id]['end_s']-by_row[row_id]['start_s']
                                        for row_id in ids) < 2.:
            continue
        centers[slot] = center
        support_ids[slot] = ids
    for row in rows:
        if row['status'] == 'assigned' or row.get('overlap_refused_s') or row['id'] not in embeddings:
            continue
        vector = norm(embeddings[row['id']])
        ranked = sorted(((float(vector @ center), slot) for slot, center in centers.items()),
                        reverse=True)
        if not ranked:
            continue
        own, slot = ranked[0]
        competing = ranked[1][0] if len(ranked) > 1 else -1.
        direct = slot in per_row[row['id']]
        if (per_row[row['id']] and not direct) or own < propagate + (0. if direct else .08):
            continue
        if own-competing < .08:
            continue
        row['status'] = 'assigned'
        row['slot_number'] = slot
        row['confidence'] = own
        row['evidence'].update(reason='cross_cluster_voice_trial',
                               source_segments=support_ids[slot], voice_similarity=own,
                               voice_margin=own-competing)
    return rows


cases = []
for item in json.loads((ROOT / 'inventory.json').read_text()):
    folder = ROOT / Path(item['file']).stem
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    with np.load(folder / 'psycon-turn-embeddings.npz') as saved:
        embeddings = dict(zip(saved['ids'].tolist(), saved['vectors']))
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    labels = defaultdict(set)
    for observation in detail['observations']:
        if (observation.get('reliable') and observation.get('face_identity_verified') and
                observation['score'] >= .85 and
                observation['score']-observation['competing_score'] >= .3):
            labels[observation['source_segment_id']].add(observation['slot_number'])
    labels = {row_id: next(iter(s)) for row_id, s in labels.items() if len(s) == 1}
    cases.append((item, detail, embeddings, samples, labels))

results = []
for support in SUPPORT:
    for propagate in PROPAGATE:
        total = {'support_threshold': support, 'propagate_threshold': propagate,
                 'ready_profiles': 0, 'assigned_s': 0., 'held_out_correct': 0,
                 'held_out_wrong': 0, 'per_recording': []}
        for item, detail, embeddings, samples, labels in cases:
            slots = set(range(1, item['detected_faces']+1))
            rows = fresh(detail['rows'])
            psycon.link_faces(rows, detail['observations'], embeddings, slots)
            rescue(rows, detail['observations'], embeddings, slots, support, propagate)
            ready = sum(len(assigned_audio_for_slot(samples, 16000, rows, slot)[0]) >= 48000
                        for slot in slots)
            assigned = sum(row['end_s']-row['start_s'] for row in rows if row['status'] == 'assigned')
            total['ready_profiles'] += ready
            total['assigned_s'] += assigned
            total['per_recording'].append({'file': item['file'], 'ready': ready,
                                           'assigned_s': round(assigned, 2)})
            for fold in range(3):
                held = {row_id for index, row_id in enumerate(sorted(labels)) if index % 3 == fold}
                observations = [item for item in detail['observations']
                                if item['source_segment_id'] not in held]
                held_rows = fresh(detail['rows'])
                psycon.link_faces(held_rows, observations, embeddings, slots)
                rescue(held_rows, observations, embeddings, slots, support, propagate)
                for row in held_rows:
                    if row['id'] in held and row['status'] == 'assigned':
                        if row['slot_number'] == labels[row['id']]:
                            total['held_out_correct'] += 1
                        else:
                            total['held_out_wrong'] += 1
        total['assigned_s'] = round(total['assigned_s'], 2)
        results.append(total)
        print(support, propagate, total['ready_profiles'], total['assigned_s'],
              total['held_out_correct'], total['held_out_wrong'], flush=True)

(ROOT / 'psycon-cross-cluster-trial.json').write_text(json.dumps(results, indent=2))
