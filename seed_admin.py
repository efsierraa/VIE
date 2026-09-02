"""Crea la primera cuenta de administración.

Ejemplo:
    python seed_admin.py --usuario admin --clave una-clave-segura --nombres "María" --apellidos "Pérez"
"""
import argparse

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import User


def main():
    parser = argparse.ArgumentParser(description="Crear la primera cuenta de administración de VIE")
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--clave", required=True)
    parser.add_argument("--nombres", required=True)
    parser.add_argument("--apellidos", required=True)
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == args.usuario.lower()).first()
        if existing:
            print(f"El usuario '{args.usuario}' ya existe.")
            return
        db.add(
            User(
                username=args.usuario.lower(),
                password_hash=hash_password(args.clave),
                nombres=args.nombres,
                apellidos=args.apellidos,
                role="admin",
            )
        )
        db.commit()
        print(f"Cuenta de administración '{args.usuario.lower()}' creada. Ingresa en /login.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
