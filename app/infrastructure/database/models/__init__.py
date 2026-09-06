"""Importing this package registers every model on `Base.metadata`.

Alembic's env.py relies on it for autogenerate.
"""

from app.infrastructure.database.models.company import CompanyMemberModel, CompanyModel
from app.infrastructure.database.models.product import CategoryModel, ProductModel
from app.infrastructure.database.models.user import UserModel

__all__ = [
    "CategoryModel",
    "CompanyMemberModel",
    "CompanyModel",
    "ProductModel",
    "UserModel",
]
