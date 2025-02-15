from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    given_name = Column(String)
    surname = Column(String)
    email = Column(String)
    business_phone = Column(String)
    mobile_phone = Column(String)
    job_title = Column(String)
    office_location = Column(String)
    department = Column(String)
    company = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
