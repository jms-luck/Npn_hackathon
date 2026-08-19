import ast
import re
from functools import lru_cache

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from backend.app.core.config import settings
from backend.app.core.logging_config import service_logger
from backend.app.models import Candidate, Company, JobPosting, Resume, User
from backend.app.services.cache import cache_delete_prefix, cache_get, cache_set
from backend.app.services.public_ids import format_public_id


logger = service_logger("neo4j")


@lru_cache
def neo4j_driver():
    if not settings.neo4j_uri or not settings.neo4j_username or not settings.neo4j_password:
        raise RuntimeError("Neo4j is not configured")
    return GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password), connection_timeout=8)


def ensure_graph_schema() -> None:
    statements = [
        "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS FOR (n:Candidate) REQUIRE n.candidate_id IS UNIQUE",
        "CREATE CONSTRAINT resume_id_unique IF NOT EXISTS FOR (n:Resume) REQUIRE n.resume_id IS UNIQUE",
        "CREATE CONSTRAINT job_id_unique IF NOT EXISTS FOR (n:Job) REQUIRE n.job_id IS UNIQUE",
        "CREATE CONSTRAINT company_id_unique IF NOT EXISTS FOR (n:Company) REQUIRE n.company_id IS UNIQUE",
        "CREATE CONSTRAINT skill_key_unique IF NOT EXISTS FOR (n:Skill) REQUIRE n.key IS UNIQUE",
    ]
    with neo4j_driver().session() as session:
        for statement in statements:
            session.run(statement).consume()


def parse_skills(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = None
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, (list, tuple, set)):
            values = list(parsed)
    except (ValueError, SyntaxError):
        pass
    if values is None:
        values = re.split(r"[,;|\n]", raw.strip("{}[]()"))
    result, seen = [], set()
    for value in values:
        skill = str(value).strip().strip("'\"")
        key = skill.casefold()
        if 1 < len(skill) <= 80 and key not in seen:
            seen.add(key); result.append(skill)
    return result[:50]


def sync_candidate_records(records: list[dict]) -> None:
    if not records: return
    with neo4j_driver().session() as session:
        session.run("UNWIND $rows AS row MERGE (c:Candidate {candidate_id:row.candidate_id}) SET c.public_id=row.public_id,c.name=row.name,c.email=row.email,c.phone=row.phone,c.location=row.location,c.profile_summary=row.profile_summary,c.linkedin_url=row.linkedin_url,c.github_url=row.github_url,c.portfolio_url=row.portfolio_url", rows=records).consume()


def sync_resume_records(records: list[dict]) -> None:
    if not records: return
    with neo4j_driver().session() as session:
        session.run("UNWIND $rows AS row MATCH (c:Candidate {candidate_id:row.candidate_id}) MERGE (r:Resume {resume_id:row.resume_id}) SET r.public_id=row.public_id,r.name=row.name,r.version=row.version,r.content_type=row.content_type,r.parsing_status=row.parsing_status,r.created_at=row.created_at MERGE (c)-[:HAS_RESUME]->(r)", rows=records).consume()


def sync_application_records(records: list[dict]) -> None:
    if not records: return
    with neo4j_driver().session() as session:
        session.run("UNWIND $rows AS row MATCH (c:Candidate {candidate_id:row.candidate_id}) MATCH (r:Resume {resume_id:row.resume_id}) MERGE (co:Company {company_id:row.company_id}) SET co.public_id=row.company_public_id,co.name=row.company_name MERGE (j:Job {job_id:row.job_id}) SET j.public_id=row.job_public_id,j.title=row.job_title,j.description=row.job_description,j.skills=row.skills MERGE (j)-[:AT_COMPANY]->(co) MERGE (c)-[a:APPLIED_TO]->(j) SET a.application_id=row.application_id,a.public_id=row.application_public_id,a.status=row.status,a.scope=row.scope,a.applied_at=row.applied_at MERGE (r)-[:SUBMITTED_FOR]->(j)", rows=records).consume()


