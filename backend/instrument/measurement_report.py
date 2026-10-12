"""A deterministic measurement summary, explicitly separate from LLM inference."""
import math


def build(features, goal, baseline):
    definitions = {
        'speaking_time': ('Attributed speaking duration', 1., 'seconds',
                          'Total duration attributed to this speaker by the audio pipeline.'),
        'speaking_share': ('Speaking share', 100., '%',
                          'Share of exclusive attributed speaking time, not a score of leadership or engagement.'),
        'words_per_minute': ('Attributed speech rate', 1., 'words/min',
                            'Attributed word count divided by attributed speaking duration, not a fluency or personality score.'),
    }
    observations = []
    for feature in features:
        name = feature['name']; value = feature.get('value')
        if name not in definitions or type(value) not in (int,float) or not math.isfinite(value):
            continue
        if feature.get('status')!='measured' or value<0 or (name=='speaking_share' and value>1):
            continue
        label, scale, unit, meaning = definitions[name]
        observations.append(dict(feature=name,label=label,value=value,display_value=round(value*scale,2),
                                 display_unit=unit,meaning=meaning,scope='complete attributed recording',
                                 source='automated measurement',confidence=feature.get('confidence','unavailable')))
    practices = {
        'Executive': 'In your next decision-focused discussion, state one proposed decision, give its supporting reason, then invite a response.',
        'Builder': 'When proposing an idea, describe one concrete test and what result would change your view.',
        'Salesperson': 'Ask one question about the listener\'s needs before explaining how your proposal addresses them.',
        'Negotiator': 'Summarize the other speaker\'s stated concern and ask whether you understood it before proposing a compromise.',
    }
    return dict(version='measurement-summary-1',status='available' if observations else 'unavailable',
                observations=observations,selected_goal=goal,
                optional_practice=practices.get(goal,'State one point with its reason, then invite a response.'),
                practice_basis='User-selected communication goal; not a diagnosis or a recommendation inferred from source-score predictions',
                practice_effect='Not evaluated; no improvement or personalization benefit claimed',
                history_status=baseline.get('status','unavailable'),history_sessions=baseline.get('sample_count',0),
                limitations=['Attribution and transcription have not been independently validated on this corpus',
                             'No validated ideal participation share or speech-rate threshold is supplied',
                             'Contextual measurements do not establish a stable personality',
                             'This deterministic summary is not an LLM-generated report'])
