# Group session spreadsheet

One CSV belongs to one marked video. It is the psychologist marksheet, version 4.0, copied into columns. The paper form is `docs/PSYCON_Psychologist_Observation_Mark_Sheet.tex`.

Upload the video first. The page numbers each face from the right. Then press **Add spreadsheet to training** while that session is the one on screen. The file name does not choose the session.

## File

Save as CSV, UTF-8. The first row is the header. One data row is one person on that frame. Do not add a second header, a title row, or a totals row.

```text
participant,class,A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T
```

`participant` is the number drawn on the face. Participant 1 is the person on the right. Participant 2 is the next person to their left. Do not put a legal name in this column.

`class` is the Class / section line on that person's sheet. It can differ from row to row. Use the same text the psychologist wrote, such as `10-A` or `9-B`.

`A` through `T` are the rating boxes. Each cell is only `0`, `1`, `2`, `3`, `4`, or `N/O`. Fill all twenty items for every person on the frame.

## How to copy a score

| Mark on the sheet | Cell |
| --- | --- |
| 0, not seen, and the person had a fair chance | `0` |
| 1, one weak or brief occurrence | `1` |
| 2, repeated or noticeable, with limited effect | `2` |
| 3, clear and repeated, or it affects the exchange | `3` |
| 4, sustained, or it strongly affects the exchange | `4` |
| N/O, no fair chance, or the recording cannot support a rating | `N/O` |

`0` is a real rating. It is not the same as `N/O`. Gaze direction alone is not evidence for A. Poor audio is not a vocal-delivery score for S. An interruption by someone else is not G.

For Q, R, S, and T, score the change against that same person's earlier behaviour in this recording. Do not compare them with the person beside them. If that earlier baseline was never available, use `N/O`.

## What each letter is

The words are the item titles on the scoring sheet.

| Column | Area | What the psychologist rated |
| --- | --- | --- |
| A | Discussion tracking | Loses the active discussion thread |
| B | Discussion tracking | Response does not address the preceding point |
| C | Discussion tracking | Does not adjust after the discussion changes |
| D | Discussion tracking | Needs clear spoken information repeated |
| E | Contribution structure | Idea order is hard to follow |
| F | Contribution structure | Claim without the requested reason or example |
| G | Contribution structure | Stops before completing the central point |
| H | Contribution structure | Moves away from the task without a clear link |
| I | Turn-taking | Starts speaking before a turn is available |
| J | Turn-taking | Keeps overlapping after another speaker is clear |
| K | Turn-taking | Holds the floor after a cue to share it |
| L | Turn-taking | Does not acknowledge a direct peer contribution |
| M | Response to challenge | Sharp behavioural change right after disagreement |
| N | Response to challenge | That change continues after the exchange moves on |
| O | Response to challenge | Participation falls after a challenge |
| P | Response to challenge | Does not revise or clarify after clear feedback |
| Q | Pressure-linked delivery | Speaking rate changes after a pressure event |
| R | Pressure-linked delivery | Pauses or hesitations increase after a pressure event |
| S | Pressure-linked delivery | Volume, pitch, or steadiness changes after a pressure event |
| T | Pressure-linked delivery | Movement or participation changes after a pressure event |

## What stays on the paper sheet

These lines on the marksheet are not CSV columns. The training file stores the class and the twenty ratings only.

- Session ID, date, topic, language, and observation minutes
- Observer name, signature, and reviewer code
- Seat or speaker channel
- The written timestamp, quote, and evidence note beside each score above 0
- The Q–T baseline and trigger notes
- Context checkboxes, validity yes/no lines, and the pattern summary

A score above 0 still needs that written evidence on the paper sheet. The CSV does not replace the sheet.

Do not put names, diagnoses, personality labels, or the pattern checkboxes into A–T. The pattern summary is not a substitute for the twenty ratings.

## Example

Three people were marked. Person 1 is on the right and is in 10-A. Person 3 is further left and is in 9-B. The numbers below are examples of how to type the sheet, not a real session.

```text
participant,class,A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T
1,10-A,0,1,0,0,2,0,0,0,1,0,0,0,0,0,0,0,N/O,0,0,1
2,10-A,0,0,0,0,0,0,1,0,0,2,0,0,1,0,0,0,0,1,0,0
3,9-B,N/O,N/O,N/O,0,0,0,0,1,0,0,0,1,0,0,2,0,0,0,N/O,0
```

Person 1 has a brief mismatch on B, a noticeable organisation problem on E, one early turn entry on I, and a participation change on T. Q is `N/O` because that person's earlier speaking-rate baseline could not be judged. Person 3 has `N/O` on A–C because they had no fair chance to follow the opening, and `N/O` on S because the audio at that moment could not support a vocal rating.
