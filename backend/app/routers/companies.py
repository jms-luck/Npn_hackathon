import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from backend.app.database.connection import get_db
from backend.app.models import Company, JobPosting
from backend.app.schemas.contracts import CompanyResponse
from backend.app.core.config import settings
from backend.app.services.cache import cache_get, cache_get_raw, cache_set, cache_set_raw


router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/options", response_class=Response)
def company_options(db: Session = Depends(get_db)) -> Response:
    key = "companies:options"
    if cached := cache_get_raw(key):
        return Response(cached, media_type="application/json")
    rows = db.execute(select(Company.company_id, Company.company_name).order_by(Company.company_name)).all()
    payload = [{"company_id": company_id, "company_name": company_name} for company_id, company_name in rows]
    serialized = json.dumps(payload, separators=(",", ":"))
    cache_set_raw(key, serialized, settings.cache_company_ttl)
    return Response(serialized, media_type="application/json")


@router.get("", response_model=list[CompanyResponse])
def list_companies(limit: int = Query(100, le=1000), offset: int = 0, db: Session = Depends(get_db)) -> list[Company]:
    key = f"companies:list:{limit}:{offset}"
    if cached := cache_get(key):
        return cached
    has_jobs = exists(select(JobPosting.job_id).where(JobPosting.company_id == Company.company_id))
    rows = list(db.scalars(select(Company).where(has_jobs).order_by(Company.company_name).offset(offset).limit(limit)))
    payload = [CompanyResponse.model_validate(item).model_dump(mode="json") for item in rows]
    cache_set(key, payload, settings.cache_company_ttl)
    return payload


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)) -> Company:
    key = f"companies:item:{company_id}"
    if cached := cache_get(key):
        return cached
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    payload = CompanyResponse.model_validate(company).model_dump(mode="json")
    cache_set(key, payload, settings.cache_company_ttl)
    return payload