from fastapi import APIRouter, FastAPI

from .config import settings
from .schemas import ProposalIn

API = "/api/v1"
app = FastAPI(title="TradeMind MVP")
router = APIRouter(prefix=API)


@router.get("/health")
def health():
    return {"status": "ok", "mode": "paper_only", "live_execution_enabled": False}


@router.post("/proposals")
def create_proposal(p: ProposalIn):
    return p


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: int):
    return {"id": proposal_id}


@router.get("/portfolio")
def portfolio():
    return {"equity": settings.starting_equity}


app.include_router(router)
