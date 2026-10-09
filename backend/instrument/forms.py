"""Versioned source-derived rubrics; communication labels require human annotation."""
import hashlib
from pathlib import Path
import re
from .store import encode

TRAITS = {
 'directness': 'How consistently the participant states an explicit claim or request that a listener can identify in context. Hedging alone does not imply low directness.',
 'proposal_orientation': 'How consistently the participant contributes concrete proposed actions or options when the task offers an opportunity. Do not infer from an assigned role.',
 'questioning': 'How consistently the participant asks relevant information-seeking or clarification questions when a question is appropriate. Rhetorical punctuation alone is insufficient.',
 'acknowledgement': 'How consistently the participant explicitly recognises the preceding peer contribution before responding when reciprocal response is appropriate. Agreement is not required.',
 'topic_control': 'How consistently the participant initiates or redirects discussion topics with an explicit link and observable uptake by others. Speaking time alone is insufficient.'
}
SCORES={'0':'Not observed despite a fair opportunity','1':'One weak or brief occurrence','2':'Repeated or noticeable, with limited effect','3':'Clear and repeated, or affects the exchange','4':'Sustained or strongly affects the exchange','N/O':'No fair opportunity or recording cannot support a rating'}
FLAGS=('limited_opportunity','overlap','poor_recording','unfamiliar_language','moderation','unequal_participation','sensitive_topic','accommodation')
VALIDITY={'fair_opportunity':('Yes','No'), 'speaker_identity':('Yes','No','Uncertain'), 'recording_support':('Yes','No','Partly'), 'context_effect':('No','Possibly','Yes')}
PATTERNS=('discussion_tracking','contribution_structure','turn_sharing','challenge_linked_change','pressure_linked_delivery')


def definitions():
    docs=Path(__file__).resolve().parents[2]/'docs'
    sheet=(docs/'PSYCON_Psychologist_Observation_Mark_Sheet.tex').read_text(encoding='utf-8')
    guide=(docs/'PSYCON_Tendency_Flag_Guide.tex').read_text(encoding='utf-8')
    items=[]
    for key,title,description in re.findall(r'\\ItemRow\{([A-T])\. ([^}]+)\}\{([^}]+)\}',sheet):
        items.append(dict(key=key,description=title+'. '+description,answer_type='ordinal',allowed_values=[0,1,2,3,4,'N/O',None],modality='audio_or_participation' if key=='T' else 'audio',requirements=dict(positive_evidence=True,event=key=='K' or key>='M',same_session_baseline=key>='Q',fair_opportunity=True,confidence=True)))
    if len(items)!=20:
        raise RuntimeError('Source marksheet no longer matches the audited v4.0 definition')
    return [dict(id='at-4.0',version='4.0',title='Contextual observation marksheet',source_hash=hashlib.sha256((sheet+guide).encode()).hexdigest(),definition=dict(scores=SCORES,flags=FLAGS,validity=VALIDITY,patterns=PATTERNS,eligibility_policy_version='audio-context-2',interpretation_rule_version='guide-1',interpretation_rule='1 weak moment; 2 possible session pattern; 3–4 supporting contextual pattern; N/O no conclusion. Project rule, not a scientific cutoff.',metadata_fields=['session_id','date','participant_code','seat_channel','observer_code','class_section','topic','observation_minutes','languages','recording_quality','contextual_account','evidence_summary','signature','signed_at','reviewer_code','reviewed_at']),items=items),
        dict(id='communication-1',version='1.0-exploratory',title='Communication observations',source_hash=hashlib.sha256(encode(TRAITS).encode()).hexdigest(),definition=dict(scores=SCORES,flags=FLAGS,validity=VALIDITY,patterns=[],guideline='Independently rate session behavior from at least two contextual moments; preserve opportunity and confidence. Do not derive labels from A–T, archetypes, or model output.'),items=[dict(key=k,description=v,answer_type='ordinal',allowed_values=[0,1,2,3,4,'N/O',None],modality='audio',requirements=dict(positive_evidence=True,repeated_evidence=True,fair_opportunity=True,confidence=True)) for k,v in TRAITS.items()])]


def install(store):
    from psycopg.types.json import Jsonb
    with store.connect() as db:
        for form in definitions():
            db.execute('INSERT INTO form_definitions VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(form['id'],form['version'],form['title'],form['source_hash'],Jsonb(form['definition'])))
            for item in form['items']:
                db.execute('INSERT INTO form_items VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(form['id'],item['key'],item['description'],item['answer_type'],Jsonb(item['allowed_values']),item['modality'],Jsonb(item['requirements'])))
            family='at' if form['id']=='at-4.0' else 'communication'
            db.execute('INSERT INTO training_tasks VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',(family,family,form['id'],Jsonb(dict(min_train=12,min_groups=3,min_validation=3,min_test=3,model='regularized multinomial approximation to ordinal scores',pass_criteria=dict(mae_below_baseline=True,min_test=3),unit='participant/session',feature_version='conversation-2'))))
