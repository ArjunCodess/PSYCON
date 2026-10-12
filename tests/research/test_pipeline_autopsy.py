"""Consequential regression checks for ordering and training-only ablations."""
import copy
import itertools
import numpy as np
from backend.instrument.features import extract
from research.pipeline_autopsy import fit_model, predictions, expanded, normalized_path


def test_response_latency_is_independent_of_database_row_order():
    session = dict(id='session', duration=10, topic=None, context='group_discussion')
    speakers = [dict(id='a'), dict(id='b')]
    turns = [dict(speaker_id='a', start=0, end=1),
             dict(speaker_id='b', start=2, end=3),
             dict(speaker_id='a', start=4, end=5)]
    def values(rows):
        return {(r['speaker_id'], r['name']): r['value'] for r in extract(session, speakers, rows, [])[0]}
    expected = values(turns)
    assert expected['a', 'response_latency'] == 1
    assert expected['b', 'response_latency'] == 1
    for permutation in itertools.permutations(turns):
        assert values(permutation) == expected
    assert turns[0]['start'] == 0


def training():
    return [dict(component=str(i%3), features=dict(speaking_time=dict(value=float(i)),
                 word_count=dict(value=float(i)*2)), labels=dict(P1=dict(score=i%4+1))) for i in range(16)]


def test_clean_removes_training_redundancy_and_ignores_test_values():
    train = training(); before = copy.deepcopy(train)
    m = fit_model(train, 'P1', dict(feature_set='clean', estimator='logistic_1'))
    assert m['names'] == ['speaking_time']
    assert m['removed']['word_count'] == 'training redundancy with speaking_time'
    predictions(m, [dict(features=dict(speaking_time=dict(value=1e9), word_count=dict(value=-1e9)))])
    assert train == before
    assert m['names'] == ['speaking_time']


def test_ridge_closed_form_fit_and_training_winsor_bounds():
    train = training()
    m = fit_model(train, 'P1', dict(feature_set='winsorized', estimator='ridge_10'))
    assert not m['fallback']
    np.testing.assert_allclose(m['bounds'][:, 0], [.75, 14.25])
    p = predictions(m, [dict(features=dict(speaking_time=dict(value=1e9), word_count=dict(value=2e9)))])
    assert p[0] in range(5)
    np.testing.assert_allclose(m['bounds'][:, 0], [.75, 14.25])


def test_abstention_and_unobserved_score_are_explicit():
    m = expanded([dict(rating=4, prediction=4, group='g'), dict(rating=2, prediction=None, group='g')])
    assert m['correct'] == m['matched_predictions'] == 1
    assert m['total_reference_ratings'] == 2 and m['abstention_count'] == 1
    assert m['per_class'][0]['recall'] is None
    assert m['quadratic_kappa'] is None


def test_normalized_audio_resolution_supports_both_storage_layouts(tmp_path):
    direct = tmp_path/'normalized.wav'; derived = tmp_path/'derived'/'normalized.wav'
    derived.parent.mkdir(); derived.write_bytes(b'wave')
    assert normalized_path(tmp_path) == derived
    direct.write_bytes(b'legacy')
    # Resolve an explicit current derived artifact before its legacy predecessor.
    assert normalized_path(tmp_path) == derived
