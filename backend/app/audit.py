from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog


def log(db: Session, actor: str, entity: str, action: str, entity_id: int | None = None,
        case_id: int | None = None, **details) -> None:
    """Append-only change log. Never pass secrets here."""
    db.add(AuditLog(username=actor, entity=entity, entity_id=entity_id, case_id=case_id, action=action,
                    details={k: v for k, v in details.items() if "key" not in k.lower() and "password" not in k.lower()}))
