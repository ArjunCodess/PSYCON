"""Agreement uses independently supplied paired human ratings, never predictions."""
from itertools import combinations
import math
import numpy as np
from .datasets import collect,latest


def agreement(store,family):
    form='at-4.0' if family=='at' else 'communication-1'
    with store.connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        data=collect(db)
    submissions=latest([s for s in data['annotation_submissions'] if s['form_id']==form and s['source_type']!='self_report' and s['reviewer_id']],lambda s:(s['participant_id'],s['reviewer_id'],s['source_type']),'revision')
    subjects={s['id']:s for s in submissions.values()}; grouped={}
    for a in data['annotation_answers']:
        s=subjects.get(a['submission_id'])
        if s and a['state']=='scored':grouped.setdefault((s['participant_id'],a['item_key']),{})[s['reviewer_id']]=a['score']
    pairs={}
    for (pid,target),ratings in grouped.items():
        for left,right in combinations(sorted(ratings),2):
            pairs.setdefault((target,left,right),[]).append((pid,ratings[left],ratings[right]))
    from sklearn.metrics import cohen_kappa_score
    results=[]
    for (target,left,right),rows in sorted(pairs.items()):
        y=[r[1] for r in rows];p=[r[2] for r in rows]
        k=cohen_kappa_score(y,p,labels=list(range(5)),weights='quadratic') if len(set(y+p))>1 else None
        results.append(dict(target=target,reviewers=[left,right],paired_participants=len(rows),exact_agreement=sum(a==b for a,b in zip(y,p))/len(y),mae=float(np.mean(np.abs(np.asarray(y)-np.asarray(p)))),quadratic_kappa=float(k) if k is not None and math.isfinite(k) else None,uncertainty=dict(status='unavailable',reason='Small paired pilot; no independent-group interval established'),interpretation='Label reproducibility only; no psychological validity claim'))
    return dict(family=family,pairs=results,status='available' if results else 'No independently paired human ratings')
