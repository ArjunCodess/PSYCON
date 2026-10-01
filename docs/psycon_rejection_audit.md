# PSYCON rejection audit

The current quality gate retains 57 model-supported profiles and 28 incomplete profiles across 85 marked slots in 11 recordings. The incomplete vectors remain null. This audit ranks evidence for inspection only; it does not change identity assignments or training eligibility.

Of the 28 incomplete slots, 28 have zero assigned clean seconds, 17 have tentative TalkNet review candidates, and 11 have none. Anonymous speech cannot establish whether any particular participant spoke for fewer than three isolated seconds or was occluded. The physical cause is therefore `undetermined` without independent review.

The taxonomy also records `insufficient_anchored_speech` when a slot has some assigned clean speech below three seconds, and `embedding_rejected` when assigned clean speech passes that duration but its embedding fails validation. Neither mode occurred in this batch. These labels describe evidence at the gate, not a diagnosis of the microphone or camera.

| Recording | Marked | Ready | Incomplete | Unknown speech s | Overlap s | Nonusable audio window s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IMG_3962.MOV | 8 | 6 | 2 | 85.82 | 11.27 | 20.18 |
| IMG_3983.MOV | 8 | 5 | 3 | 94.04 | 67.38 | 28.28 |
| IMG_3984.MOV | 7 | 5 | 2 | 239.82 | 47.62 | 6.00 |
| IMG_3995.MOV | 8 | 4 | 4 | 125.86 | 82.94 | 113.00 |
| IMG_3997.MOV | 7 | 6 | 1 | 98.17 | 19.56 | 124.00 |
| IMG_4002.MOV | 8 | 3 | 5 | 87.41 | 23.83 | 170.00 |
| WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4 | 8 | 5 | 3 | 212.98 | 50.02 | 76.00 |
| WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4 | 8 | 4 | 4 | 174.56 | 14.29 | 218.19 |
| WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4 | 7 | 6 | 1 | 118.69 | 35.34 | 175.35 |
| WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4 | 8 | 5 | 3 | 122.21 | 87.13 | 9.66 |
| WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4 | 8 | 8 | 0 | 61.25 | 33.16 | 20.00 |

Recording-level totals: 1420.81 s unknown, 472.54 s detected overlap, and 960.66 s nonusable audio windows. Nonusable windows include insufficient audio and may include silence. These measures can overlap in time and must not be added as disjoint losses.

Tentative TalkNet scores and their competing scores appear with source intervals in [`psycon-audit-matrix.json`](../instance/group_batch/psycon-audit-matrix.json). A candidate is a place to inspect the original video, not a confirmed speaker. TS-VAD, separation, and cross-session similarity were not run and are recorded as such. The ranked queue is sorted by candidate count, review seconds, and strongest score margin; those values do not certify identity.

The capture implications are recording-level inferences: detected overlap suggests that closer or separate microphones could provide more isolated speech, while missing visual candidates suggest improved camera coverage may help anchor it. The current recordings do not prove which change would resolve any individual null slot. 3 recordings have only seven marked faces, so an eighth speaker cannot acquire a numbered face profile from those markings alone.
