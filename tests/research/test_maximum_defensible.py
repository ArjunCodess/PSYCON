"""Consequential checks for the frozen audit and pooled nested experiment."""
import copy
import numpy as np
import pytest

from research.maximum_defensible import (
    CONFIGS, CONVERSATION, audit_groups, evaluate_config, fit_pooled,
    guarded_choice, paired_bootstrap, pooled_predict,
)
from research.emergency_audit import metrics


def example(sid, filename, group, seat=1):
    return dict(session_id=sid, participant_id=sid+str(seat), component=group,
                source_hash=sid, metadata=dict(versions=dict(local_ingestion=dict(source_filename=filename)), source_hashes=[]),
                labels={'P1':dict(participant_code=str(seat))})


def test_unrated_recording_bridge_cannot_separate_known_people():
    links=dict(links=[dict(a=dict(recording='a'),b=dict(recording='bridge')),
                      dict(a=dict(recording='bridge'),b=dict(recording='b'))])
    with pytest.raises(ValueError,match='leakage'):
        audit_groups([example('s1','a','g1'),example('s2','b','g2')],links,dict(plan=[]))
    result=audit_groups([example('s1','a','g'),example('s2','b','g')],links,dict(plan=[]))
    assert result['known_constraint_violations']==[]
    assert result['unresolved_participant_sessions']==2


def test_shared_derived_hash_cannot_cross_groups():
    a=example('s1','a','g1');b=example('s2','b','g2')
    a['metadata']['source_hashes']=['parent'];b['metadata']['source_hashes']=['parent']
    with pytest.raises(ValueError,match='leakage'):
        audit_groups([a,b],dict(links=[]),dict(plan=[]))


def records():
    rows=[]
    for g in range(4):
        for i in range(6):
            e=dict(component=f'g{g}',speaker_id=f'{g}-{i}',
                features={n:dict(value=float(i)+g*.1) for n in CONVERSATION},
                labels={'P1':dict(score=i%4+1),'P2':dict(score=i%4+1)})
            for t in ('P1','P2'):
                rows.append(dict(example=e,target=t,speaker_id=e['speaker_id'],group=f'g{g}',rating=e['labels'][t]['score']))
    return rows


def test_pooled_preprocessing_fits_training_only_and_predictions_ignore_test_labels():
    rows=records();train=[r for r in rows if r['group']!='g3'];held=[r for r in rows if r['group']=='g3']
    config=next(c for c in CONFIGS if c['name']=='pooled-conversation-logistic-0.1')
    for r in train:r['example']['features']['response_latency']['value']=None
    m=fit_pooled(train,config)
    assert 'response_latency' not in m['names']
    before=pooled_predict(m,held)
    changed=copy.deepcopy(held)
    for r in changed:r['rating']=0;r['example']['labels'][r['target']]['score']=0
    np.testing.assert_array_equal(before,pooled_predict(m,changed))
    centre=m['pre'].named_steps['scale'].mean_[0]
    assert np.isclose(centre,np.mean([r['example']['features'][m['names'][0]]['value'] for r in train]))


def test_pooled_ordinal_produces_only_valid_scores_without_test_label_access():
    rows=records();config=next(c for c in CONFIGS if c['name']=='pooled-conversation-ordinal-0.1')
    pred=evaluate_config([r for r in rows if r['group']!='g3'],[r for r in rows if r['group']=='g3'],config)
    assert len(pred)==12 and all(type(r['prediction']) is int and 0<=r['prediction']<=4 for r in pred)


def test_selection_checks_each_rare_class_even_when_macro_recall_improves():
    base=metrics([dict(group='g',rating=k,prediction=k) for k in (1,2,3,4) for _ in range(5)])
    base.update(equal_group_agreement=.5,equal_group_mae=.5)
    d={c['name']:copy.deepcopy(base) for c in CONFIGS}
    name='pooled-core-logistic-0.1'
    d[name].update(equal_group_agreement=.9,equal_group_mae=.3,macro_recall_observed=1.)
    d[name]['per_class'][2]['recall']=0.
    assert guarded_choice(d)=='median'
    d[name]['per_class'][2]['recall']=1.
    assert guarded_choice(d)==name


def test_cluster_bootstrap_is_paired_and_counts_groups_not_ratings():
    rows=[dict(target='P1',speaker_id=f'{g}-{i}',group=g,rating=4,prediction=4) for g in ('a','b') for i in range(5)]
    out=paired_bootstrap(rows,list(reversed(rows)),draws=100)
    assert out['groups']==2 and out['agreement_interval']==[0.,0.] and out['mae_interval']==[0.,0.]
