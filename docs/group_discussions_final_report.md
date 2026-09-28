# Final report: voice profiles from the group discussions

We processed all 11 recordings in `group_discussions/`. Their marked frames show 85 numbered people in total: eight recordings show eight faces, and three show seven. We tested the original method, the NVIDIA method, and two passes of PSYCON on the same video and audio. A profile is **model-supported** when the code can link speech to a numbered face and collect at least three usable seconds with a valid voice embedding. That label does not mean a person checked every speaker assignment in the original video.

| Method | Profiles produced out of 85 |
| --- | ---: |
| Original method | 40 |
| NVIDIA method | 13 |
| First PSYCON pass | 45 |
| Guarded PSYCON recovery | **57** |

The guarded recovery found 12 more profiles than the first PSYCON pass. It used repeated face and voice evidence from separate turns. We tested lower thresholds, including 0.42, but that alone did not improve the result safely and produced conflicts in the available checks. The original and NVIDIA results remain separate for comparison. Training uses only current, ready PSYCON profiles; incomplete profiles have null voice vectors.

| Recording | Numbered faces | Original | NVIDIA | First PSYCON | Recovered PSYCON |
| --- | ---: | ---: | ---: | ---: | ---: |
| IMG_3962.MOV | 8 | 5 | 1 | 5 | 6 |
| IMG_3983.MOV | 8 | 1 | 0 | 4 | 5 |
| IMG_3984.MOV | 7 | 4 | 1 | 4 | 5 |
| IMG_3995.MOV | 8 | 4 | 0 | 2 | 4 |
| IMG_3997.MOV | 7 | 3 | 3 | 5 | 6 |
| IMG_4002.MOV | 8 | 5 | 1 | 2 | 3 |
| WhatsApp Video 2026-09-27 at 1.15.33 PM.mp4 | 8 | 5 | 1 | 4 | 5 |
| WhatsApp Video 2026-09-27 at 1.15.59 PM.mp4 | 8 | 3 | 2 | 3 | 4 |
| WhatsApp Video 2026-09-27 at 1.16.36 PM.mp4 | 7 | 3 | 0 | 3 | 6 |
| WhatsApp Video 2026-09-27 at 10.19.02 AM.mp4 | 8 | 2 | 1 | 5 | 5 |
| WhatsApp Video 2026-09-27 at 10.19.44 AM.mp4 | 8 | 5 | 3 | 8 | 8 |

**What we recovered.** The code generated 76 PSYCON playback or review audio clips directly from the shared source audio. Of these, 16 are tentative review clips; they let a person inspect a possible speaker without treating that voice as confirmed. The original audio can appear in playback even when people speak over one another. Overlapping speech is excluded from acoustic profiles, because a mixed recording cannot provide a clean measurement of one person's voice.

**What remains missing.** The other 28 numbered slots have no ready PSYCON profile and no assigned clean speech. The audit found tentative visual candidates for 17 of them; the other 11 have no review candidate. Nine slots have no defensible person-specific playback clip. Across the recordings, 1,420.81 seconds of clean speech remain unattributed, and 472.54 seconds of overlap were detected. The code cannot tell which unassigned voice belongs to a particular missing person just from these totals. It also cannot infer an eighth numbered face in the three recordings where only seven faces were marked.

**How certain are the 57?** They passed the model's checks, but most assignments were not independently checked by a person against the full video. We inspected sampled clips from one recording; the other ten do not have speaker-by-word human labels. The 57 are therefore usable as model-supported output, not proven ground truth. We cannot claim that 57 is the maximum physically recoverable number, or that the 28 people did not speak. A reviewer can confirm a candidate from the original video, but an uncertain audio-to-face link must stay unknown until then.

The [marked-frame contact sheet](../instance/group_batch/marked-contact-sheet.jpg) shows the numbered faces. The [method comparison](group_discussions_full_report.md), [recovery analysis](psycon_recovery_report.md), and [rejection audit](psycon_rejection_audit.md) contain the measurements and source intervals. All 44 saved method runs and 223 generated clips passed artifact validation with no errors; the full automated test suite passed with six skips.
