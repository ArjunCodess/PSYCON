"""Withdrawal invalidates weights; deletion also removes sources and frozen copies."""
import hashlib
from .store import uid
from .assets import resolve
from .answers import invalidate_participant


def delete_participant(store,sid,pid):
    from .answers import participant
    participant(store,sid,pid)
    with store.connect() as db:
        mapping=db.execute("SELECT speaker_id,status FROM speaker_mappings WHERE participant_id=%s ORDER BY revision DESC LIMIT 1",(pid,)).fetchone()
        if mapping and mapping['status']=='confirmed':
            db.execute('UPDATE speakers SET profile_id=NULL WHERE id=%s',(mapping['speaker_id'],))
            db.execute('DELETE FROM llm_runs WHERE speaker_id=%s',(mapping['speaker_id'],))
        invalidate_participant(store,pid,'Participant data deleted',db)
        snapshots=db.execute('SELECT DISTINCT snapshot_id FROM training_examples WHERE participant_id=%s',(pid,)).fetchall()
        for snap in snapshots:
            models=db.execute('SELECT m.id FROM model_versions m JOIN training_runs r ON r.id=m.run_id WHERE r.snapshot_id=%s',(snap['snapshot_id'],)).fetchall()
            for model in models:
                for asset in db.execute('SELECT asset_id FROM model_artifacts WHERE model_id=%s',(model['id'],)):
                    # Artifact bytes retain training influence. Remove them on participant deletion.
                    path=resolve(store,asset['asset_id'],verify=False)
                    path.unlink(missing_ok=True)
                    db.execute("UPDATE assets SET state='deleted',retention='source withdrawal' WHERE id=%s",(asset['asset_id'],))
                db.execute('DELETE FROM model_predictions WHERE model_id=%s',(model['id'],))
                db.execute("UPDATE model_versions SET status='retired',retirement_reason='Training source deleted; weights removed',manifest=jsonb_build_object('retired',true),limitations='[\"Training source deleted; model cannot be loaded\"]'::jsonb WHERE id=%s",(model['id'],))
            db.execute('UPDATE training_runs SET snapshot_id=NULL WHERE snapshot_id=%s',(snap['snapshot_id'],))
            db.execute('DELETE FROM training_snapshots WHERE id=%s',(snap['snapshot_id'],))
        # A batch source may include another participant. Remove its private bytes, preserve the other normalized answers.
        imports=db.execute('SELECT DISTINCT import_id FROM annotation_submissions WHERE participant_id=%s AND import_id IS NOT NULL',(pid,)).fetchall()
        db.execute('DELETE FROM annotation_submissions WHERE participant_id=%s',(pid,))
        for source in imports:
            original=db.execute('SELECT preview FROM annotation_imports WHERE id=%s FOR UPDATE',(source['import_id'],)).fetchone()
            preview=original['preview']
            removed={r['row_number'] for r in preview['rows'] if r['participant_id']==pid}
            preview['rows']=[r for r in preview['rows'] if r['participant_id']!=pid]
            preview['source_unavailable']='Original batch bytes removed after participant deletion; surviving normalized answers retain provenance hash'
            from psycopg.types.json import Jsonb
            db.execute("UPDATE annotation_imports SET source_bytes=NULL,status='redacted',preview=%s WHERE id=%s",(Jsonb(preview),source['import_id']))
            for row_number in removed:
                db.execute('DELETE FROM annotation_import_rows WHERE import_id=%s AND row_number=%s',(source['import_id'],row_number))
        db.execute('DELETE FROM session_participants WHERE id=%s',(pid,))
        db.execute('INSERT INTO deletion_tombstones(id,subject_hash,kind,backup_policy) VALUES (%s,%s,%s,%s)',(uid(),hashlib.sha256(pid.encode()).hexdigest(),'participant','Purge affected backup generations before any restore; never restore withdrawn records'))
    store.invalidate()
