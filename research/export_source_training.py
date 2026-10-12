"""Export aggregate results and a private model bundle from a completed source fit."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from ml.src.environment import load_project_environment
from backend.instrument.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    load_project_environment(override=False)
    store = Store('instance/instrument')
    try:
        run = store.one('SELECT * FROM training_runs WHERE id=%s', (args.run,))
        snapshot = store.one('SELECT * FROM training_snapshots WHERE id=%s', (run['snapshot_id'],))
        assert run['status'] == 'complete' and snapshot['task_id'] == 'source-v5-exploratory'
        assert not store.rows('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s', (snapshot['id'],))
        models = store.rows('SELECT * FROM model_versions WHERE run_id=%s ORDER BY target', (run['id'],))
        assert len(models) == 14 and all(m['evaluation_status'] == 'exploratory' for m in models)
        manifest = snapshot['manifest']
        summary = dict(run_id=str(run['id']), snapshot_id=str(snapshot['id']), snapshot_hash=snapshot['sha256'],
                       status=run['status'], family=snapshot['task_id'], versions=run['versions'],
                       label_policy=manifest['label_policy'], validation_status=manifest['validation_status'],
                       examples=len(manifest['examples']), recordings=len({e['session_id'] for e in manifest['examples']}),
                       groups=len({e['component'] for e in manifest['examples']}),
                       retained_scores=sum(len(e['labels']) for e in manifest['examples']),
                       targets=[dict(target=m['target'], training_labels=m['manifest']['train_n'],
                                     groups=m['manifest']['train_groups'], status=m['status'],
                                     evaluation_status=m['evaluation_status'], regularization=m['manifest']['regularization']) for m in models],
                       limitations=models[0]['limitations'])
        summary['fitted_score_labels'] = sum(t['training_labels'] for t in summary['targets'])
        assert summary['fitted_score_labels'] == 423
        private = Path('.runtime/participant-overlap/source-v5-models.zip')
        with zipfile.ZipFile(private, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for model in models:
                path = Path('instance/instrument/models') / str(model['id']) / 'model.json'
                payload = path.read_bytes()
                artifact = json.loads(payload)
                assert artifact['format'] == 'psycon-logistic-json-1'
                archive.writestr(model['target'] + '/model.json', payload)
                archive.writestr(model['target'] + '/manifest.json', json.dumps(model['manifest'], indent=2))
            archive.writestr('summary.json', json.dumps(summary, indent=2))
        public = Path('docs/report_assets/source-training-summary.json')
        public.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(models=len(models), active=sum(m['status']=='active' for m in models),
                              labels=summary['fitted_score_labels'], bundle=str(private),
                              bundle_sha256=hashlib.sha256(private.read_bytes()).hexdigest())))
    finally:
        store.pool.close()


if __name__ == '__main__':
    main()
