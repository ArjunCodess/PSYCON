import pytest
from backend.instrument.datasets import eligible


def source_data(form, key, score=0, windows=()):
    return dict(
        sessions=[dict(id='s',consent='documented',status='complete',split='development')],
        session_participants=[dict(id='p',session_id='s',code='01',person_id=None,withdrawn_at=None)],
        people=[], source_reviews=[dict(session_id='s',kind='independent',revision=1)],
        speaker_mappings=[dict(id='m',participant_id='p',speaker_id='speaker',status='confirmed',revision=1)],
        consent_records=[dict(id='consent',participant_id='p',status='documented',training_allowed=True,created_at='1')],
        annotation_reviews=[dict(id='review',submission_id='submission',decision='approved',created_at='1')],
        annotation_adjudications=[], annotation_imports=[], annotation_context_flags=[], annotation_pattern_summaries=[],
        form_definitions=[dict(id=form,source_hash='source-form-hash')],
        annotation_submissions=[dict(id='submission',participant_id='p',form_id=form,source_type='observer',reviewer_id='observer',revision=1,import_id=None,metadata={})],
        annotation_answers=[dict(id='answer',submission_id='submission',item_key=key,state='scored',score=score,fair_opportunity=True,confidence=3,component='audio')],
        annotation_evidence=[dict(answer_id='answer',**w) for w in windows],
        annotation_validity_checks=[dict(submission_id='submission',name=k,category='Yes') for k in ('speaker_identity','recording_support')],
        evidence=[])


def test_v5_preserves_source_version_instead_of_silently_selecting_other_labels():
    rows=eligible(source_data('psycon-context-5.0','A'),'contextual-v5')
    assert len(rows)==1 and rows[0]['eligible']
    assert rows[0]['form_id']=='psycon-context-5.0'
    assert not eligible(source_data('psycon-context-5.0','A'),'at')
    with pytest.raises(ValueError,match='Unknown'):
        eligible({},'unsupported')


def test_v5_does_not_bypass_human_review_or_event_requirements():
    data=source_data('psycon-context-5.0','Q',score=1)
    data['annotation_reviews']=[]
    reasons=eligible(data,'contextual-v5')[0]['reasons']
    assert 'Needs independent review' in reasons
    assert 'Positive rating lacks timestamped evidence' in reasons
    assert 'Event and response windows required' in reasons
    assert 'Earlier same-session baseline required' in reasons


def test_v5_role_scores_are_not_misclassified_as_core_event_targets():
    reasons=eligible(source_data('psycon-context-5.0','P1'),'contextual-v5')[0]['reasons']
    assert any('Role-specific v5 targets' in r for r in reasons)
    assert 'Event and response windows required' not in reasons
    reasons=eligible(source_data('psycon-context-5.0','S'),'contextual-v5')[0]['reasons']
    assert 'Vocal-change acoustic features unavailable in current extractor' in reasons


def test_source_exploration_never_fabricates_missing_label_information():
    data=source_data('psycon-context-5.0','P1',score=2)
    data['annotation_reviews']=[]
    data['annotation_validity_checks']=[]
    data['annotation_answers'][0]['confidence']=None
    data['annotation_answers'][0]['fair_opportunity']=None
    row=eligible(data,'source-v5-exploratory')[0]
    assert row['eligible'] and not row['strict_behavioral_eligibility']
    assert row['observer_confidence'] is None and row['fair_opportunity'] is None
    assert row['review_id'] is None and row['windows']==[]
    assert 'Needs independent review' in row['unmet_validation_requirements']
    data['speaker_mappings'][0]['status']='uncertain'
    assert not eligible(data,'source-v5-exploratory')[0]['eligible']
    data['speaker_mappings'][0]['status']='confirmed'
    data['annotation_answers'][0]['state']='not_observed'
    data['annotation_answers'][0]['score']=None
    assert not eligible(data,'source-v5-exploratory')[0]['eligible']


def test_source_training_requires_explicit_exploratory_acknowledgement():
    from backend.instrument.training import queue
    class Store:
        def one(self,*args): return dict(manifest=dict(study='source_exploration'))
        def rows(self,*args): return []
    with pytest.raises(ValueError,match='Explicit exploratory'):
        queue(Store(),'snapshot')
