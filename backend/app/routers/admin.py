from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Holiday, User, UserRole
from app.models.schemas import HolidayOut, HolidayCreate, UserOut
from app.services.ticket_service import get_holiday_dates, run_auto_close_inactivity_check

router = APIRouter(tags=["Admin & Holidays"])

class AutoCloseRequest(BaseModel):
    as_of: Optional[datetime] = None

class AutoCloseResponse(BaseModel):
    message: str
    closed_count: int
    closed_ticket_ids: List[int]

@router.get("/api/customers", response_model=List[UserOut])
def list_customers(db: Session = Depends(get_db)):
    """List sample customers for testing customer portal."""
    return db.query(User).filter(User.role == UserRole.CUSTOMER).all()

@router.get("/api/holidays", response_model=List[HolidayOut])
def list_holidays(db: Session = Depends(get_db)):
    """List all configured holidays."""
    return db.query(Holiday).order_by(Holiday.date.asc()).all()

@router.post("/api/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def add_holiday(payload: HolidayCreate, db: Session = Depends(get_db)):
    """Add a new festival holiday."""
    existing = db.query(Holiday).filter(Holiday.date == payload.date).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Holiday for date {payload.date} already exists: {existing.name}")

    h = Holiday(date=payload.date, name=payload.name)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h

@router.post("/api/admin/run-auto-close", response_model=AutoCloseResponse)
def trigger_auto_close(
    payload: Optional[AutoCloseRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Triggers auto-close check for tickets waiting >= 5 working days (2,700 working minutes)
    without customer reply. Optional as_of timestamp for demo & testing.
    """
    holidays = get_holiday_dates(db)
    as_of = payload.as_of if payload else None
    closed_ids = run_auto_close_inactivity_check(db, holidays, as_of)

    return AutoCloseResponse(
        message=f"Auto-close scan complete. Transitioned {len(closed_ids)} inactive ticket(s) to CLOSED.",
        closed_count=len(closed_ids),
        closed_ticket_ids=closed_ids
    )
