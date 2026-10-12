import copy
import numpy as np
import pytest

from research.defensible_source_models import fit_candidate, predict, select, measures, eligible_names
from backend.instrument.research import measurement_focus, validate_output


def examples():
    return [dict(component=f'g{g}', speaker_id=f'{g}-{i}', labels={'P1': {'score': (i % 3)+1}},
                 features={'speech': {'value': float(i)}, 'P2__future': {'value': 99.},
                           'P1__context': {'value': None if i % 2 else float(g)}})
            for g in range(4) for i in range(5)]


@pytest.mark.parametrize('candidate',['median','mode','logistic-0.1-none','ridge-10'])
def test_portable_source_prediction_round_trip(candidate):
    rows = examples(); model = fit_candidate(rows,'P1',candidate)
    import json
    restored = json.loads(json.dumps(model))
    assert [predict(model,e) for e in rows] == [predict(restored,e) for e in rows]
    assert all(0 <= predict(model,e)[0] <= 4 for e in rows)


def test_unavailable_features_and_other_target_context_cannot_enter_training():
    rows = examples(); rows[0]['features']['test_only']={'value':42.}
    assert 'test_only' not in eligible_names(rows[1:],'P1')
    assert 'P2__future' not in eligible_names(rows,'P1')


def test_tiny_training_set_falls_back_to_explicit_population_reference():
    model=fit_candidate(examples()[:4],'P1','ridge-10')
    assert model['format']=='psycon-source-constant-1' and model['fallback']


def test_selection_uses_only_training_groups_not_omitted_labels():
    rows=examples(); train=[e for e in rows if e['component']!='g3']
    before=select(train,'P1')
    for e in rows:
        if e['component']=='g3':
            e['labels']['P1']['score']=4; e['features']['speech']['value']=99999.
    assert select(train,'P1')==before


def test_sensitivity_selection_cannot_use_omitted_labels():
    from research.sensitivity_source_models import select_for_sensitivity
    rows=examples(); train=[e for e in rows if e['component']!='g3']
    before=select_for_sensitivity(train,'P1')
    for e in rows:
        if e['component']=='g3':
            e['labels']['P1']['score']=4; e['features']['speech']['value']=99999.
    assert select_for_sensitivity(train,'P1')==before


def test_sensitivity_has_explicit_zero_support_and_one_vs_rest_counts():
    rows=[dict(rating=1,prediction=1,group='a'),dict(rating=1,prediction=4,group='a'),
          dict(rating=4,prediction=4,group='b')]
    m=measures(rows)
    assert m['by_score'][0]['sensitivity'] is None
    assert m['by_score'][1]['sensitivity']==.5
    assert m['by_score'][4]['specificity']==.5
    assert m['macro_sensitivity']==.75


def packet_and_report():
    focus=measurement_focus([dict(name='speaking_share',value=.178,unit='proportion',status='measured')])
    packet=dict(target_speaker_id='s',transcript=[dict(id='u',speaker_id='s')],evidence=[],report_focus=focus)
    claim=dict(speaker_id='s',observation='Attributed speaking share is 17.80%.',inference='Participation depends on role.',
               evidence_ids=['u'],confidence='moderate',limitation='No validated norm.',
               suggestion='Try stating the decision before its supporting reason.',feature_names=['speaking_share'])
    return packet,dict(claims=[claim],summary='Measured context',limitations=['No prior history'])


def test_duplicate_claims_are_rejected_instead_of_silently_deduplicated():
    p,r=packet_and_report();r['claims'].append(copy.deepcopy(r['claims'][0]))
    with pytest.raises(ValueError,match='Repeated'):validate_output(r,p,'C')


@pytest.mark.parametrize('change,error',[
    ({'observation':'Speaking share is 99.90%.'},'reproduce'),
    ({'feature_names':['invented']},'supplied measured'),
    ({'confidence':'high'},'high confidence'),
])
def test_structured_report_cannot_invent_metrics_or_confidence(change,error):
    p,r=packet_and_report();r['claims'][0].update(change)
    with pytest.raises(ValueError,match=error):validate_output(r,p,'C')


def test_structured_report_accepts_traceable_measured_values():
    p,r=packet_and_report();assert validate_output(r,p,'C')==r


def test_invalid_or_unavailable_metrics_do_not_create_report_anchors():
    assert measurement_focus([dict(name='speaking_share',value=2.,unit='proportion',status='measured')]) is None
    assert measurement_focus([dict(name='words_per_minute',value=np.nan,unit='words/min',status='measured')]) is None


def test_history_only_comparison_keeps_every_other_input_identical():
    from backend.instrument.research import history_only_pair
    p,r=packet_and_report();p['personal_baseline']={'status':'available','sample_count':3,'statistics':{'speech':1.}}
    pair=history_only_pair(p)
    assert pair['without_history']=={k:v for k,v in pair['with_history'].items() if k!='personal_baseline'}
    assert p['personal_baseline']['sample_count']==3
    p['personal_baseline']['status']='insufficient_history'
    with pytest.raises(ValueError,match='unavailable'):history_only_pair(p)


def test_measurement_summary_does_not_depend_on_predicted_scores():
    from backend.instrument.measurement_report import build
    report=build([dict(name='speaking_share',value=.178,unit='proportion',status='measured',confidence='moderate')],
                 'Executive',{'status':'insufficient_history','sample_count':0})
    assert report['observations'][0]['display_value']==17.8
    assert report['history_sessions']==0
    assert report['practice_effect'].startswith('Not evaluated')


def test_feature_denominators_use_actual_opportunities_and_turn_counts():
    from backend.instrument.features import extract
    session=dict(id='fixture',duration=10.,topic=None,context='discussion')
    turns=[dict(speaker_id='s',start=0.,end=2.),dict(speaker_id='other',start=2.,end=3.),
           dict(speaker_id='s',start=4.,end=6.)]
    texts=['Why?', 'We should test.', 'Maybe this works.', 'I agree.']
    utterances=[dict(id=f'u{i}',speaker_id='s',start=i*.4,end=i*.4+.3,text=text) for i,text in enumerate(texts)]
    features,_,_=extract(session,[dict(id='s'),dict(id='other')],turns,utterances)
    own={f['name']:f for f in features if f['speaker_id']=='s'}
    assert own['mean_turn_duration']['denominator']==2
    assert own['question_ratio']['denominator']==4
    assert own['open_question_ratio']['denominator']==1
    assert own['unhedged_proposal_ratio']['denominator']==1
    assert own['words_per_minute']['denominator']==4.
    assert own['question_rate']['denominator']==10.
