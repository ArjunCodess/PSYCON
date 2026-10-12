"""Apply author-supplied person links without approving speech or human labels.

Run with the configured canonical PostgreSQL. Preview by default; --apply writes
one transaction and saves a private before/after journal under .runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from backend.instrument.answers import invalidate_participant
from backend.instrument.store import Store, now, public, uid
from ml.src.environment import load_project_environment

ROOT = Path(__file__).resolve().parents[1]


def components(manifest, counts):
    parent = {}
    def find(node):
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]
    for link in manifest['links']:
        nodes = []
        for side in ('a', 'b'):
            value = link[side]
            node = (value['recording'], value['seat_from_right'])
            if type(node[1]) is not int or not 1 <= node[1] <= counts.get(node[0], 0):
                raise ValueError('Unknown recording or out-of-range seat in supplied links')
            nodes.append(node)
        parent[find(nodes[0])] = find(nodes[1])
    grouped = {}
    for node in parent:
        grouped.setdefault(find(node), []).append(node)
    result = sorted(sorted(nodes) for nodes in grouped.values())
    for nodes in result:
        if len({node[0] for node in nodes}) != len(nodes):
            raise ValueError('Identity links join two different seats in one recording')
    return result


def plan(db, groups):
    sessions = [public(dict(r)) for r in db.execute("SELECT id,filename,status,created_at FROM sessions WHERE owner_id='local' ORDER BY created_at,id")]
    participants = [public(dict(r)) for r in db.execute("SELECT * FROM session_participants WHERE owner_id='local'")]
    bindings = {}
    for filename in sorted({node[0] for group in groups for node in group}):
        candidates = [s for s in sessions if s['filename'] == filename]
        annotated = [s for s in candidates if any(p['session_id'] == s['id'] for p in participants)]
        if len(annotated) > 1:
            raise ValueError('Multiple participant-bearing analyses require explicit reconciliation')
        complete = [s for s in candidates if s['status'] == 'complete']
        session = annotated[0] if annotated else complete[-1] if complete else None
        if session is None:
            raise ValueError('No complete or participant-bearing analysis for ' + filename)
        own = [p for p in participants if p['session_id'] == session['id']]
        for p in own:
            if not p['code'].isdigit():
                raise ValueError('Participant seat codes need explicit numeric mapping')
        if len({int(p['code']) for p in own}) != len(own):
            raise ValueError('Duplicate numeric seat codes')
        conventions = db.execute("SELECT DISTINCT a.metadata->>'seat_convention' AS convention FROM annotation_submissions a JOIN session_participants p ON p.id=a.participant_id WHERE p.session_id=%s", (session['id'],)).fetchall()
        if any(r['convention'] != 'right to left in displayed frame' for r in conventions):
            raise ValueError('Existing annotation seat convention differs from supplied coordinates')
        for _, seat in [n for g in groups for n in g if n[0] == filename]:
            p = next((p for p in own if int(p['code']) == seat), None)
            if p and p['withdrawn_at']:
                raise ValueError('Cannot relink a withdrawn participant')
            bindings[(filename, seat)] = dict(session_id=session['id'], participant=p,
                                             code=p['code'] if p else f'{seat:02d}')
    out = []
    for nodes in groups:
        existing = {bindings[n]['participant']['person_id'] for n in nodes
                    if bindings[n]['participant'] and bindings[n]['participant']['person_id']}
        if len(existing) > 1:
            raise ValueError('Conflicting existing person IDs; automatic merge refused')
        person_id = next(iter(existing), str(uuid5(NAMESPACE_URL, 'psycon:author-overlap:' + json.dumps(nodes))))
        person = db.execute('SELECT * FROM people WHERE id=%s', (person_id,)).fetchone()
        if person and (person['withdrawn_at'] or person['owner_id'] != 'local'):
            raise ValueError('Person is withdrawn or outside the local owner')
        for node in nodes:
            binding = bindings[node]
            conflicts = db.execute("SELECT id FROM session_participants WHERE session_id=%s AND person_id=%s AND code<>%s", (binding['session_id'], person_id, binding['code'])).fetchall()
            if conflicts:
                raise ValueError('Person already occupies a different seat in this session')
        out.append(dict(person_id=person_id, nodes=[dict(recording=n[0], seat_from_right=n[1], **bindings[n]) for n in nodes]))
    return out


def run(apply=False):
    manifest_path = ROOT / 'docs/research/PARTICIPANT_OVERLAP.json'
    content = manifest_path.read_bytes()
    manifest = json.loads(content)
    benchmark = json.loads((ROOT / 'docs/report_assets/nemotron-benchmark-summary.json').read_text())
    groups = components(manifest, {r['file']: r['marked_faces'] for r in benchmark['records']})
    load_project_environment(override=False)
    store = Store(ROOT / 'instance/instrument')
    folder = ROOT / '.runtime/participant-overlap'
    folder.mkdir(parents=True, exist_ok=True)
    report = dict(source_sha256=hashlib.sha256(content).hexdigest(), source='Author-supplied handwritten notes and explicit corrections', apply=apply, identity_groups=len(groups))
    try:
        with store.connect() as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
            db.execute('SELECT pg_advisory_xact_lock(%s)', (0x50534F56,))
            db.execute("SELECT id FROM sessions WHERE owner_id='local' FOR UPDATE").fetchall()
            db.execute("SELECT id FROM session_participants WHERE owner_id='local' FOR UPDATE").fetchall()
            report['plan'] = plan(db, groups)
            report['created_participants'] = 0
            report['changed_participants'] = 0
            # Keep a recovery record before the transaction's first mutation.
            journal = folder / ('before-' + uid() + '.json')
            journal.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
            if apply:
                for group in report['plan']:
                    person_id = group['person_id']
                    db.execute("INSERT INTO people(id,owner_id,code) VALUES (%s,'local',%s) ON CONFLICT(id) DO NOTHING", (person_id, 'overlap-' + person_id[:12]))
                    db.execute("INSERT INTO profiles(id,user_id,label,created_at) VALUES (%s,'local',%s,%s) ON CONFLICT(id) DO NOTHING", (person_id, 'overlap-' + person_id[:12], now()))
                    for node in group['nodes']:
                        previous = node['participant']
                        if previous and previous['person_id'] == person_id:
                            continue
                        pid = previous['id'] if previous else uid()
                        if previous:
                            db.execute('UPDATE session_participants SET person_id=%s WHERE id=%s', (person_id, pid))
                        else:
                            db.execute("INSERT INTO session_participants(id,session_id,person_id,code,owner_id) VALUES (%s,%s,%s,%s,'local')", (pid, node['session_id'], person_id, node['code']))
                            db.execute("INSERT INTO speaker_mappings(id,participant_id,session_id,revision,status,reviewer_id,reason) VALUES (%s,%s,%s,1,'unmapped','author identity import','Person identity supplied; anonymous speech cluster not reviewed')", (uid(), pid, node['session_id']))
                            report['created_participants'] += 1
                        mapping = db.execute('SELECT * FROM speaker_mappings WHERE participant_id=%s ORDER BY revision DESC LIMIT 1', (pid,)).fetchone()
                        if mapping and mapping['status'] == 'confirmed':
                            speaker = db.execute('SELECT profile_id FROM speakers WHERE id=%s', (mapping['speaker_id'],)).fetchone()
                            if speaker['profile_id'] and speaker['profile_id'] not in (person_id, previous['person_id'] if previous else None):
                                raise ValueError('Confirmed speaker has conflicting history identity')
                            db.execute('UPDATE speakers SET profile_id=%s WHERE id=%s', (person_id, mapping['speaker_id']))
                        invalidate_participant(store, pid, 'Author-supplied cross-recording person identity linked', db)
                        from psycopg.types.json import Jsonb
                        db.execute("INSERT INTO audit_events(id,owner_id,action,subject_id,details) VALUES (%s,'local','participant_person_link',%s,%s)", (uid(), pid, Jsonb(dict(person_id=person_id,previous_person_id=previous['person_id'] if previous else None,recording=node['recording'],seat_from_right=node['seat_from_right'],source_sha256=report['source_sha256'],authority='Project author supplied identity correspondence; not independent speech/label validation'))))
                        node['applied_participant_id'] = pid
                        report['changed_participants'] += 1
                if report['changed_participants']:
                    db.execute('DELETE FROM baseline_profiles')
                    db.execute('DELETE FROM comparisons')
                    db.execute("UPDATE llm_runs SET status='stale',error='Person overlap changed; refresh historical inputs' WHERE condition='C' AND status IN ('complete','queued','running')")
        report['committed'] = apply
        (folder / ('applied.json' if apply else 'preview.json')).write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'plan'}, default=str))
    finally:
        store.pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    run(parser.parse_args().apply)
