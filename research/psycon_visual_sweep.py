"""Compare TalkNet reliability gates using cached multi-recording evidence."""
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
POLICIES = {
    'baseline': (.80, .30, .70, .35, .60),
    'mild': (.75, .35, .65, .30, .60),
    'moderate': (.70, .40, .60, .25, .65),
    'wide': (.65, .45, .55, .20, .70),
}
VOICE = ((.55, .65), (.55, .60), (.65, .45), (.65, .55))


def observations_for_policy(original, policy):
    absolute, competitor_cap, separated, margin, separated_cap = policy
    observations = copy.deepcopy(original)
    for item in observations:
        score = float(item['score'])
        competitor = float(item['competing_score'])
        reliable = ((score >= absolute and competitor <= competitor_cap) or
                    (score >= separated and score-competitor >= margin and
                     competitor <= separated_cap))
        item['reliable'] = bool(item.get('face_identity_verified') and
                                float(item.get('track_continuity', 0)) >= .8 and
                                (reliable or item.get('visual_repetition')))
    return observations


def reset(original):
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


def evaluate(detail, embeddings, samples, face_count, policy, voice, support):
    observations = observations_for_policy(detail['observations'], policy)
    rows = reset(detail['rows'])
    slots = set(range(1, face_count+1))
    psycon.link_faces(rows, observations, embeddings, slots,
                      threshold=voice, support_threshold=support)
    ready = sum(len(assigned_audio_for_slot(samples, 16000, rows, slot)[0]) >= 48000
                for slot in slots)
    assigned = sum(row['end_s']-row['start_s'] for row in rows if row['status'] == 'assigned')
    return ready, assigned, rows, observations


cases = []
for item in json.loads((ROOT / 'inventory.json').read_text()):
    folder = ROOT / Path(item['file']).stem
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    with np.load(folder / 'psycon-turn-embeddings.npz') as saved:
        embeddings = dict(zip(saved['ids'].tolist(), saved['vectors']))
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    cases.append((item, detail, embeddings, samples))

outcomes = []
for policy_name, policy in POLICIES.items():
    for voice, support in VOICE:
        total = {'visual_policy': policy_name, 'voice_threshold': voice,
                 'support_threshold': support, 'ready_profiles': 0,
                 'assigned_s': 0., 'held_out_correct': 0, 'held_out_wrong': 0,
                 'per_recording': []}
        for item, detail, embeddings, samples in cases:
            ready, assigned, rows, observations = evaluate(
                detail, embeddings, samples, item['detected_faces'], policy, voice, support)
            total['ready_profiles'] += ready
            total['assigned_s'] += assigned
            total['per_recording'].append({'file': item['file'], 'ready': ready,
                                           'assigned_s': round(assigned, 2)})
            # Benchmark propagation on visual observations whose original score
            # was already high. Remove all observations from a held-out turn.
            labels = {}
            for observation in detail['observations']:
                if (observation.get('reliable') and observation.get('face_identity_verified') and
                        observation['score'] >= .85 and
                        observation['score']-observation['competing_score'] >= .3):
                    labels.setdefault(observation['source_segment_id'], set()).add(
                        observation['slot_number'])
            labels = {key: next(iter(slots)) for key, slots in labels.items() if len(slots) == 1}
            for fold in range(3):
                held_ids = {row_id for index, row_id in enumerate(sorted(labels))
                            if index % 3 == fold}
                training = [observation for observation in observations
                            if observation['source_segment_id'] not in held_ids]
                held_rows = reset(detail['rows'])
                psycon.link_faces(held_rows, training, embeddings,
                                  set(range(1, item['detected_faces']+1)),
                                  threshold=voice, support_threshold=support)
                for row in held_rows:
                    if row['id'] in held_ids and row['status'] == 'assigned':
                        if row['slot_number'] == labels[row['id']]:
                            total['held_out_correct'] += 1
                        else:
                            total['held_out_wrong'] += 1
        total['assigned_s'] = round(total['assigned_s'], 2)
        outcomes.append(total)
        print(policy_name, voice, support, total['ready_profiles'],
              total['assigned_s'], total['held_out_correct'],
              total['held_out_wrong'], flush=True)

(ROOT / 'psycon-visual-sweep.json').write_text(json.dumps(outcomes, indent=2))
