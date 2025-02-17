from fastapi import APIRouter, Depends, Request, UploadFile, File
from sqlalchemy.orm import Session
import csv
import io
from app.db.database import get_db
from app.models.contact import Contact
from app.dependencies import templates
from app.auth.certificate_auth import get_access_token
import httpx
from fastapi.responses import HTMLResponse
import logging

router = APIRouter(prefix="/contacts")

logger = logging.getLogger(__name__)


@router.get("")
async def get_contacts(request: Request, db: Session = Depends(get_db)):
    contacts = db.query(Contact).order_by(Contact.display_name).all()
    # Debug log to verify we're getting contacts
    logger.info(f"Retrieved {len(contacts)} contacts from database")

    return templates.TemplateResponse(
        "contacts/contact_row.html",
        {"request": request, "contacts": contacts}
    )


@router.get("/add/local")
async def show_local_contact_form(request: Request):
    return templates.TemplateResponse(
        "contacts/add_local_form.html",
        {"request": request}
    )


@router.post("/add/local")
async def add_local_contact(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    contact = Contact(
        display_name=form.get("display_name"),
        email=form.get("email"),
        given_name=form.get("given_name"),
        surname=form.get("surname"),
        job_title=form.get("job_title"),
        company_name=form.get("company_name"),
        department=form.get("department"),
        business_phones=form.get("business_phones"),
        mobile_phone=form.get("mobile_phone"),
        office_location=form.get("office_location")
    )
    db.add(contact)
    db.commit()

    # Get all contacts in sorted order
    contacts = db.query(Contact).order_by(Contact.display_name).all()

    return templates.TemplateResponse(
        "contacts/contact_row.html",
        {"request": request, "contacts": contacts}
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
    return HTMLResponse(content="")


@router.get("/close-modal")
async def close_modal():
    return ""  # Empty response to clear the modal


@router.get("/add/gal")
async def show_gal_form(request: Request):
    access_token = await get_access_token()
    if not access_token:
        return HTMLResponse("Authentication failed", status_code=401)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/users",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$select": "id,displayName,userPrincipalName,businessPhones,mobilePhone,jobTitle,department,officeLocation",
                "$top": 999
            }
        )

        if resp.status_code != 200:
            return HTMLResponse("Failed to fetch users", status_code=resp.status_code)

        users = resp.json().get("value", [])
        return templates.TemplateResponse(
            "contacts/add_gal_form.html",
            {"request": request, "users": users}
        )


@router.post("/add/gal")
async def add_gal_contacts(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    user_ids = form.getlist("user_ids")

    access_token = await get_access_token()
    if not access_token:
        return HTMLResponse("Authentication failed", status_code=401)

    added_contacts = []
    async with httpx.AsyncClient() as client:
        for user_id in user_ids:
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/users/{user_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "$select": "displayName,givenName,surname,jobTitle,companyName,department,businessPhones,mobilePhone,officeLocation,mail"
                }
            )

            if resp.status_code == 200:
                user_data = resp.json()
                # Safely get the first business phone or None
                business_phones = user_data.get("businessPhones", [])
                business_phone = business_phones[0] if business_phones else None

                contact = Contact(
                    display_name=user_data.get("displayName"),
                    email=user_data.get("mail"),
                    given_name=user_data.get("givenName"),
                    surname=user_data.get("surname"),
                    job_title=user_data.get("jobTitle"),
                    company_name=user_data.get("companyName"),
                    department=user_data.get("department"),
                    business_phones=business_phone,
                    mobile_phone=user_data.get("mobilePhone"),
                    office_location=user_data.get("officeLocation")
                )
                db.add(contact)
                added_contacts.append(contact)

    db.commit()

    contacts = db.query(Contact).order_by(Contact.display_name).all()

    response = templates.TemplateResponse(
        "contacts/list.html",
        {"request": request, "contacts": contacts}
    )
    # Add HX-Trigger header to close modal
    response.headers["HX-Trigger"] = "closeModal"
    return response


@router.get("/{contact_id}/edit")
async def edit_contact_form(contact_id: int, request: Request, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    return templates.TemplateResponse(
        "contacts/edit_form.html",
        {"request": request, "contact": contact}
    )


@router.put("/{contact_id}")
async def update_contact(contact_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    contact = db.query(Contact).filter(Contact.id == contact_id).first()

    for field in form:
        setattr(contact, field, form[field])

    db.commit()

    return templates.TemplateResponse(
        "contacts/contact_row.html",
        {"request": request, "contacts": [contact]}
    )
