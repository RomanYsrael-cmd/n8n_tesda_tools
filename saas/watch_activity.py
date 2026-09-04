"""Temporary live bridge for a job already running during a worker upgrade."""
import sys,time
from pathlib import Path
from .config import load_config
from .database import SaaSDatabase
from cblm_app.database import CBLMDatabase

def main(job_id: str) -> None:
    db=SaaSDatabase(load_config().database_url); work=next(Path('/tmp').glob(f"tesda-{job_id[:8]}-*"),None)
    if not work: return
    runtime=work/'runtime'; local=CBLMDatabase(runtime/'cblm.sqlite3')
    prior=db.events(job_id); seen={e.get('detail',{}).get('filename') for e in prior}; states={}
    while True:
        cloud=db.job(job_id)
        if not cloud or cloud.get('status') != 'running': return
        row=local.get_job(job_id) or {}; db.update(job_id,progress=max(25,int(row.get('progress') or 0)),message=row.get('message') or 'Generating documents')
        for stage in local.stages(job_id):
            key=(stage['lo_number'],stage['topic_number'],stage['stage']); value=(stage['status'],stage['attempts'],stage['message'])
            if states.get(key)!=value: states[key]=value; db.event(job_id,'stage',stage.get('message') or stage['stage'],detail={'kind':'stage','tool':'cblm',**stage})
        for folder in (runtime/'JSON Dump'/'Success',runtime/'JSON Dump'/'Failed'):
            for path in folder.glob(f'{job_id}*.json') if folder.exists() else []:
                if path.name in seen: continue
                seen.add(path.name); label='response' if 'response' in path.name else 'request' if 'request' in path.name else 'diagnostic'
                db.event(job_id,'llm',f'LLM {label}: {path.name}',detail={'kind':'llm','label':label,'filename':path.name,'content':path.read_text(encoding='utf-8')[:250000]})
        time.sleep(1.5)

if __name__=='__main__': main(sys.argv[1])
