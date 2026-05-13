"""
Script para crear el primer usuario administrador.
Uso: python crear_admin.py

Requiere que la app esté configurada (DATABASE_URL o SQLite local).
"""
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


async def main():
    from app.db import init_db, crear_usuario, email_existe
    from app.auth import hash_password

    await init_db()

    print("\n=== Crear Administrador GLOSA ===\n")
    email = input("Email del admin: ").strip().lower()
    nombre = input("Nombre completo: ").strip()
    password = input("Contraseña: ").strip()

    if not email or not nombre or not password:
        print("❌ Todos los campos son requeridos.")
        return

    if await email_existe(email):
        print(f"❌ Ya existe un usuario con el email {email}")
        return

    hashed = hash_password(password)
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    user_id = await crear_usuario(email, nombre, hashed, "admin", fecha)
    print(f"\n✅ Administrador creado exitosamente (ID: {user_id})")
    print(f"   Email: {email}")
    print(f"   Nombre: {nombre}")
    print(f"   Rol: admin\n")


if __name__ == "__main__":
    asyncio.run(main())
