from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String

from app.database import Base
from app.utils import utcnow

ROLES = ("admin", "guarda", "residente")
VISITOR_ROLES = ("visitante", "domiciliario")
VISIT_STATUS = ("pendiente", "dentro", "finalizada", "cancelada")
VALID_HOURS = (1, 2, 4, 8, 12, 24)
PACKAGE_STATUS = ("en_porteria", "entregado", "confirmado", "disputa", "cancelado")
DIAS_FOTO_ENTREGADA = 30


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nombres = Column(String(120), nullable=False, default="")
    apellidos = Column(String(120), nullable=False, default="")
    role = Column(String(20), nullable=False)  # admin | guarda | residente
    tower = Column(String(10))
    apartment = Column(String(10))
    active = Column(Boolean, default=True, nullable=False)
    full_name = Column(String(120))  # legado: solo se usa para migrar datos viejos

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}".strip()


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    short_code = Column(String(8), unique=True, index=True)  # código corto para digitar en portería
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


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    short_code = Column(String(8), unique=True, index=True)
    resident_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    description = Column(String(200))
    photo = Column(LargeBinary)
    photo_mime = Column(String(40))
    status = Column(String(20), default="en_porteria", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    delivered_at = Column(DateTime)
    delivered_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)
    photo_delete_after = Column(DateTime)  # la foto se borra sola 30 días tras la entrega

    # Paquete para alguien sin cuenta en el sistema: la cédula reemplaza al QR
    tercero = Column(Boolean, default=False, nullable=False)
    nombre_tercero = Column(String(120))
    cedula_tercero = Column(String(30), index=True)
    foto_cedula = Column(LargeBinary)
