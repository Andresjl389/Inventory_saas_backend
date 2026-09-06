"""Composition root for repositories.

Use cases depend on the domain Protocols; the concrete SQLAlchemy classes are
only ever named here.
"""

from typing import Annotated

from fastapi import Depends

from app.infrastructure.database.repositories.category_repository import (
    SqlAlchemyCategoryRepository,
)
from app.infrastructure.database.repositories.company_member_repository import (
    SqlAlchemyCompanyMemberRepository,
)
from app.infrastructure.database.repositories.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.repositories.product_repository import SqlAlchemyProductRepository
from app.infrastructure.database.repositories.tenant_scope import SqlAlchemyTenantScope
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.presentation.api.dependencies.database import SessionDep


def get_user_repository(session: SessionDep) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(session)


def get_company_repository(session: SessionDep) -> SqlAlchemyCompanyRepository:
    return SqlAlchemyCompanyRepository(session)


def get_company_member_repository(session: SessionDep) -> SqlAlchemyCompanyMemberRepository:
    return SqlAlchemyCompanyMemberRepository(session)


def get_category_repository(session: SessionDep) -> SqlAlchemyCategoryRepository:
    return SqlAlchemyCategoryRepository(session)


def get_product_repository(session: SessionDep) -> SqlAlchemyProductRepository:
    return SqlAlchemyProductRepository(session)


def get_tenant_scope(session: SessionDep) -> SqlAlchemyTenantScope:
    return SqlAlchemyTenantScope(session)


UserRepoDep = Annotated[SqlAlchemyUserRepository, Depends(get_user_repository)]
CompanyRepoDep = Annotated[SqlAlchemyCompanyRepository, Depends(get_company_repository)]
MemberRepoDep = Annotated[SqlAlchemyCompanyMemberRepository, Depends(get_company_member_repository)]
CategoryRepoDep = Annotated[SqlAlchemyCategoryRepository, Depends(get_category_repository)]
ProductRepoDep = Annotated[SqlAlchemyProductRepository, Depends(get_product_repository)]
TenantScopeDep = Annotated[SqlAlchemyTenantScope, Depends(get_tenant_scope)]
