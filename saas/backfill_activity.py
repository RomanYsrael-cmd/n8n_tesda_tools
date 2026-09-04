"""One-shot recovery of safe local stage/log data after a worker deployment."""
from pathlib import Path
import json
from .config import load_config
from .database import SaaSDatabase

def main() -> None:
    db=SaaSDatabase(load_config().database_url)
    for work in Path("/tmp").glob("tesda-*"):
        runtime=work/"runtime"; sqlite=runtime/"cblm.sqlite3"
        if not sqlite.exists(): continue
        from cblm_app.database import CBLMDatabase
        local=CBLMDatabase(sqlite)
        for row in local.list_jobs():
            job_id=row["id"]
            if not db.job(job_id): continue
            db.update(job_id,progress=max(25,int(row.get("progress") or 0)),message=row.get("message") or "Generating documents")
            for stage in local.stages(job_id): db.event(job_id,"stage",stage.get("message") or stage["stage"],detail={"kind":"stage","tool":"cblm",**stage})
            for folder in (runtime/"JSON Dump"/"Success",runtime/"JSON Dump"/"Failed"):
                for path in folder.glob(f"{job_id}*.json") if folder.exists() else []:
                    label="response" if "response" in path.name else "request" if "request" in path.name else "diagnostic"
                    db.event(job_id,"llm",f"LLM {label}: {path.name}",detail={"kind":"llm","label":label,"filename":path.name,"content":path.read_text(encoding="utf-8")[:250000]})

if __name__ == "__main__": main()
