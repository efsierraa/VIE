from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base
from app.utils import utcnow

ROLES = ("admin", "guarda", "residente")
VISITOR_ROLES = ("visitante", "domiciliario")
VISIT_STATUS = ("pendiente", "dentro", "finalizada", "cancelada")
VALID_HOURS = (1, 2, 4, 8, 12, 24)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    role = Column(String(20), nullable=False)  # admin | guarda | residente
    tower = Column(String(10))
    apartment = Column(String(10))
    active = Column(Boolean, default=True, nullable=False)


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    visitor_name = Column(String(120), nullable=False)
    subject = Column(String(200), nullable=False)
    id_number = Column(String(30))
    visitor_role = Column(String(20), nullable=False)  # visitante | domiciliario

    resident_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tower = Column(String(10), nullable=False)
    apartment = Column(String(10), nullable=False)

    status = Column(String(20), default="pendiente", nullable=False)
    manual = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    entry_at = Column(DateTime)
    exit_at = Column(DateTime)
    entry_guard_id = Column(Integer, ForeignKey("users.id"))
    exit_guard_id = Column(Integer, ForeignKey("users.id"))