def sync_global_records(records: list[dict]) -> None:
    if not records: return
    with neo4j_driver().session() as session:
        session.run("UNWIND $rows AS row MATCH (c:Candidate {candidate_id:row.candidate_id}) MATCH (r:Resume {resume_id:row.resume_id}) MERGE (c)-[p:IN_TALENT_POOL]->(r) SET p.status=row.status,p.applied_at=row.applied_at", rows=records).consume()


def sync_application_entities(job: JobPosting, candidate: Candidate, user: User, resume: Resume, company: Company, application_id: int | None, status: str, scope: str, applied_at=None) -> None:
    ensure_graph_schema()
    sync_candidate_records([{"candidate_id":candidate.candidate_id,"public_id":format_public_id("candidate",candidate.candidate_id),"name":user.name,"email":user.email,"phone":candidate.phone,"location":candidate.location,"profile_summary":candidate.profile_summary,"linkedin_url":candidate.linkedin_url,"github_url":candidate.github_url,"portfolio_url":candidate.portfolio_url}])
    sync_resume_records([{"candidate_id":candidate.candidate_id,"resume_id":resume.resume_id,"public_id":f"RES_{resume.resume_id:03d}","name":resume.original_filename,"version":resume.version,"content_type":resume.content_type,"parsing_status":resume.parsing_status,"created_at":resume.created_at.isoformat() if resume.created_at else None}])
    sync_application_records([{"candidate_id":candidate.candidate_id,"resume_id":resume.resume_id,"company_id":company.company_id,"company_public_id":format_public_id("company",company.company_id),"company_name":company.company_name,"job_id":job.job_id,"job_public_id":format_public_id("job",job.job_id),"job_title":job.job_title,"job_description":job.job_description,"skills":job.skills,"application_id":application_id,"application_public_id":format_public_id("application",application_id) if application_id else None,"status":status,"scope":scope,"applied_at":applied_at.isoformat() if hasattr(applied_at,"isoformat") else applied_at}])


def suitability_text(matched: list[str], missing: list[str], semantic_score: float | None) -> str:
    score = f" Semantic similarity is {semantic_score:.1f}%." if semantic_score is not None else ""
    if matched:
        gap = f" Missing or unverified: {', '.join(missing[:6])}." if missing else " All listed skills are represented."
        return f"The resume demonstrates {len(matched)} required skills: {', '.join(matched[:8])}.{gap}{score}"
    if missing:
        return f"No explicit required skills were verified. Review: {', '.join(missing[:8])}.{score}"
    return f"Suitability is based on semantic similarity between the complete resume and job description.{score}"


def fallback_graph(job: JobPosting, candidate: Candidate, user: User, resume: Resume, company: Company, matched: list[str], missing: list[str], semantic_score: float | None, scope: str, status: str) -> dict:
    nodes = [
        {"id": f"candidate:{candidate.candidate_id}", "type": "Candidate", "label": user.name, "properties": {"candidate_id": format_public_id("candidate", candidate.candidate_id), "email": user.email, "location": candidate.location}},
        {"id": f"resume:{resume.resume_id}", "type": "Resume", "label": resume.original_filename, "properties": {"version": resume.version}},
        {"id": f"job:{job.job_id}", "type": "Job", "label": job.job_title, "properties": {"job_id": format_public_id("job", job.job_id), "semantic_score": semantic_score}},
        {"id": f"company:{company.company_id}", "type": "Company", "label": company.company_name, "properties": {"company_id": format_public_id("company", company.company_id)}},
    ]
    edges = [
        {"source": f"candidate:{candidate.candidate_id}", "target": f"resume:{resume.resume_id}", "type": "HAS_RESUME"},
        {"source": f"candidate:{candidate.candidate_id}", "target": f"job:{job.job_id}", "type": "APPLIED_TO", "properties": {"scope": scope, "status": status, "semantic_score": semantic_score}},
        {"source": f"resume:{resume.resume_id}", "target": f"job:{job.job_id}", "type": "SUBMITTED_FOR"},
        {"source": f"job:{job.job_id}", "target": f"company:{company.company_id}", "type": "AT_COMPANY"},
    ]
    for skill in matched + missing:
        key = re.sub(r"[^a-z0-9]+", "-", skill.casefold()).strip("-")
        nodes.append({"id": f"skill:{key}", "type": "Skill", "label": skill, "properties": {"matched": skill in matched}})
        edges.append({"source": f"job:{job.job_id}", "target": f"skill:{key}", "type": "REQUIRES"})
        if skill in matched:
            edges.append({"source": f"candidate:{candidate.candidate_id}", "target": f"skill:{key}", "type": "HAS_SKILL"})
        else:
            edges.append({"source": f"candidate:{candidate.candidate_id}", "target": f"skill:{key}", "type": "MISSING_SKILL"})
    return {"nodes": nodes, "edges": edges}


