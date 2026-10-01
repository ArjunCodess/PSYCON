"""Cache per-turn SpeechBrain vectors for reproducible local threshold sweeps."""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from ml.src.speaker_analysis import SpeechBrainEmbedder


ROOT = Path('instance/group_batch')
embedder = SpeechBrainEmbedder(device='cuda')

for item in json.loads((ROOT / 'inventory.json').read_text()):
    folder = ROOT / Path(item['file']).stem
    detail = json.loads((folder / 'psycon-detail.json').read_text())
    cache = folder / 'psycon-turn-embeddings.npz'
    eligible = [row for row in detail['rows'] if row.get('cluster_label') is not None
                and row['end_s'] - row['start_s'] >= 1]
    if cache.exists():
        with np.load(cache) as saved:
            if set(saved['ids'].tolist()) == {row['id'] for row in eligible}:
                print(item['file'], len(eligible), 'cached', flush=True)
                continue
    with wave.open(str(folder / 'shared-16khz.wav'), 'rb') as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, 16000)
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    ids = []
    vectors = []
    for row in eligible:
        clip = samples[round(row['start_s']*16000):round(row['end_s']*16000)]
        if len(clip) < 16000:
            continue
        ids.append(row['id'])
        vectors.append(embedder.embed(clip, 16000))
    pending = folder / 'psycon-turn-embeddings.building'
    with pending.open('wb') as handle:
        np.savez_compressed(handle, ids=np.asarray(ids, dtype='U36'),
                            vectors=np.asarray(vectors, dtype=np.float32),
                            pcm_frames=np.asarray([len(samples)], dtype=np.int64))
    pending.replace(cache)
    print(item['file'], len(ids), 'embedded', flush=True)
