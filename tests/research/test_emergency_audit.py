import copy
import math
import pytest
from sklearn.metrics import cohen_kappa_score, confusion_matrix
from research.emergency_audit import align, metrics, choose, POLICY


def refs():
    return [dict(target='P1',speaker_id='a',group='g1',rating=1),
            dict(target='P1',speaker_id='b',group='g2',rating=4)]


def test_alignment_uses_ids_and_preserves_missing_outputs():
    result=align(refs(),[dict(target='P1',speaker_id='b',prediction=4)])
    assert result[0]['prediction'] is None and result[0]['missing_output']
    assert result[1]['prediction']==4
    m=metrics(result)
    assert m['total_reference_ratings']==2 and m['matched_predictions']==1
    assert m['coverage']==.5 and m['exact_agreement']==1
    assert m['missing_output_count']==1 and m['abstention_count']==0


@pytest.mark.parametrize('bad',[1.5,'4',True,-1,5,float('nan')])
def test_invalid_labels_are_never_coerced_or_silently_dropped(bad):
    with pytest.raises(ValueError): align(refs(),[dict(target='P1',speaker_id='a',prediction=bad)])


def test_duplicate_unmatched_and_reference_or_group_mismatch_fail():
    p=dict(target='P1',speaker_id='a',prediction=1)
    for predictions in [[p,p],[dict(p,speaker_id='unknown')],[dict(p,rating=4)],[dict(p,group='wrong')]]:
        with pytest.raises(ValueError): align(refs(),predictions)
    with pytest.raises(ValueError): align(refs()+refs(),[])


def test_abstentions_and_zero_class_metrics_are_explicit():
    rows=align(refs(),[dict(target='P1',speaker_id='a',prediction=None),dict(target='P1',speaker_id='b',prediction=4)])
    assert metrics(rows)['abstention_count']==1
    m=metrics([dict(group='g',rating=1,prediction=4),dict(group='g',rating=4,prediction=4)])
    assert m['per_class'][0]['recall'] is None
    assert m['per_class'][1]['recall']==0 and m['per_class'][1]['f1']==0
    assert m['per_class'][1]['precision'] is None
    assert m['macro_recall_observed']==.5


def test_metrics_match_independent_sklearn_kappa_and_confusion():
    y=[1,2,3,4,4];p=[4,2,4,4,3]
    m=metrics([dict(group='g',rating=a,prediction=b) for a,b in zip(y,p)])
    assert m['confusion']==confusion_matrix(y,p,labels=range(5)).tolist()
    assert math.isclose(m['quadratic_kappa'],cohen_kappa_score(y,p,labels=range(5),weights='quadratic'))
    assert m['exact_agreement']==.4 and m['mae']==1


def test_empty_and_constant_agreement_kappa_not_fabricated():
    assert metrics([])['exact_agreement'] is None
    m=metrics([dict(group='g',rating=4,prediction=4)])
    assert m['exact_agreement']==1 and m['quadratic_kappa'] is None


def test_selection_cannot_trade_away_mae_or_recall_for_agreement():
    base=dict(matched_predictions=20,equal_group_agreement=.6,equal_group_mae=.4,macro_recall_observed=.3)
    d={c:copy.deepcopy(base) for c in POLICY['candidates']}
    d['compact-forest'].update(equal_group_agreement=.9,equal_group_mae=.5)
    d['compact-extra'].update(equal_group_agreement=.9,macro_recall_observed=.1)
    assert choose(d)=='median'
    d['core-ridge-10'].update(equal_group_agreement=.65,equal_group_mae=.35)
    assert choose(d)=='core-ridge-10'
