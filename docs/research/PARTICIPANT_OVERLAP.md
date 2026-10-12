# Author-supplied participant overlaps

These links transcribe the two handwritten images and the project author's explicit corrections. They concern the same people appearing in different recordings, not simultaneous overlapping speech. They are author-supplied identity correspondences, not independent model-accuracy labels. No names or source photographs are published.

WAV means WhatsApp Video. All WhatsApp filenames below start with `WhatsApp Video 2026-09-27 at` and end with `PM.mp4` or `AM.mp4` as shown. Positions are relative to the displayed frame. The canonical seat number counts from the **right**, starting at 1; it is not a diarization cluster index. Conversion is `right_position = seat_count - left_position + 1`, using the committed benchmark's marked-slot counts.

The [machine-readable links](PARTICIPANT_OVERLAP.json) retain full filenames and right-based coordinates. Only the first handwritten section has the left/right correction; later sections keep their stated directions.

## 1. WAV 1.15.33 PM and IMG_3962.MOV

Every handwritten “left” in this section means “right”. Each recording has eight marked slots.

| WAV position from right | IMG_3962 position from right |
| --- | --- |
| 1 | 2 |
| 2 | 3 |
| 3 | 4 |
| 4 | 5 |
| 5 | 6 |
| 6 | 8 |

The last pair is 6 → 8, not 6 → 7. No correspondence is inferred for the unlisted seats.

## 2. WAV 10.19.44 AM and WAV 10.19.02 AM

The author states that all participants occupy exactly the same positions in these recordings. Both have eight marked slots, so right positions 1 through 8 match the same right positions 1 through 8, producing eight links.

## 3. One person across three recordings

| Recording | Author's position | Canonical position from right |
| --- | --- | --- |
| WAV 1.16.36 PM | Third from left | 5 of 7 |
| IMG_3997.MOV | Leftmost | 7 of 7 |
| IMG_3962.MOV | Rightmost | 1 of 8 |

These three slots form one identity component. Two links represent the chain; three pairwise combinations would not mean three distinct duplicate reductions.

## 4. WAV 10.19.02 AM and IMG_3983.MOV

| WAV position from left | IMG_3983 position | WAV canonical right position | IMG canonical right position |
| --- | --- | --- | --- |
| 1 | Rightmost | 8 | 1 |
| 2 | Third from left | 7 | 6 |
| 3 | Fourth from left | 6 | 5 |

Both recordings have eight marked slots. This section uses its original left/right directions without the first-section correction.

## Consequences for sampling and evaluation

The 85 person-recording slots reduce to **66 provisional identity components** when only these nineteen supplied links are merged. This is an **upper bound of 66 unique people**, not a confirmed count: remaining unlisted slots may also belong to the same people. The linked subset contains 34 slots grouped into fifteen known repeated-person components; 51 slots remain unlinked and cannot be assumed distinct.

Known repeated participants connect the eleven recordings into six provisional recording components:

| Component | Recordings that must stay together for unseen-participant evaluation |
| --- | --- |
| A | WAV 1.15.33 PM; IMG_3962.MOV; WAV 1.16.36 PM; IMG_3997.MOV |
| B | WAV 10.19.44 AM; WAV 10.19.02 AM; IMG_3983.MOV |
| C | IMG_3984.MOV |
| D | IMG_3995.MOV |
| E | IMG_4002.MOV |
| F | WAV 1.15.59 PM |

These are minimum grouping constraints. Additional identities or shared source ancestry can merge them further. No unseen-participant train/test split may separate recordings within A or B. Six components do not establish six statistically independent groups because unlisted links remain unresolved. The existing profile-coverage denominator stays 85 slots, and coverage counts stay unchanged.

The supplied links have now been applied transactionally by `research/apply_participant_overlaps.py`, with private before-state journals and database audit events. Thirty-four participant records carry fifteen known person IDs; eight newly registered linked seats have no invented answers or permissions. Application is idempotent, preserves current speaker-mapping states, and invalidates affected derived lineage. The source-score snapshot uses these grouping constraints. Repeated membership still does not establish valid chronological history without recording times and permissions.
