# Group discussion pipeline comparison

This report compares the current **Existing**, **NVIDIA**, and **PSYCON** code paths on every video in `group_discussions/`. The methods share source-video PCM at 16 kHz and the numbered faces from each recording’s marked frame. The five 4K recordings use a synchronized 1920×1080, 25 fps video-only copy for visual scoring; source audio is unchanged, and the runner checks its duration against the decoded PCM within 0.2 seconds.

A ready profile has at least three usable seconds under its method’s gates. Ready counts measure coverage, not verified attribution accuracy. Overlapping original audio can be included in playback, while profile and training measurements exclude it. Participant numbers are positions within each recording; they do not identify the same person across sessions.

## Recording inventory and marked screenshots

![Numbered marked frames for all recordings](../instance/group_batch/marked-contact-sheet.jpg)

| Recording | Duration | Size GB | Visible faces | Marked frame |
| --- | ---: | ---: | ---: | --- |
| IMG_3962.MOV | 11:48 | 0.80 | 8 | [image](<../instance/group_batch/IMG_3962-marked.jpg>) |
| IMG_3983.MOV | 15:12 | 2.89 | 8 | [image](<../instance/group_batch/IMG_3983-marked.jpg>) |
| IMG_3984.MOV | 20:01 | 3.79 | 7 | [image](<../instance/group_batch/IMG_3984-marked.jpg>) |
| IMG_3995.MOV | 13:29 | 2.56 | 8 | [image](<../instance/group_batch/IMG_3995-marked.jpg>) |
| IMG_3997.MOV | 13:53 | 2.63 | 7 | [image](<../instance/group_batch/IMG_3997-marked.jpg>) |
| IMG_4002.MOV | 10:15 | 1.95 | 8 | [image](<../instance/group_batch/IMG_4002-marked.jpg>) |
| WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4 | 16:14 | 0.12 | 8 | [image](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM-marked.jpg>) |
| WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4 | 11:28 | 0.08 | 8 | [image](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM-marked.jpg>) |
| WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4 | 12:43 | 0.09 | 7 | [image](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM-marked.jpg>) |
| WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4 | 12:58 | 0.09 | 8 | [image](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM-marked.jpg>) |
| WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4 | 16:36 | 0.12 | 8 | [image](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM-marked.jpg>) |

## Comparison

![Ready profiles and unknown clean speech by method](../instance/group_batch/method-comparison.png)

| Recording | Faces | Existing ready | NVIDIA ready | PSYCON ready |
| --- | ---: | ---: | ---: | ---: |
| IMG_3962.MOV | 8 | 5 | 1 | 5 |
| IMG_3983.MOV | 8 | 1 | 0 | 4 |
| IMG_3984.MOV | 7 | 4 | 1 | 4 |
| IMG_3995.MOV | 8 | 4 | 0 | 2 |
| IMG_3997.MOV | 7 | 3 | 3 | 5 |
| IMG_4002.MOV | 8 | 5 | 1 | 2 |
| WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4 | 8 | 5 | 1 | 4 |
| WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4 | 8 | 3 | 2 | 3 |
| WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4 | 7 | 3 | 0 | 3 |
| WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4 | 8 | 2 | 1 | 5 |
| WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4 | 8 | 5 | 3 | 8 |

The folder contains 11 distinct video files. The `10.19.44 AM` WhatsApp file is byte-identical to the earlier root discussion video, so the earlier rehearsal covers that one folder recording. Three marked frames show seven people, and the other eight show eight. The runner keeps the detected count for each session instead of inventing an eighth face.

### Aggregate run outcomes

| Method | Complete runs | Failed runs | Ready profiles in complete runs | Assigned s | Unknown clean s | Excluded overlap s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EXISTING | 11 | 0 | 40 | 395.21 | 6525.42 | 0.00 |
| NVIDIA | 11 | 0 | 13 | 526.05 | 6521.64 | 458.76 |
| PSYCON | 11 | 0 | 45 | 4400.18 | 1696.24 | 472.54 |

