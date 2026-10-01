"""Test a second evidence pass that preserves baseline PSYCON assignments."""
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
WITH_RESCUE = '--rescue' in sys.argv
WITH_HIGHRES = '--highres' in sys.argv
POLICIES = {
    'baseline': (.80, .30, .70, .35, .60),
    'mild': (.75, .35, .65, .30, .60),
    'moderate': (.70, .40, .60, .25, .65),
}
ALT_VOICE = (.60, .65, .70)
ALT_SUPPORT = (.45, .50, .55, .60)


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


def policy_observations(original, policy):
    absolute, competitor_cap, separated, margin, separated_cap = policy
    observations = copy.deepcopy(original)
    for observation in observations:
        score = float(observation['score'])
        competitor = float(observation['competing_score'])
        pass_score = ((score >= absolute and competitor <= competitor_cap) or
                      (score >= separated and score-competitor >= margin and
                       competitor <= separated_cap))
        observation['reliable'] = bool(observation.get('face_identity_verified') and
                                       float(observation.get('track_continuity', 0)) >= .8 and
                                       (pass_score or observation.get('visual_repetition')))
    return observations


def link(original, observations, embeddings, slots, voice, support):
    rows = reset(original)
    psycon.link_faces(rows, observations, embeddings, slots,
                      threshold=voice, support_threshold=support)
    return rows


def combine(base, alternate, missing_slots, observations):
    by_row = {}
    source_rows = {row['id']: row for row in base}
    for observation in observations:
        if observation.get('reliable'):
            by_row.setdefault(observation['source_segment_id'], set()).add(
                observation['slot_number'])
    for original, candidate in zip(base, alternate):
        slot = candidate.get('slot_number')
        evidence = candidate.get('evidence') or {}
        supports = [source_rows[row_id] for row_id in evidence.get('source_segments', [])
                    if row_id in source_rows]
        independent = (len({row.get('source_turn_index') for row in supports}) >= 2 and
                       max((row['start_s'] for row in supports), default=0) -
                       min((row['start_s'] for row in supports), default=0) >= 2.)
        if (original['status'] != 'unknown' or candidate['status'] != 'assigned' or
                slot not in missing_slots or original.get('overlap_refused_s') or
                evidence.get('training_eligible', True) is False or
                evidence.get('reason') != 'active_speaker_and_voice_consistent' or
                len(evidence.get('source_segments', [])) < 2 or not independent or
                float(evidence.get('voice_similarity') or 0) < .60 or
                (evidence.get('voice_margin') is not None and
                 float(evidence['voice_margin']) < .05) or
                any(other != slot for other in by_row.get(original['id'], ()) )):
            continue
        original['status'] = 'assigned'
        original['slot_number'] = slot
        original['confidence'] = candidate['confidence']
        original['evidence'] = {**evidence, 'reason': 'second_pass_visual_voice_consistent'}
    return base


cases = []
for item in json.loads((ROOT / 'inventory.json').read_text()):
    folder = ROOT / Path(item['file']).stem
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    detail['rescue_observations'] = (json.loads((folder / 'psycon-rescue-observations-v2.json').read_text())
                                     ['observations'] if WITH_RESCUE else [])
    highres_path = folder / 'psycon-highres-observations.json'
    if WITH_HIGHRES and highres_path.exists():
        detail['rescue_observations'] += json.loads(highres_path.read_text())['observations']
    with np.load(folder / 'psycon-turn-embeddings.npz') as saved:
        embeddings = dict(zip(saved['ids'].tolist(), saved['vectors']))
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    labels = {}
    for observation in detail['observations']:
        if (observation.get('reliable') and observation.get('face_identity_verified') and
                observation['score'] >= .85 and
                observation['score']-observation['competing_score'] >= .3):
            labels.setdefault(observation['source_segment_id'], set()).add(observation['slot_number'])
    labels = {key: next(iter(slots)) for key, slots in labels.items() if len(slots) == 1}
    cases.append((item, detail, embeddings, samples, labels))

outcomes = []
for policy_name, policy in POLICIES.items():
    for voice in ALT_VOICE:
        for support in ALT_SUPPORT:
            total = {'policy': policy_name, 'voice_threshold': voice,
                     'support_threshold': support, 'ready_profiles': 0,
                     'assigned_s': 0., 'held_out_correct': 0,
                     'held_out_wrong': 0, 'per_recording': []}
            for item, detail, embeddings, samples, labels in cases:
                slots = set(range(1, item['detected_faces']+1))
                base = link(detail['rows'], detail['observations'], embeddings, slots, .55, .65)
                missing = {profile['slot_number'] for profile in detail['profiles']
                           if profile['status'] != 'ready'}
                alternate_observations = policy_observations(
                    detail['observations'] + detail['rescue_observations'], policy)
                alternate = link(detail['rows'], alternate_observations, embeddings,
                                 slots, voice, support)
                combined = combine(base, alternate, missing, alternate_observations)
                ready = sum(len(assigned_audio_for_slot(samples, 16000, combined, slot)[0]) >= 48000
                            for slot in slots)
                assigned = sum(row['end_s']-row['start_s'] for row in combined
                               if row['status'] == 'assigned')
                total['ready_profiles'] += ready
                total['assigned_s'] += assigned
                total['per_recording'].append({'file': item['file'], 'ready': ready,
                                               'assigned_s': round(assigned, 2)})
                for fold in range(3):
                    held_ids = {row_id for index, row_id in enumerate(sorted(labels))
                                if index % 3 == fold}
                    base_obs = [obs for obs in detail['observations']
                                if obs['source_segment_id'] not in held_ids]
                    alt_obs = [obs for obs in alternate_observations
                               if obs['source_segment_id'] not in held_ids]
                    held_base = link(detail['rows'], base_obs, embeddings, slots, .55, .65)
                    held_alt = link(detail['rows'], alt_obs, embeddings, slots, voice, support)
                    held_combined = combine(held_base, held_alt, missing, alt_obs)
                    for row in held_combined:
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

(ROOT / ('psycon-recovery-highres-trial.json' if WITH_HIGHRES else
         'psycon-recovery-v2-trial.json' if WITH_RESCUE else
         'psycon-recovery-trial.json')).write_text(json.dumps(outcomes, indent=2))
