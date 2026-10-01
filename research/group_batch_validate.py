"""Check the saved comparison and playback artifacts against source PCM."""
from __future__ import annotations

import json
import csv
import hashlib
import math
import wave
from pathlib import Path

import numpy as np


ROOT = Path('instance/group_batch')
METHODS = ('existing', 'nvidia', 'psycon', 'psycon-recovered',
           'nemotron-offline', 'nemotron-streaming-guarded')
inventory = json.loads((ROOT / 'inventory.json').read_text())
errors = []
complete = 0
failed = []
clips = 0
expected_profile_rows = 0


def check(condition, message):
    if not condition:
        errors.append(message)


for item in inventory:
    stem = Path(item['file']).stem
    folder = ROOT / stem
    check(item['status'] == 'complete', f'{stem}: inventory {item["status"]}')
    check((ROOT / f'{stem}-marked.jpg').exists(), f'{stem}: marked image missing')
    check((folder / 'timeline.png').exists(), f'{stem}: timeline missing')
    pcm = folder / 'shared-16khz.wav'
    if not pcm.exists():
        errors.append(f'{stem}: shared PCM missing')
        continue
    with wave.open(str(pcm), 'rb') as source:
        check((source.getnchannels(), source.getsampwidth(), source.getframerate()) ==
              (1, 2, 16000), f'{stem}: PCM format')
        duration = source.getnframes() / source.getframerate()
    for method in METHODS:
        path = folder / f'{method}-summary.json'
        if not path.exists():
            errors.append(f'{stem}/{method}: summary missing')
            continue
        summary = json.loads(path.read_text())
        if summary['status'] != 'complete':
            failed.append({'recording': item['file'], 'method': method,
                           'reason': summary.get('reason')})
            continue
        complete += 1
        detail_path = folder / f'{method}-detail.json'
        if not detail_path.exists():
            errors.append(f'{stem}/{method}: detail missing')
            continue
        detail = json.loads(detail_path.read_text())
        expected_profile_rows += item['detected_faces']
        if method.startswith('nemotron-'):
            check(summary.get('pcm_sha256') == hashlib.sha256(pcm.read_bytes()).hexdigest(),
                  f'{stem}/{method}: shared PCM changed since inference')
        if method == 'nemotron-offline':
            probability_path = folder / 'nemotron-offline-probabilities.npz'
            check(probability_path.exists(), f'{stem}/{method}: raw probabilities missing')
            if probability_path.exists():
                with np.load(probability_path) as saved:
                    probabilities = saved['probabilities']
                check(probabilities.ndim == 2 and probabilities.shape[1] == 8,
                      f'{stem}/{method}: raw channel shape')
                check(np.isfinite(probabilities).all() and
                      np.all((probabilities >= 0) & (probabilities <= 1)),
                      f'{stem}/{method}: invalid activity probabilities')
                check(abs(len(probabilities)*.01-duration) <= .021,
                      f'{stem}/{method}: raw activity clock differs from PCM')
        check(len(detail['profiles']) == item['detected_faces'],
              f'{stem}/{method}: profile count differs from marked faces')
        check(sum(profile['status'] == 'ready' for profile in detail['profiles']) ==
              summary['ready_profiles'], f'{stem}/{method}: ready count mismatch')
        for profile in detail['profiles']:
            check(1 <= profile['slot_number'] <= item['detected_faces'],
                  f'{stem}/{method}: slot out of range')
            if profile['status'] == 'ready':
                check(profile['usable_seconds'] >= 3,
                      f'{stem}/{method}: ready profile under speech gate')
            if method.startswith('nemotron-'):
                metrics = profile.get('metrics') or {}
                check(metrics.get('benchmark_only') is True,
                      f'{stem}/{method}: benchmark profile missing source guard')
                check(metrics.get('feature_schema') == 'nemotron-benchmark-face-voice-1',
                      f'{stem}/{method}: benchmark schema mixed with PSYCON')
                if profile['status'] == 'ready':
                    embedding = profile.get('embedding') or []
                    check(len(embedding) == 192 and all(math.isfinite(value) for value in embedding)
                          and sum(value*value for value in embedding) > 0,
                          f'{stem}/{method}: ready profile missing valid voice shape')
        for row in detail['rows']:
            check(0 <= row['start_s'] < row['end_s'] <= duration + .2,
                  f'{stem}/{method}: row outside PCM')
            slot = row.get('slot_number')
            if slot is not None:
                check(1 <= slot <= item['detected_faces'],
                      f'{stem}/{method}: row slot out of range')
            if method in ('psycon', 'psycon-recovered', 'nemotron-offline', 'nemotron-streaming-guarded') and row.get('overlap_refused_s'):
                check(row['status'] != 'assigned',
                      f'{stem}/{method}: overlap admitted to clean rows')
    manifest_path = folder / 'playback/manifest.json'
    if not manifest_path.exists():
        errors.append(f'{stem}: playback manifest missing')
        continue
    for entry in json.loads(manifest_path.read_text()):
        path = Path(entry['path'])
        if not path.exists():
            errors.append(f'{stem}: clip missing {path}')
            continue
        with wave.open(str(path), 'rb') as source:
            clip_duration = source.getnframes() / source.getframerate()
        clips += 1
        check(abs(clip_duration - entry['clip_s']) < .02,
              f'{stem}: clip duration differs from manifest {path}')
        interval_duration = sum(end - start for start, end in entry['source_intervals'])
        check(abs(clip_duration - interval_duration) < .03,
              f'{stem}: clip duration differs from source intervals {path}')
        for start, end in entry['source_intervals']:
            check(0 <= start < end <= duration + .2,
                  f'{stem}: playback interval outside PCM {path}')

check((ROOT / 'marked-contact-sheet.jpg').exists(), 'contact sheet missing')
check((ROOT / 'method-comparison.png').exists(), 'comparison chart missing')
for filename in ('comparison.csv', 'profiles.csv', 'segments.csv'):
    check((ROOT / filename).exists(), f'{filename} missing')
comparison_path = ROOT / 'comparison.csv'
if comparison_path.exists():
    with comparison_path.open(newline='') as source:
        comparison = list(csv.DictReader(source))
    expected_pairs = {(item['file'], method) for item in inventory for method in METHODS}
    check(len(comparison) == len(expected_pairs) and
          {(row['recording'], row['method']) for row in comparison} == expected_pairs,
          'comparison.csv must retain every recording and method')
profiles_path = ROOT / 'profiles.csv'
if profiles_path.exists():
    with profiles_path.open(newline='') as source:
        profile_rows = list(csv.DictReader(source))
    check(len(profile_rows) == expected_profile_rows,
          'profiles.csv count differs from completed method outputs')
result = {'recordings': len(inventory), 'expected_method_runs': len(inventory)*len(METHODS),
          'complete_method_runs': complete, 'failed_method_runs': failed,
          'generated_clips': clips, 'errors': errors}
(ROOT / 'validation.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
raise SystemExit(1 if errors or failed else 0)
