from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings
from app.company.router import router as company_router
from app.filings.router import router as filings_router
from app.financials.router import router as financials_router
from app.research.router import router as research_router

app = FastAPI(title="Axiom")

# Named origin rather than "*": the frontend is the only browser client,
# and a wildcard would let any page on the internet call this API with the
# user's browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(company_router)
app.include_router(financials_router)
app.include_router(filings_router)
app.include_router(research_router)
