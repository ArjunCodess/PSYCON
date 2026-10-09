"""Multi-process worker. PostgreSQL owns jobs and the shared inference resource."""
import time


def run_trainer(store, once=False, imports=None):
    """Fit durable CPU jobs independently of the long-running media queue."""
    from .training import process_training
    from .import_jobs import process_import
    try:
        while True:
            imported = process_import(imports) if imports is not None else None
            result = process_training(store)
            if result:
                print("Training:", result["id"], result["status"], flush=True)
            if once:
                return result or imported
            if result is None and imported is None:
                time.sleep(1)
    finally:
        store.pool.close()
        if imports is not None:
            imports.pool.close()


def run(service,once=False):
    from .research import process_run
    from .training import process_training
    from .import_jobs import process_import
    from .store import Store
    import os
    trainer=Store(service.store.root,database_url=os.getenv('PSYCON_TRAINER_DATABASE_URL') or service.store.url,role='psycon_trainer')
    try:
        while True:
            imported=process_import(service.store)
            session=service.process_next() if imported is None else None
            interpretation=process_run(service) if session is None else None
            training=process_training(trainer) if session is None and interpretation is None else None
            for kind,result in (('Import',imported),('Session',session),('Interpretation',interpretation),('Training',training)):
                if result:
                    print(f"{kind} {result['id']}: {result['status']}",flush=True)
            if once:
                return
            if not any((imported,session,interpretation,training)):
                time.sleep(1)
    finally:
        trainer.pool.close()
