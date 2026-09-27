"""Export source-PCM review clips using each production method's playback rule."""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group import psycon
from backend.group.voice import assigned_audio_for_slot, review_audio_for_slot, REVIEW_CLIP_SECONDS

ROOT = Path('instance/group_batch')
items = json.loads((ROOT / 'inventory.json').read_text())


def wav(path, audio):
    with wave.open(str(path), 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(np.asarray(audio, dtype='<i2').tobytes())


def limited_intervals(intervals, seconds):
    kept = []
    remaining = seconds
    for start, end in intervals:
        if remaining <= 0:
            break
        kept_end = min(end, start + remaining)
        kept.append((start, kept_end))
        remaining -= kept_end - start
    return kept


for item in items:
    folder = ROOT / Path(item['file']).stem
    pcm = folder / 'shared-16khz.wav'
    if not pcm.exists():
        continue
    with wave.open(str(pcm), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').copy()
    output = folder / 'playback'
    output.mkdir(exist_ok=True)
    manifest = []
    for method in ('existing', 'nvidia', 'psycon', 'psycon-recovered'):
        detail_path = folder / f'{method}-detail.json'
        if not detail_path.exists():
            continue
        detail = json.loads(detail_path.read_text())
        if detail['summary']['status'] != 'complete':
            continue
        for previous in output.glob(f'{method}-p*.wav'):
            previous.unlink()
        rows = detail['rows']
        for profile in detail['profiles']:
            slot = int(profile['slot_number'])
            review_only = False
            if method in ('psycon', 'psycon-recovered'):
                audio, intervals, mixed = psycon.playback_audio_for_slot(samples, rows, slot)
                if not len(audio):
                    audio = review_audio_for_slot(samples, 16000, rows, slot)
                    review_only = bool(len(audio))
                    intervals = [(row['start_s'], row['end_s']) for row in rows
                                 if row['status'] == 'unknown' and
                                 (row.get('evidence') or {}).get('review_slot') == slot]
            else:
                audio, intervals = assigned_audio_for_slot(samples, 16000, rows, slot)
                mixed = 0.
                if method == 'existing':
                    if profile['status'] == 'ready':
                        audio = audio[:round(REVIEW_CLIP_SECONDS * 16000)]
                        intervals = limited_intervals(intervals, len(audio) / 16000)
                    else:
                        audio = review_audio_for_slot(samples, 16000, rows, slot)
                        review_only = bool(len(audio))
                        intervals = [(row['start_s'], row['end_s']) for row in rows
                                     if row['status'] == 'unknown' and
                                     (row.get('evidence') or {}).get('review_slot') == slot]
            if not len(audio):
                continue
            intervals = [(start, end) for start, end in intervals if end - start > 1e-6]
            path = output / f'{method}-p{slot:02d}.wav'
            wav(path, audio)
            manifest.append({'method': method, 'slot': slot, 'path': str(path),
                             'clip_kind': 'tentative_review' if review_only else 'assigned_playback',
                             'profile_status': profile['status'],
                             'profile_usable_s': profile['usable_seconds'],
                             'clip_s': round(len(audio)/16000, 2),
                             'mixed_overlap_s': round(mixed, 2),
                             'source_intervals': intervals,
                             'existing_ready_preview_limit_s': (REVIEW_CLIP_SECONDS if
                                                                 method == 'existing' and
                                                                 profile['status'] == 'ready' else None)})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(item['file'], len(manifest), 'review clips', flush=True)
