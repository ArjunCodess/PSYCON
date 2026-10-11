"""Compatibility launcher for the canonical PostgreSQL research workspace."""
from ml.src.environment import load_project_environment
load_project_environment()
import os
os.environ.setdefault('PSYCON_DATABASE_ROLE','psycon_web')
if os.getenv('PSYCON_WEB_DATABASE_URL'):os.environ['PSYCON_DATABASE_URL']=os.environ['PSYCON_WEB_DATABASE_URL']
from backend.instrument.app import create_app
app=create_app()
if __name__=='__main__':
    app.run(host='127.0.0.1',port=8001,debug=False)
