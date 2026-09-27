"""Replay current PSYCON matching and measurements from pinned model outputs.

Community-1, TalkNet, and per-turn SpeechBrain inference were run in the full
batch. This script reruns matching and profile computation without repeating
those expensive upstream calls. It writes separate artifacts for comparison.
"""
from __future__ import annotations

import copy
import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group import psycon
from backend.group.voice import _tentative_measures
from ml.src.speaker_analysis import SpeakerTurn
from ml.src.speaker_analysis import SpeechBrainEmbedder


ROOT = Path('instance/group_batch')
items = json.loads((ROOT / 'inventory.json').read_text())
review_only = '--review-only' in sys.argv


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=lambda item:
                         item.tolist() if isinstance(item, np.ndarray) else str(item)))


embedder = None if review_only else SpeechBrainEmbedder(device='cuda')
for item in items:
    folder = ROOT / Path(item['file']).stem
    original = json.loads((folder / 'psycon-detail.json').read_text())
    if review_only:
        recovered_path = folder / 'psycon-recovered-detail.json'
        if not recovered_path.exists():
            raise FileNotFoundError(recovered_path)
        recovered = json.loads(recovered_path.read_text())
        with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
            samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').copy()
        count = psycon.mark_review_candidates(recovered['rows'], original['observations'],
                                              set(range(1, item['detected_faces']+1)))
        for profile in recovered['profiles']:
            if profile['status'] != 'ready':
                tentative = _tentative_measures(samples, 16000, recovered['rows'],
                                                profile['slot_number'], [])
                if tentative is not None:
                    profile['metrics']['tentative'] = tentative
        recovered['summary']['review_candidates'] = count
        save(recovered_path, recovered)
        save(folder / 'psycon-recovered-summary.json', recovered['summary'])
        print(item['file'], count, 'review candidates', flush=True)
        continue
    rows = copy.deepcopy(original['rows'])
    for row in rows:
        row.update(status='unknown', slot_number=None, confidence=0.)
        row['evidence'] = {'version': psycon.MATCHING_VERSION,
                           'reason': 'overlapping_speakers' if row.get('overlap_refused_s')
                           else 'speaker_unmapped',
                           'clusters': row.get('evidence', {}).get('clusters', [])}
    observations = copy.deepcopy(original['observations'])
    with np.load(folder / 'psycon-turn-embeddings.npz') as saved:
        embeddings = dict(zip(saved['ids'].tolist(), saved['vectors']))
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').copy()
    slots = set(range(1, item['detected_faces']+1))
    mapping = psycon.link_faces(rows, observations, embeddings, slots)
    recovered = psycon.recover_supported_faces(rows, observations, embeddings, slots)
    review_candidates = psycon.mark_review_candidates(rows, observations, slots)
    psycon.mark_playback_overlap(rows)
    turns = [SpeakerTurn(float(turn['start_s']), float(turn['end_s']),
                         str(turn['speaker_id']))
             for turn in json.loads((folder / 'psycon-exclusive-turns.json').read_text())]
    profiles = psycon.make_profiles(samples, rows, item['faces'], turns, embedder=embedder)
    summary = {'status': 'complete', 'method': 'psycon-recovered', 'file': item['file'],
               'matching_version': psycon.MATCHING_VERSION,
               'replay_source': 'pinned community1 talknet speechbrain model outputs',
               'recovered_turns': recovered, 'review_candidates': review_candidates,
               'mapping': mapping,
               'visible_faces': item['detected_faces'],
               'ready_profiles': sum(p['status'] == 'ready' for p in profiles),
               'assigned_s': round(sum(row['end_s']-row['start_s'] for row in rows
                                       if row['status'] == 'assigned'), 2),
               'unknown_s': round(sum(row['end_s']-row['start_s'] for row in rows
                                      if row['status'] == 'unknown' and
                                      not row.get('overlap_refused_s')), 2),
               'overlap_s': round(sum(row.get('overlap_refused_s', 0) for row in rows), 2),
               'profiles': [{'slot': p['slot_number'], 'status': p['status'],
                             'usable_s': round(p['usable_seconds'], 2),
                             'transcription': (p.get('metrics', {}).get('transcription') or
                                               {}).get('status')} for p in profiles]}
    save(folder / 'psycon-recovered-detail.json', {'summary': summary, 'rows': rows,
                                                   'observations': observations,
                                                   'profiles': profiles})
    save(folder / 'psycon-recovered-summary.json', summary)
    print(item['file'], summary['ready_profiles'], 'ready',
          summary['recovered_turns'], 'recovered rows', flush=True)
