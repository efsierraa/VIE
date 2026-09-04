from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils import utcnow

ROLES = ("admin", "guarda", "residente")
VISITOR_ROLES = ("visitante", "domiciliario")
VISIT_STATUS = ("pendiente", "dentro", "finalizada", "cancelada")
VALID_HOURS = (1, 2, 4, 8, 12, 24, 48, 168, 360, 720)  # hasta 30 días: visitas extendidas
PACKAGE_STATUS = ("en_porteria", "entregado", "confirmado", "disputa", "cancelado")
DIAS_FOTO_ENTREGADA = 30
MINUTOS_GRACIA_EDICION = 60  # el guarda puede editar lo suyo durante 1 hora


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
    visitor_name = Column(String(120), nullable=False)  # "Nombres Apellidos" para mostrar y buscar
    visitor_nombres = Column(String(80))  # dos campos claros: nombres y apellidos por separado
    visitor_apellidos = Column(String(80))
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
    salida_auto = Column(Boolean, default=False, nullable=False)  # salida marcada al expirar el QR
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

    # Paquete para alguien sin cuenta: se registra con el nombre del destinatario
    # (viene en la etiqueta). Al reclamar, se coteja el nombre con la cédula física
    # y se guarda el número de cédula de quien reclamó como evidencia.
    tercero = Column(Boolean, default=False, nullable=False)
    nombre_tercero = Column(String(120))  # "Nombres Apellidos" del destinatario de la etiqueta
    tercero_nombres = Column(String(80))
    tercero_apellidos = Column(String(80))
    cedula_tercero = Column(String(30), index=True)  # cédula de quien reclamó, al entregar

    # Todo paquete nace con destino asociado: se copia del perfil del residente
    # o se digita de la etiqueta (terceros). Se actualiza al asignar un residente.
    tower = Column(String(10))
    apartment = Column(String(10))

    # Resolución de disputa a dos partes: portería (guarda o admin) y residente.
    # El paquete pasa a confirmado solo cuando ambas aceptan.
    resuelta_porteria = Column(Boolean, default=False, nullable=False)
    resuelta_residente = Column(Boolean, default=False, nullable=False)
    resuelta_at = Column(DateTime)


class EditLog(Base):
    """Control de ediciones: qué cambió, quién y cuándo, en datos manuales."""

    __tablename__ = "edit_logs"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(10), nullable=False)  # visita | paquete
    entity_uuid = Column(String(36), nullable=False, index=True)
    editor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    creado_at = Column(DateTime, default=utcnow, nullable=False)
    cambios = Column(Text, nullable=False)  # resumen legible: "asunto: 'x' → 'y'"

    editor = relationship("User")
