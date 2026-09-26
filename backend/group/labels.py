"""Spreadsheet rows for one marked session.

The participant column uses the numbers drawn on the first frame.
Participant 1 is the face on the right. Columns A–T are marksheet 4.0 scores.
"""

from __future__ import annotations

import csv
import io
import re

from .rubric import ALLOWED_SCORES, ITEM_LETTERS


class LabelSheetError(ValueError):
    pass


_SLOT = re.compile(r"(?:participant|slot|p)?\s*0*(\d{1,2})$", re.IGNORECASE)
_SLOT_HEADERS = {"participant", "participant_id", "participant id", "slot", "slot_number", "id", "number"}
_CLASS_HEADERS = {"class", "class_name", "class name"}


def parse_label_csv(data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LabelSheetError("The spreadsheet must be a UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise LabelSheetError("The spreadsheet needs a header row")
    headers = {name.strip().lower(): name for name in reader.fieldnames if name and name.strip()}
    slot_header = next((headers[name] for name in _SLOT_HEADERS if name in headers), None)
    if slot_header is None:
        raise LabelSheetError("Add a participant column numbered the same way as the marked frame")
    class_header = next((headers[name] for name in _CLASS_HEADERS if name in headers), None)
    if class_header is None:
        raise LabelSheetError("Add a class column. Class is entered on each spreadsheet row and can differ by participant")
    item_headers = {letter: headers[letter.lower()] for letter in ITEM_LETTERS if letter.lower() in headers}
    if not item_headers:
        raise LabelSheetError("Add score columns A through T")
    rows = []
    seen: set[int] = set()
    for line_number, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values()):
            continue
        slot = _slot(raw.get(slot_header))
        if slot in seen:
            raise LabelSheetError(f"Participant {slot} is listed more than once")
        seen.add(slot)
        class_name = str(raw.get(class_header) or "").strip()
        if not class_name or len(class_name) > 64:
            raise LabelSheetError(f"Participant {slot} needs a class in the spreadsheet")
        scores = {}
        for letter, header in item_headers.items():
            value = str(raw.get(header) or "").strip().upper()
            if not value:
                continue
            if value == "NO":
                value = "N/O"
            if value not in ALLOWED_SCORES:
                raise LabelSheetError(f"Row {line_number} column {letter} must be 0–4 or N/O")
            scores[letter] = value
        if not scores:
            raise LabelSheetError(f"Participant {slot} has no scores")
        rows.append({"slot_number": slot, "class_name": class_name, "scores": scores})
    if not rows:
        raise LabelSheetError("The spreadsheet has no participant rows")
    return rows


def _slot(value: object) -> int:
    text = str(value or "").strip()
    match = _SLOT.fullmatch(text)
    if match is None:
        raise LabelSheetError(f"Participant value {text!r} is not a number from the marked frame")
    slot = int(match.group(1))
    if not 1 <= slot <= 10:
        raise LabelSheetError("Participant numbers must be from 1 to 10")
    return slot
