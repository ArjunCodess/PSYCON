import json
from pathlib import Path
import pytest
from research.apply_participant_overlaps import components


def test_author_links_preserve_corrected_directions_and_transitive_identity():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / 'docs/research/PARTICIPANT_OVERLAP.json').read_text())
    data = json.loads((root / 'docs/report_assets/nemotron-benchmark-summary.json').read_text())
    groups = components(manifest, {r['file']: r['marked_faces'] for r in data['records']})
    assert len(groups) == 15
    assert sum(map(len, groups)) == 34
    w = 'WhatsApp Video 2026-09-27 at '
    assert sorted([(w + '1.15.33 PM.mp4', 6), ('IMG_3962.MOV', 8)]) in groups
    assert sorted([(w + '1.16.36 PM.mp4', 5), ('IMG_3997.MOV', 7), ('IMG_3962.MOV', 1)]) in groups
    assert sorted([(w + '10.19.44 AM.mp4', 7), (w + '10.19.02 AM.mp4', 7), ('IMG_3983.MOV', 6)]) in groups


def test_conflicting_same_recording_seats_are_rejected():
    def link(a, b):
        return dict(a=dict(recording=a[0], seat_from_right=a[1]), b=dict(recording=b[0], seat_from_right=b[1]))
    with pytest.raises(ValueError, match='two different seats'):
        components(dict(links=[link(('a', 1), ('b', 1)), link(('b', 1), ('a', 2))]), {'a': 2, 'b': 1})
    with pytest.raises(ValueError, match='out-of-range'):
        components(dict(links=[link(('a', 3), ('b', 1))]), {'a': 2, 'b': 1})