def graph_suitability(job: JobPosting, candidate: Candidate, user: User, resume: Resume, company: Company, semantic_score: float | None, scope: str, status: str) -> dict:
    key = f"graph:job:{job.job_id}:candidate:{candidate.candidate_id}:resume:{resume.resume_id}"
    if cached := cache_get(key): return cached
    required = parse_skills(job.skills); text = (resume.extracted_text or "").casefold()
    matched = [skill for skill in required if skill.casefold() in text]; missing = [skill for skill in required if skill not in matched]
    graph = fallback_graph(job, candidate, user, resume, company, matched, missing, semantic_score, scope, status); source = "neo4j"
    try:
        sync_application_entities(job,candidate,user,resume,company,None,status,scope)
        with neo4j_driver().session() as session:
            session.run("MATCH (j:Job {job_id:$job_id})-[rel:REQUIRES]->() DELETE rel",job_id=job.job_id).consume()
            session.run("MATCH (c:Candidate {candidate_id:$candidate_id})-[rel:HAS_SKILL]->() DELETE rel",candidate_id=candidate.candidate_id).consume()
            session.run("MATCH (c:Candidate {candidate_id:$candidate_id})-[rel:MISSING_SKILL]->() DELETE rel",candidate_id=candidate.candidate_id).consume()
            if required:
                session.run("MATCH (j:Job {job_id:$job_id}),(c:Candidate {candidate_id:$candidate_id}) UNWIND $required AS name MERGE (s:Skill {key:toLower(name)}) SET s.name=name MERGE (j)-[:REQUIRES]->(s) FOREACH (_ IN CASE WHEN name IN $matched THEN [1] ELSE [] END | MERGE (c)-[:HAS_SKILL]->(s)) FOREACH (_ IN CASE WHEN NOT (name IN $matched) THEN [1] ELSE [] END | MERGE (c)-[:MISSING_SKILL]->(s))",job_id=job.job_id,candidate_id=candidate.candidate_id,required=required,matched=matched).consume()
            session.run("MATCH (c:Candidate {candidate_id:$candidate_id})-[a:APPLIED_TO]->(j:Job {job_id:$job_id}) SET a.semantic_score=$score",candidate_id=candidate.candidate_id,job_id=job.job_id,score=semantic_score).consume()
        logger.info("applicant_graph_updated",extra={"candidate_id":candidate.candidate_id,"job_id":job.job_id,"resume_id":resume.resume_id,"nodes":len(graph["nodes"]),"edges":len(graph["edges"])})
    except (Neo4jError, ServiceUnavailable, RuntimeError) as exc:
        source="fallback"; logger.warning("neo4j_graph_unavailable",extra={"candidate_id":candidate.candidate_id,"job_id":job.job_id,"error_type":type(exc).__name__})
    result={"candidate_id":candidate.candidate_id,"job_id":job.job_id,"matched_skills":matched,"missing_skills":missing,"semantic_score":semantic_score,"explanation":suitability_text(matched,missing,semantic_score),"source":source,"graph":graph}
    cache_set(key,result,settings.cache_graph_ttl)
    return result


def neo4j_health() -> bool:
    try: neo4j_driver().verify_connectivity(); return True
    except (Neo4jError, ServiceUnavailable, RuntimeError): return False


def clear_graph_cache(candidate_id: int | None = None) -> None:
    cache_delete_prefix(f"graph:job:" if candidate_id is None else "graph:job:")
