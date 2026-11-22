from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, UserRole

def get_current_actor(
    x_actor_id: str = Header(default="1", alias="X-Actor-Id"),
    db: Session = Depends(get_db)
) -> User:
    try:
        actor_id = int(x_actor_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Actor-Id header; must be integer")

    user = db.query(User).filter(User.id == actor_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {actor_id} not found")
    return user

def require_agent(actor: User = Depends(get_current_actor)) -> User:
    if actor.role not in (UserRole.AGENT, UserRole.LEAD):
        raise HTTPException(status_code=403, detail="Agent or Lead privileges required")
    return actor
