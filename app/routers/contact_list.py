from fastapi import APIRouter, Depends, Request, UploadFile, File
from sqlalchemy.orm import Session
import csv
import io
from app.db.database import get_db
from app.models.contact import Contact
from app.dependencies import templates

router = APIRouter(prefix="/contacts")


@router.get("")
async def get_contacts(request: Request, db: Session = Depends(get_db)):
    contacts = db.query(Contact).all()
    return templates.TemplateResponse(
        "contacts/list.html",
        {"request": request, "contacts": contacts}
    )


@router.post("/add/local")
async def add_local_contact(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    contact = Contact(
        display_name=form.get("display_name"),
        email=form.get("email"),
        # ... other fields
    )
    db.add(contact)
    db.commit()

    return templates.TemplateResponse(
        "contacts/contact_row.html",
        {"request": request, "contact": contact}
    )


@router.post("/add/csv")
async def add_from_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    content = await file.read()
    csv_data = csv.DictReader(io.StringIO(content.decode()))

    new_contacts = []
    for row in csv_data:
        contact = Contact(**row)
        db.add(contact)
        new_contacts.append(contact)

    db.commit()

    return templates.TemplateResponse(
        "contacts/contact_rows.html",
        {"request": request, "contacts": new_contacts}
    )


@router.delete("/{contact_id}")
async def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    db.delete(contact)
    db.commit()
    return {"success": True}
