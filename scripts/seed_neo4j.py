import argparse
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.database.connection import SessionLocal
from backend.app.models import Application, Candidate, Company, GlobalApplicant, JobPosting, Resume, User
from backend.app.services.graph import ensure_graph_schema, sync_application_records, sync_candidate_records, sync_global_records, sync_resume_records
from backend.app.services.public_ids import format_public_id


def batches(statement, id_column, batch_size):
    last_id = 0
    while True:
        with SessionLocal() as db:
            rows = db.execute(statement.where(id_column > last_id).order_by(id_column).limit(batch_size)).all()
        if not rows: break
        yield rows
        last_id = getattr(rows[-1][0], id_column.key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed all PostgreSQL applicant relationships into Neo4j.")
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args(); ensure_graph_schema(); counts={"candidates":0,"resumes":0,"applications":0,"talent_pool":0}
    candidate_stmt=select(Candidate,User).join(User,Candidate.user_id==User.user_id)
    for rows in batches(candidate_stmt,Candidate.candidate_id,args.batch_size):
        records=[{"candidate_id":c.candidate_id,"public_id":format_public_id("candidate",c.candidate_id),"name":u.name,"email":u.email,"phone":c.phone,"location":c.location,"profile_summary":c.profile_summary,"linkedin_url":c.linkedin_url,"github_url":c.github_url,"portfolio_url":c.portfolio_url} for c,u in rows]; sync_candidate_records(records); counts["candidates"]+=len(records); print(counts)
    resume_stmt=select(Resume)
    for rows in batches(resume_stmt,Resume.resume_id,args.batch_size):
        records=[{"candidate_id":r.candidate_id,"resume_id":r.resume_id,"public_id":f"RES_{r.resume_id:03d}","name":r.original_filename,"version":r.version,"content_type":r.content_type,"parsing_status":r.parsing_status,"created_at":r.created_at.isoformat() if r.created_at else None} for (r,) in rows]; sync_resume_records(records); counts["resumes"]+=len(records); print(counts)
    app_stmt=select(Application,JobPosting,Company).join(JobPosting,Application.job_id==JobPosting.job_id).join(Company,JobPosting.company_id==Company.company_id)
    for rows in batches(app_stmt,Application.application_id,args.batch_size):
        records=[{"candidate_id":a.candidate_id,"resume_id":a.resume_id,"company_id":co.company_id,"company_public_id":format_public_id("company",co.company_id),"company_name":co.company_name,"job_id":j.job_id,"job_public_id":format_public_id("job",j.job_id),"job_title":j.job_title,"job_description":j.job_description,"skills":j.skills,"application_id":a.application_id,"application_public_id":format_public_id("application",a.application_id),"status":a.status,"scope":"JOB","applied_at":a.applied_at.isoformat() if a.applied_at else None} for a,j,co in rows]; sync_application_records(records); counts["applications"]+=len(records); print(counts)
    global_stmt=select(GlobalApplicant)
    for rows in batches(global_stmt,GlobalApplicant.global_applicant_id,args.batch_size):
        records=[{"candidate_id":g.candidate_id,"resume_id":g.resume_id,"status":g.status,"applied_at":g.applied_at.isoformat() if g.applied_at else None} for (g,) in rows]; sync_global_records(records); counts["talent_pool"]+=len(records); print(counts)
    print({"status":"complete",**counts})

if __name__ == "__main__": main()
