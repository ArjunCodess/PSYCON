# PSYCON recovery across group discussions

The guarded second pass produced 57/85 training-ready numbered profiles across 11 recordings, up 12 from the initial PSYCON pass. The remaining 28 visible person-slots need further video confirmation or usable isolated speech. Three recordings have seven marked faces, so the inventory has 85 visible slots rather than 88.

![Ready profiles by recording and method](../instance/group_batch/psycon-recovery-comparison.png)

![Numbered faces at the marked frame for every recording](../instance/group_batch/marked-contact-sheet.jpg)

## Threshold decision

The cached-model grid tested 36 voice/support pairs, then 36 visual/voice/support second-pass settings. Lowering voice similarity to 0.42 alone reached at most 44 ready profiles and produced up to three conflicts against held-out high-confidence visual turns. A guarded second pass with TalkNet score gates 0.70/0.60, SpeechBrain turn similarity 0.65, and support agreement 0.45 reached 57 ready profiles with zero conflicts in that same weak-label check. It also requires two distinct source turns at least two seconds apart, a 0.05 voice margin against another face, and no contradictory reliable face on a promoted row. These labels come from the detector itself, so zero conflicts is not a human accuracy estimate.

The original 4K frames were rescored in sampled windows from all five 4K recordings. Adding those observations did not improve this guarded count, and some top-face scores changed, so the runtime continues to use its synchronized 1920-wide analysis copy. The targeted extra TalkNet windows also did not improve the guarded count. Both probes are saved for later review.

## Per-recording result

| Recording | Faces | Existing | NVIDIA | Initial PSYCON | Recovered PSYCON | Unready slots | Unknown clean s | Overlap s |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| IMG_3962.MOV | 8 | 5 | 1 | 5 | 6 | 4, 8 | 85.82 | 11.27 |
| IMG_3983.MOV | 8 | 1 | 0 | 4 | 5 | 2, 3, 7 | 94.04 | 67.38 |
| IMG_3984.MOV | 7 | 4 | 1 | 4 | 5 | 4, 6 | 239.82 | 47.62 |
| IMG_3995.MOV | 8 | 4 | 0 | 2 | 4 | 1, 2, 4, 8 | 125.86 | 82.94 |
| IMG_3997.MOV | 7 | 3 | 3 | 5 | 6 | 1 | 98.17 | 19.56 |
| IMG_4002.MOV | 8 | 5 | 1 | 2 | 3 | 3, 4, 5, 7, 8 | 87.41 | 23.83 |
| WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4 | 8 | 5 | 1 | 4 | 5 | 1, 3, 7 | 212.98 | 50.02 |
| WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4 | 8 | 3 | 2 | 3 | 4 | 1, 2, 3, 7 | 174.56 | 14.29 |
| WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4 | 7 | 3 | 0 | 3 | 6 | 4 | 118.69 | 35.34 |
| WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4 | 8 | 2 | 1 | 5 | 5 | 1, 2, 6 | 122.21 | 87.13 |
| WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4 | 8 | 5 | 3 | 8 | 8 | none | 61.25 | 33.16 |

## Evidence and limits

The code generated 76 PSYCON playback or review WAVs from the shared PCM; 16 are tentative review clips and the rest have assigned speech. Nine numbered slots have no defensible person-specific WAV. Each [recovered detail](../instance/group_batch/IMG_3962/psycon-recovered-detail.json) records the exact assigned source intervals, visual observations, voice similarity, and profile measurements. Every recording has a corresponding recovered detail and [playback manifest](../instance/group_batch/IMG_3962/playback/manifest.json). A tentative review clip is marked `tentative_review`; it cannot train a profile until a reviewer confirms the numbered face from the original video. Mixed overlap may appear in assigned playback when a nearby clean turn supports the cluster, while overlap stays out of feature extraction.

The [full comparison report](group_discussions_full_report.md) contains the marked-frame screenshots, timelines, initial implementation, NVIDIA, and initial PSYCON results. Their original data remain separate for comparison. The [original-video rehearsal](psycon_discussion_rehearsal.md) covers sampled manual checks on one recording. The other ten recordings lack human speaker-by-word labels, so their recovered profiles remain model-supported candidates rather than validated identities.

The replay used saved outputs from pinned Community-1, TalkNet, and per-turn SpeechBrain inference on all 11 videos, then ran the current production matching and profile computation on the shared PCM. The full prior GPU batch completed all 33 method runs. `python -m pytest tests -q --basetemp instance/group_batch_pytest_final_recovery -p no:cacheprovider` passed with six skips. [Artifact validation](../instance/group_batch/validation.json) checks source PCM bounds, profiles, and playback WAV durations.
