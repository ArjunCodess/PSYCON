"""Checkpointed local comparison of the three production group analysis paths."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, '/app')
from backend.group import diarization, nvidia, psycon
from backend.group.extract import _energy_segments, _transcribe
from backend.group.voice import assign_windows, build_profiles
from ml.src.speaker_analysis import SpeechBrainEmbedder

ROOT = Path('/app')
OUT = ROOT / 'instance/group_batch'
INVENTORY = json.loads((OUT / 'inventory.json').read_text())
NAME = os.environ['GROUP_BATCH_FILE']
METHOD = os.environ['GROUP_BATCH_METHOD']
INFO = next(item for item in INVENTORY if item['file'] == NAME)
VIDEO = ROOT / 'group_discussions' / NAME
STEM = VIDEO.stem
DEST = OUT / STEM
DEST.mkdir(exist_ok=True)


def analysis_video():
    if INFO['width'] <= 1920 and INFO['height'] <= 1080:
        return VIDEO, {'kind': 'original', 'width': INFO['width'],
                       'height': INFO['height'], 'fps': INFO['fps']}
    proxy = DEST / 'analysis-1920w-25fps.mp4'
    if not proxy.exists() or proxy.stat().st_size < 1024:
        print(NAME, 'creating synchronized 1920w visual copy', flush=True)
        pending = DEST / 'analysis-1920w-25fps.building.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(VIDEO),
                        '-map', '0:v:0', '-an', '-vf', 'scale=1920:1080:flags=fast_bilinear,fps=25',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(pending)], check=True)
        pending.replace(proxy)
    import cv2
    capture = cv2.VideoCapture(str(proxy))
    if not capture.isOpened():
        raise RuntimeError('analysis_video_decode_failed')
    fps = capture.get(cv2.CAP_PROP_FPS)
    duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    capture.release()
    # Container duration can exceed both streams on phone recordings. Compare
    # the visual copy to the actual source PCM used by every method.
    pcm_duration_s = len(samples) / 16000
    if abs(duration - pcm_duration_s) > .2:
        raise RuntimeError(f'analysis_video_timing_changed:{duration}')
    return proxy, {'kind': 'scaled_video_only', 'width': 1920,
                   'height': 1080, 'fps': 25, 'source_duration_s': INFO['duration_s'],
                   'pcm_duration_s': round(pcm_duration_s, 3),
                   'analysis_duration_s': round(duration, 3),
                   'video_tail_without_frames_s': round(max(0, pcm_duration_s - duration), 3)}


def dump(name, value):
    (DEST / name).write_text(json.dumps(value, indent=2, default=lambda item:
                             item.tolist() if isinstance(item, np.ndarray) else str(item)))


def load_pcm():
    pcm = DEST / 'shared-16khz.wav'
    if not pcm.exists() or pcm.stat().st_size < 44:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(VIDEO),
                        '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(pcm)],
                       check=True)
    with wave.open(str(pcm), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError('shared_pcm_format_invalid')
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').copy()
    return samples


def summarize(rows, profiles, *, observations, turns, extra=None):
    result = {
        'status': 'complete', 'method': METHOD, 'file': NAME,
        'duration_s': len(samples) / 16000, 'visible_faces': len(boxes),
        'analysis_video': visual_info,
        'turn_count': len(turns), 'row_count': len(rows),
        'observation_count': len(observations),
        'reliable_observation_count': sum(bool(item.get('reliable')) for item in observations),
        'assigned_s': round(sum(row['end_s']-row['start_s'] for row in rows
                                if row.get('status') == 'assigned'), 2),
        'unknown_s': round(sum(row['end_s']-row['start_s'] for row in rows
                               if row.get('status') == 'unknown' and not row.get('overlap_refused_s')), 2),
        'overlap_s': round(sum(row.get('overlap_refused_s', 0) for row in rows), 2),
        'ready_profiles': sum(profile['status'] == 'ready' for profile in profiles),
        'profiles': [{'slot': profile['slot_number'], 'status': profile['status'],
                      'usable_s': round(profile['usable_seconds'], 2),
                      'transcription': (profile.get('metrics', {}).get('transcription') or {}).get('status')}
                     for profile in profiles],
        'reason_counts': {reason: sum(row.get('evidence', {}).get('reason') == reason for row in rows)
                          for reason in sorted({row.get('evidence', {}).get('reason') for row in rows
                                                if row.get('evidence', {}).get('reason')})},
    }
    result.update(extra or {})
    dump(f'{METHOD}-detail.json', {'summary': result, 'turns': turns,
                                   'rows': rows, 'observations': observations,
                                   'profiles': profiles})
    dump(f'{METHOD}-summary.json', result)
    return result


started = time.time()
try:
    samples = load_pcm()
    visual_video, visual_info = analysis_video()
    boxes = [{**face, 'rotation_degrees': INFO['rotation_degrees'],
              'frame_time_s': INFO['marked_frame_s']} for face in INFO['faces']]
    print(NAME, METHOD, 'pcm_s', round(len(samples)/16000, 2),
          'faces', len(boxes), flush=True)
    if not boxes:
        raise RuntimeError('marked_faces_missing')
    if METHOD == 'existing':
        # The deployed base image has Sherpa and no Community-1 dependency.
        # Use its actual diarizer even though this comparison image also has
        # Community-1 installed for the independent PSYCON method.
        turns = diarization.diarize(samples, 16000)
        if not turns:
            raise RuntimeError('no_speech_segments')
        visual_turns = _energy_segments(samples, 16000)
        rows = assign_windows(visual_turns, boxes, visual_video)
        reasons = []
        transcript = _transcribe(samples, 16000, turns, reasons)
        profiles = build_profiles(samples, 16000, rows, boxes, transcript)
        result = summarize(rows, profiles, observations=[], turns=turns,
                           extra={'diarization_engine': turns[0].get('engine'),
                                  'visual_turn_engine': 'energy',
                                  'transcript_segments': len(transcript), 'failure_reasons': reasons})
        dump('existing-transcript.json', transcript)
    elif METHOD == 'nvidia':
        if len(boxes) > nvidia.MAX_SPEAKERS:
            raise ValueError('nemotron_eight_speaker_capacity_exceeded')
        probabilities = nvidia.streaming_logits(samples, 16000)
        turns = nvidia.activity_segments(probabilities)
        rows = nvidia.clean_windows(turns, duration_s=len(samples)/16000)
        observations = nvidia.visual_observations(rows, boxes, visual_video)
        mapping = nvidia.map_speakers(rows, observations,
                                      {int(box['slot_number']) for box in boxes})
        profiles = build_profiles(samples, 16000, rows, boxes, [],
                                  matching_version=nvidia.MATCHING_VERSION)
        result = summarize(rows, profiles, observations=observations, turns=turns,
                           extra={'mapping': mapping,
                                  'active_channels': len({turn['cluster_label'] for turn in turns}),
                                  'capacity_warning': (len({turn['cluster_label'] for turn in turns}) == 8
                                                       and len(boxes) == 8)})
    elif METHOD == 'psycon':
        diary = psycon.diarize(samples)
        quality = psycon.audio_quality_windows(samples)
        rows = psycon.clean_windows(diary.regular_turns, len(samples)/16000, quality)
        observations = psycon.active_observations(rows, boxes, visual_video, samples)
        embedder = SpeechBrainEmbedder(device='cuda')
        embeddings = {}
        for row in rows:
            if row['cluster_label'] is None:
                continue
            clip = samples[round(row['start_s']*16000):round(row['end_s']*16000)]
            if len(clip) >= 16000:
                embeddings[row['id']] = embedder.embed(clip, 16000)
        mapping = psycon.link_faces(rows, observations, embeddings,
                                    {int(box['slot_number']) for box in boxes},
                                    threshold=max(.55, embedder.verification_threshold))
        recovered = psycon.recover_supported_faces(
            rows, observations, embeddings, {int(box['slot_number']) for box in boxes})
        review_candidates = psycon.mark_review_candidates(
            rows, observations, {int(box['slot_number']) for box in boxes})
        orphaned_seconds = psycon.mark_speech_disposition(rows, observations)
        psycon.mark_playback_overlap(rows)
        profiles = psycon.make_profiles(samples, rows, boxes, diary.exclusive_turns,
                                        embedder=embedder)
        result = summarize(rows, profiles, observations=observations,
                           turns=[turn.to_dict() for turn in diary.regular_turns],
                           extra={'mapping': mapping, 'recovered_turns': recovered,
                                  'review_candidates': review_candidates,
                                  'orphaned_seconds': orphaned_seconds,
                                  'exclusive_turns': len(diary.exclusive_turns),
                                  'quality_rejected_s': round(sum(item['end_s']-item['start_s']
                                                                  for item in quality
                                                                  if item['status'] != 'usable'), 2)})
        dump('psycon-exclusive-turns.json', [turn.to_dict() for turn in diary.exclusive_turns])
        dump('psycon-quality.json', quality)
    else:
        raise ValueError(f'unknown_method:{METHOD}')
    result['elapsed_s'] = round(time.time()-started, 2)
    dump(f'{METHOD}-summary.json', result)
    print(NAME, METHOD, 'done', result['ready_profiles'], 'ready',
          result['assigned_s'], 'assigned_s', 'elapsed', result['elapsed_s'], flush=True)
except Exception as exc:
    result = {'status': 'failed', 'method': METHOD, 'file': NAME,
              'reason': f'{type(exc).__name__}:{exc}', 'elapsed_s': round(time.time()-started, 2),
              'traceback': traceback.format_exc()}
    dump(f'{METHOD}-summary.json', result)
    print(NAME, METHOD, 'FAILED', result['reason'], flush=True)
    raise
