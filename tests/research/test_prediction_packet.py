from copy import deepcopy

from backend.instrument.research import compact_prediction_metadata
from backend.instrument.store import encode


def test_repeated_model_metadata_is_losslessly_compacted_without_changing_predictions():
    rows = [dict(model_id=str(i), target='P'+str(i), score=i % 5,
                 distribution={'1': .2, '2': .8}, abstention=None, evidence_ids=['citation-'+str(n) for n in range(40)],
                 lineage=dict(snapshot_hash='frozen', feature_schema={'names': ['feature']*40}),
                 uncertainty=dict(status='uncalibrated', limitations=['Unreviewed source scores']*10))
            for i in range(1, 15)]
    original = deepcopy(rows)
    compact, registry = compact_prediction_metadata(rows)
    assert rows == original and len(registry) == 3
    restored = deepcopy(compact)
    for row in restored:
        for name in ('lineage', 'uncertainty', 'evidence_ids'):
            row[name] = registry[row[name]['metadata_ref']]
    assert restored == original
    assert len(encode(dict(predictions=compact, metadata=registry))) < len(encode(rows))
