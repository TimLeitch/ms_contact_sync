from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.database import Base
from datetime import datetime


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    given_name = Column(String)
    surname = Column(String)
    job_title = Column(String)
    company_name = Column(String)
    department = Column(String)
    business_phones = Column(String)
    mobile_phone = Column(String)
    office_location = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)
