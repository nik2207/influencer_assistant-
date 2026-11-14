from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import current_user

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[schemas.ContactOut])
def list_contacts(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(models.Contact).filter_by(user_id=user.id).order_by(models.Contact.name).all()


@router.post("", response_model=schemas.ContactOut, status_code=201)
def create_contact(body: schemas.ContactIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    c = models.Contact(user_id=user.id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.patch("/{contact_id}", response_model=schemas.ContactOut)
def patch_contact(contact_id: int, body: schemas.ContactPatch,
                  user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(models.Contact, contact_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Contact not found")
    data = body.model_dump(exclude_none=True)
    if "brand_record_id" in data and data["brand_record_id"] is not None:
        br = db.get(models.BrandRecord, data["brand_record_id"])
        if not br or br.user_id != user.id:
            raise HTTPException(404, "Brand not found")
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(models.Contact, contact_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Contact not found")
    db.delete(c)
    db.commit()
