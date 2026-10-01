# Discussion video rehearsal, 2026-09-27

The local `WhatsApp Video 2026-09-23 at 11.35.12 PM.mp4` is 995.6 seconds. Pinned Community-1 revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` ran on the RTX 4060 from shared mono 16 kHz PCM. It returned 320 regular and 287 exclusive turns across eight anonymous clusters. Clean-window gates left 745.71 seconds of clean speech, excluded 33.16 seconds of overlap from profiles, and rejected 20 seconds of audio-quality windows.

The current face and voice linker attributed clean turns to all eight numbered faces, and all eight profiles now pass the three-second speech gate. Participant 8 has 6.22 clean seconds from two separate turns, 11.07–12.92 and 15.25–19.62 seconds. The latter was recovered by checking two disjoint active-speaker windows within the turn against the same marked face, then requiring its voice embedding to agree with the first turn. The remaining 61.25 clean seconds stay unknown. The full GPU run completed without a runtime blocker.

| Participant | Clean training seconds | Playback seconds | Mixed overlap in playback | Profile |
| --- | ---: | ---: | ---: | --- |
| 1 | 45.87 | 62.23 | 16.35 | ready |
| 2 | 46.43 | 48.39 | 0.79 | ready |
| 3 | 66.41 | 69.06 | 2.65 | ready |
| 4 | 128.36 | 136.22 | 7.86 | ready |
| 5 | 169.07 | 173.40 | 4.34 | ready |
| 6 | 31.20 | 44.47 | 13.26 | ready |
| 7 | 189.74 | 197.92 | 8.18 | ready |
| 8 | 6.22 | 6.22 | 0 | ready |

Playback concatenates source PCM spans in chronological order. Where an assigned speaker participates in overlap, the span retains the original mixed sound, including other audible speakers. Overlap is attributed for playback through a repeated cluster link or a nearby assigned clean turn, with the supporting segment saved in evidence. It never enters acoustic, transcription, language, jitter, or training measurements. Mixed overlap seconds can appear in two participant playback files, so the column does not sum to the 33.16 seconds of overlap in the recording. The eight local review exports are `instance/psycon-final-p1.wav` through `instance/psycon-final-p8.wav`; interval provenance is in `instance/psycon_playback_report.json`.

The model audit found Community-1 grouped Participant 8's first short turn with Participant 2's later voice in `SPEAKER_05`, while the second turn sits inside Participant 5's predominant `SPEAKER_01` cluster. Their face links were made per turn instead of spreading either cluster label. The second turn's two video windows scored 0.636 and 0.852 for Participant 8; the other visible faces' best scores were 0.340 and 0.237. The two turns' SpeechBrain cosine similarity was 0.557 against the fixed 0.55 gate, so this identity is supported but close to the voice threshold and warrants direct video review before treating it as ground truth. The first Participant 3 active-speaker observation around 160.3 seconds had weak voice agreement; consistent later observations supported Participant 3 without lowering the voice threshold to 0.42. The main unresolved risk is the 61.25 unknown clean seconds and any attribution error inside mixed overlap that cannot be checked by listening to a single isolated channel.

I inspected sampled original-video frames at supporting turns for all eight faces. SFace reacquired the intended marked faces in those samples; still images cannot establish every spoken word. Participant 8's source-video review clips are `instance/psycon-review-p8.mp4` and `instance/psycon-review-p8-candidate-15s.mp4`. The later [full group comparison](group_discussions_full_report.md) runs all videos now present in `group_discussions/`. Synthetic tests cover changed seat positions, cluster splitting and merging, isolated short turns, two-window video support, overlap playback, profile exclusion, reviewer correction, and training gates.