These totals count every file in `group_discussions/` once. Ready counts measure how many numbered faces passed each method’s speech gate; they are not accuracy scores. Existing does not explicitly separate overlap, so its zero overlap total cannot be compared as an overlap detector result.

Across the 11 folder recordings, PSYCON produced 45 ready profiles across 85 visible person-session slots. Most recordings still have people with insufficient clean speech or unresolved identity, and only the repeated original discussion reached eight ready profiles. A review confirmation can resolve a supported unknown turn; it cannot manufacture three usable clean seconds for training.


## Per-recording measurements

### IMG_3962.MOV

Duration 11:48; 8 numbered faces. [Marked frame](<../instance/group_batch/IMG_3962-marked.jpg>) · [source video](<../group_discussions/IMG_3962.MOV>) · [shared PCM](<../instance/group_batch/IMG_3962/shared-16khz.wav>) · [timeline](<../instance/group_batch/IMG_3962/timeline.png>) · [review clips](<../instance/group_batch/IMG_3962/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 5 | 80.52 | 456.66 | 0.00 | 1:1.06, 2:13.12, 3:26.25, 4:21.03, 5:12.76, 6:6.29, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_3962/existing-detail.json>) |
| NVIDIA | complete | 1 | 14.52 | 596.81 | 12.80 | 1:0.00, 2:14.52, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_3962/nvidia-detail.json>) |
| PSYCON | complete | 5 | 363.34 | 113.01 | 11.27 | 1:0.00, 2:12.49, 3:61.92, 4:0.00, 5:106.29, 6:28.88, 7:153.76, 8:0.00 | [detail](<../instance/group_batch/IMG_3962/psycon-detail.json>) |

### IMG_3983.MOV

Duration 15:12; 8 numbered faces. [Marked frame](<../instance/group_batch/IMG_3983-marked.jpg>) · [source video](<../group_discussions/IMG_3983.MOV>) · [shared PCM](<../instance/group_batch/IMG_3983/shared-16khz.wav>) · [timeline](<../instance/group_batch/IMG_3983/timeline.png>) · [review clips](<../instance/group_batch/IMG_3983/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 1 | 13.87 | 703.64 | 0.00 | 1:12.37, 2:0.00, 3:0.00, 4:0.00, 5:1.50, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_3983/existing-detail.json>) |
| NVIDIA | complete | 0 | 0.00 | 680.79 | 68.31 | 1:0.00, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_3983/nvidia-detail.json>) |
| PSYCON | complete | 4 | 538.41 | 106.08 | 67.38 | 1:37.76, 2:0.00, 3:0.00, 4:66.71, 5:67.51, 6:366.43, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_3983/psycon-detail.json>) |

### IMG_3984.MOV

