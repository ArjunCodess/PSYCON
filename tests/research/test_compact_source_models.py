import copy,json
import pytest
import numpy as np
from research.compact_source_models import fit,predict,select,CORE,CONVERSATION
from backend.instrument.training import infer


def examples():
    return [dict(component=f'g{g}',speaker_id=f'{g}-{i}',labels={'P1':{'score':i%4+1}},
        features={n:{'value':float(i)/10+g*.01} for n in CONVERSATION}) for g in range(4) for i in range(6)]


@pytest.mark.parametrize('candidate',['core-logistic-0.1-none','compact-logistic-0.1-balanced','core-ridge-10',
    'compact-ordinal-0.1','compact-forest','compact-extra'])
def test_compact_portable_predictions_and_probabilities(candidate):
    rows=examples();m=fit(rows,'P1',candidate);restored=json.loads(json.dumps(m))
    assert [predict(m,e) for e in rows]==[predict(restored,e) for e in rows]
    for e in rows:
        score,p=infer(m,{n:f['value'] for n,f in e['features'].items()})
        assert 0<=score<=4
        if p:assert all(0<=v<=1 for v in p.values()) and np.isclose(sum(p.values()),1.)


def test_core_excludes_context_and_features_available_only_in_omitted_group():
    rows=examples();rows[0]['features']['private_identity']={'value':123}
    for e in rows:
        if e['component']!='g3':e['features']['response_latency']['value']=None
    m=fit([e for e in rows if e['component']!='g3'],'P1','core-logistic-0.1-none')
    assert set(m['features'])<=set(CORE) and 'response_latency' not in m['features']


def test_compact_selection_uses_no_omitted_group_labels_or_features():
    rows=examples();train=[e for e in rows if e['component']!='g3'];before=select(train,'P1')
    for e in rows:
        if e['component']=='g3':
            e['labels']['P1']['score']=0
            for f in e['features'].values():f['value']=999999
    assert select(train,'P1')==before


def test_small_sample_references_remain_explicit():
    m=fit(examples()[:4],'P1','compact-ordinal-1')
    assert m['fallback'] and m['format']=='psycon-source-constant-1'


def test_ordinal_projection_handles_crossing_thresholds_and_lower_median_tie():
    artifact=dict(format='psycon-source-ordinal-1',features=[],medians=[],indicator_features=[],means=[],scales=[],
        thresholds=[{'constant':1.},{'constant':.5},{'constant':.8},{'constant':.1}])
    score,p=infer(artifact,{})
    assert score==1 and p=={'0':0.,'1':.5,'2':0.,'3':.4,'4':.1}


def test_new_logistic_tie_policy_does_not_change_legacy_artifacts():
    m=dict(format='psycon-logistic-json-1',features=[],medians=[],indicator_features=[],means=[],scales=[],
        classes=[1,4],coefficients=[[]],intercept=[1e-13])
    assert infer(m,{})[0]==4
    m['tie_tolerance']=1e-12
    assert infer(m,{})[0]==1