Duration 20:01; 7 numbered faces. [Marked frame](<../instance/group_batch/IMG_3984-marked.jpg>) · [source video](<../group_discussions/IMG_3984.MOV>) · [shared PCM](<../instance/group_batch/IMG_3984/shared-16khz.wav>) · [timeline](<../instance/group_batch/IMG_3984/timeline.png>) · [review clips](<../instance/group_batch/IMG_3984/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 4 | 36.37 | 910.64 | 0.00 | 1:3.33, 2:0.00, 3:0.00, 4:0.00, 5:3.73, 6:9.49, 7:19.82 | [detail](<../instance/group_batch/IMG_3984/existing-detail.json>) |
| NVIDIA | complete | 1 | 22.46 | 1049.40 | 49.02 | 1:0.00, 2:0.00, 3:0.00, 4:22.46, 5:0.00, 6:0.00, 7:0.00 | [detail](<../instance/group_batch/IMG_3984/nvidia-detail.json>) |
| PSYCON | complete | 4 | 715.99 | 252.82 | 47.62 | 1:30.89, 2:0.00, 3:301.22, 4:0.00, 5:366.25, 6:0.00, 7:6.83 | [detail](<../instance/group_batch/IMG_3984/psycon-detail.json>) |

### IMG_3995.MOV

Duration 13:29; 8 numbered faces. [Marked frame](<../instance/group_batch/IMG_3995-marked.jpg>) · [source video](<../group_discussions/IMG_3995.MOV>) · [shared PCM](<../instance/group_batch/IMG_3995/shared-16khz.wav>) · [timeline](<../instance/group_batch/IMG_3995/timeline.png>) · [review clips](<../instance/group_batch/IMG_3995/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 4 | 25.99 | 572.26 | 0.00 | 1:6.77, 2:2.17, 3:3.13, 4:1.51, 5:2.70, 6:1.65, 7:3.64, 8:4.41 | [detail](<../instance/group_batch/IMG_3995/existing-detail.json>) |
| NVIDIA | complete | 0 | 0.00 | 523.56 | 69.80 | 1:0.00, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_3995/nvidia-detail.json>) |
| PSYCON | complete | 2 | 291.75 | 183.49 | 82.94 | 1:0.00, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:50.68, 7:241.08, 8:0.00 | [detail](<../instance/group_batch/IMG_3995/psycon-detail.json>) |

### IMG_3997.MOV

Duration 13:53; 7 numbered faces. [Marked frame](<../instance/group_batch/IMG_3997-marked.jpg>) · [source video](<../group_discussions/IMG_3997.MOV>) · [shared PCM](<../instance/group_batch/IMG_3997/shared-16khz.wav>) · [timeline](<../instance/group_batch/IMG_3997/timeline.png>) · [review clips](<../instance/group_batch/IMG_3997/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 3 | 35.04 | 553.95 | 0.00 | 1:3.39, 2:26.04, 3:1.65, 4:3.96, 5:0.00, 6:0.00, 7:0.00 | [detail](<../instance/group_batch/IMG_3997/existing-detail.json>) |
| NVIDIA | complete | 3 | 31.11 | 661.73 | 15.23 | 1:4.34, 2:0.00, 3:7.62, 4:19.15, 5:0.00, 6:0.00, 7:0.00 | [detail](<../instance/group_batch/IMG_3997/nvidia-detail.json>) |
| PSYCON | complete | 5 | 403.13 | 135.17 | 19.56 | 1:0.00, 2:140.17, 3:32.31, 4:22.45, 5:61.66, 6:0.00, 7:145.14 | [detail](<../instance/group_batch/IMG_3997/psycon-detail.json>) |

### IMG_4002.MOV

Duration 10:15; 8 numbered faces. [Marked frame](<../instance/group_batch/IMG_4002-marked.jpg>) · [source video](<../group_discussions/IMG_4002.MOV>) · [shared PCM](<../instance/group_batch/IMG_4002/shared-16khz.wav>) · [timeline](<../instance/group_batch/IMG_4002/timeline.png>) · [review clips](<../instance/group_batch/IMG_4002/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 5 | 53.19 | 326.01 | 0.00 | 1:6.21, 2:6.50, 3:1.59, 4:31.75, 5:3.31, 6:3.08, 7:0.75, 8:0.00 | [detail](<../instance/group_batch/IMG_4002/existing-detail.json>) |
| NVIDIA | complete | 1 | 55.55 | 352.97 | 15.63 | 1:0.00, 2:54.42, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_4002/nvidia-detail.json>) |
| PSYCON | complete | 2 | 124.00 | 115.39 | 23.83 | 1:0.00, 2:36.94, 3:0.00, 4:0.00, 5:0.00, 6:72.27, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/IMG_4002/psycon-detail.json>) |

### WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4

Duration 16:14; 8 numbered faces. [Marked frame](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM-marked.jpg>) · [source video](<../group_discussions/WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4>) · [shared PCM](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM/shared-16khz.wav>) · [timeline](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM/timeline.png>) · [review clips](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 5 | 61.12 | 687.92 | 0.00 | 1:29.35, 2:10.82, 3:8.80, 4:8.74, 5:3.39, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM/existing-detail.json>) |
| NVIDIA | complete | 1 | 37.39 | 653.56 | 50.24 | 1:0.00, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00, 8:37.39 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM/nvidia-detail.json>) |
| PSYCON | complete | 4 | 413.09 | 232.30 | 50.02 | 1:0.00, 2:153.33, 3:0.00, 4:119.01, 5:27.70, 6:113.06, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.33 PM/psycon-detail.json>) |

### WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4

Duration 11:28; 8 numbered faces. [Marked frame](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM-marked.jpg>) · [source video](<../group_discussions/WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4>) · [shared PCM](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM/shared-16khz.wav>) · [timeline](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM/timeline.png>) · [review clips](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 3 | 14.51 | 443.35 | 0.00 | 1:0.00, 2:3.44, 3:1.88, 4:3.18, 5:0.00, 6:4.54, 7:0.00, 8:1.46 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM/existing-detail.json>) |
| NVIDIA | complete | 2 | 19.00 | 477.37 | 7.85 | 1:0.00, 2:0.00, 3:0.00, 4:8.26, 5:0.00, 6:0.00, 7:0.00, 8:10.74 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM/nvidia-detail.json>) |
| PSYCON | complete | 3 | 176.42 | 195.39 | 14.29 | 1:0.00, 2:0.00, 3:0.00, 4:28.53, 5:78.74, 6:0.00, 7:0.00, 8:69.16 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.15.59 PM/psycon-detail.json>) |

### WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4

Duration 12:43; 7 numbered faces. [Marked frame](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM-marked.jpg>) · [source video](<../group_discussions/WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4>) · [shared PCM](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM/shared-16khz.wav>) · [timeline](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM/timeline.png>) · [review clips](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 3 | 34.09 | 481.49 | 0.00 | 1:6.96, 2:0.00, 3:1.03, 4:0.00, 5:16.54, 6:7.14, 7:2.40 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM/existing-detail.json>) |
| NVIDIA | complete | 0 | 0.00 | 496.02 | 48.02 | 1:0.00, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM/nvidia-detail.json>) |
| PSYCON | complete | 3 | 234.06 | 179.13 | 35.34 | 1:0.00, 2:60.95, 3:30.45, 4:0.00, 5:137.95, 6:0.00, 7:0.00 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 1.16.36 PM/psycon-detail.json>) |

### WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4

Duration 12:58; 8 numbered faces. [Marked frame](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM-marked.jpg>) · [source video](<../group_discussions/WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4>) · [shared PCM](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM/shared-16khz.wav>) · [timeline](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM/timeline.png>) · [review clips](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 2 | 11.22 | 620.76 | 0.00 | 1:1.95, 2:0.00, 3:3.48, 4:0.00, 5:0.00, 6:1.60, 7:0.99, 8:3.20 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM/existing-detail.json>) |
| NVIDIA | complete | 1 | 8.75 | 537.23 | 87.90 | 1:8.75, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:0.00, 7:0.00, 8:0.00 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM/nvidia-detail.json>) |
| PSYCON | complete | 5 | 455.53 | 122.21 | 87.13 | 1:0.00, 2:0.00, 3:90.50, 4:125.63, 5:97.10, 6:0.00, 7:122.75, 8:16.81 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.02 AM/psycon-detail.json>) |

### WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4

Duration 16:36; 8 numbered faces. [Marked frame](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM-marked.jpg>) · [source video](<../group_discussions/WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4>) · [shared PCM](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM/shared-16khz.wav>) · [timeline](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM/timeline.png>) · [review clips](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM/playback/manifest.json>)

| Method | Status | Ready | Assigned s | Unknown clean s | Overlap s | Usable seconds by slot | Data |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| EXISTING | complete | 5 | 29.29 | 768.74 | 0.00 | 1:8.96, 2:0.00, 3:0.00, 4:3.53, 5:3.62, 6:2.34, 7:3.13, 8:7.71 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM/existing-detail.json>) |
| NVIDIA | complete | 3 | 337.27 | 492.20 | 33.96 | 1:116.95, 2:0.00, 3:33.19, 4:0.00, 5:0.00, 6:0.00, 7:187.13, 8:0.00 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM/nvidia-detail.json>) |
| PSYCON | complete | 8 | 684.46 | 61.25 | 33.16 | 1:45.87, 2:46.43, 3:66.41, 4:128.36, 5:169.07, 6:31.20, 7:189.74, 8:6.22 | [detail](<../instance/group_batch/WhatsApp Video 2026-09-27 at 10.19.44 AM/psycon-detail.json>) |

## Verification

`python -m pytest tests -q --basetemp instance/group_batch_pytest_final -p no:cacheprovider` passed on this branch with six skips. The GPU batch ran the three method paths on each source recording; each method summary records completion or its explicit failure reason. The [validation result](../instance/group_batch/validation.json) checks the saved outputs and playback interval provenance.

`IMG_3997.MOV` reports 832.668 seconds in its container, while its decoded PCM is 831.228 seconds and the visual copy is 831.120 seconds. The first strict check against container duration failed all three methods before inference. The runner now compares the visual copy to the PCM actually analyzed, within 0.2 seconds; all three completed on retry. The worker also emitted optional torchcodec and torchaudio backend warnings, but it processed the predecoded PCM and no final method run failed.

## What the test establishes

The scripts processed each file independently, using its own marked frame, source PCM, and method outputs. The screenshots and timelines show numbered face detections and where each method placed assigned, unknown, and overlap intervals. The playback manifests map each generated WAV back to its original source intervals. The full JSON records the per-turn evidence and profile measurements, including explicit unavailable fields.

I reviewed the original video at sampled supporting turns for all eight people in the byte-identical earlier discussion recording. That review found one Community-1 cluster mixing voices that the per-turn face and voice checks separated, and one short participant with only 6.22 usable seconds whose voice similarity of 0.557 is close to the 0.55 gate. Those findings are documented in [the original-video rehearsal](psycon_discussion_rehearsal.md). The other recordings have model outputs and marked-frame screenshots but no speaker-by-word human labels; their profile counts must not be read as verified face attribution.

## Method and evidence definitions

**Existing** uses the deployed base worker’s Sherpa diarizer, energy visual windows, and the initial visual matcher; each per-file detail records the diarization engine and transcript. **NVIDIA** uses pinned Nemotron-3 streaming speaker channels and repeated visual votes. **PSYCON** uses pinned Community-1 regular and exclusive turns, TalkNet active-speaker checks, SFace identity, and SpeechBrain voice agreement. The detailed JSON files contain the anonymous turns, assigned and unknown intervals, visual observations, profiles, and evidence reasons.
Pinned revisions and the worker’s GPU and access-token setup are in [the runtime record](psycon_group_runtime.md).

The repeatable batch code is in [`research/group_batch_inventory.py`](../research/group_batch_inventory.py), [`research/group_batch_all.ps1`](../research/group_batch_all.ps1), and [`research/group_batch_run.py`](../research/group_batch_run.py). The export and visualization scripts in the same directory rebuild the WAV review clips, timeline images, chart, and this report from saved results. The batch skips completed method summaries, so a failed recording can be retried without rerunning the others.
The [artifact validation](../instance/group_batch/validation.json) checks method counts, participant numbers, PCM boundaries, overlap exclusion, and generated WAV duration.

The original videos establish what can be seen and heard; no manually annotated speaker-by-word ground truth exists for these recordings. A model’s ready profile is therefore a candidate for review, and an unassigned interval remains unknown. Sustained-vowel measures remain unavailable from discussion audio.

[Machine-readable comparison](../instance/group_batch/comparison.csv) · [profiles](../instance/group_batch/profiles.csv) · [segments](../instance/group_batch/segments.csv)
