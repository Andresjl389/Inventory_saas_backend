import uuid

from app.application.suppliers.dto.supplier import (
    CreateSupplierCommand,
    ListSuppliersQuery,
    SupplierDTO,
    SupplierPageDTO,
    UpdateSupplierCommand,
)
from app.domain.shared.pagination import Page
from app.domain.suppliers.entities.supplier import Supplier
from app.domain.suppliers.exceptions import (
    DuplicateSupplierDocumentError,
    SupplierNotFoundError,
)
from app.domain.suppliers.repositories.supplier_repository import SupplierRepository
from app.domain.tenants.tenant_context import TenantContext


class CreateSupplierUseCase:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def execute(
        self, command: CreateSupplierCommand, *, tenant: TenantContext
    ) -> SupplierDTO:
        if command.document_type and command.document_number:
            existing = await self._suppliers.get_by_document(
                tenant.company_id, command.document_type, command.document_number
            )
            if existing is not None:
                raise DuplicateSupplierDocumentError()

        supplier = await self._suppliers.add(
            Supplier(
                company_id=tenant.company_id,
                name=command.name.strip(),
                document_type=command.document_type,
                document_number=command.document_number,
                email=str(command.email) if command.email else None,
                phone=command.phone,
                address=command.address,
            )
        )
        return SupplierDTO.model_validate(supplier, from_attributes=True)


class GetSupplierUseCase:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def execute(self, supplier_id: uuid.UUID, *, tenant: TenantContext) -> SupplierDTO:
        supplier = await self._suppliers.get_by_id(tenant.company_id, supplier_id)
        if supplier is None:
            raise SupplierNotFoundError()
        return SupplierDTO.model_validate(supplier, from_attributes=True)


class ListSuppliersUseCase:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def execute(self, query: ListSuppliersQuery, *, tenant: TenantContext) -> SupplierPageDTO:
        result = await self._suppliers.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            search=query.search,
            is_active=query.is_active,
        )
        return SupplierPageDTO(
            items=[SupplierDTO.model_validate(row, from_attributes=True) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class UpdateSupplierUseCase:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def execute(
        self, supplier_id: uuid.UUID, command: UpdateSupplierCommand, *, tenant: TenantContext
    ) -> SupplierDTO:
        supplier = await self._suppliers.get_by_id(tenant.company_id, supplier_id)
        if supplier is None:
            raise SupplierNotFoundError()

        document_type = command.document_type or supplier.document_type
        document_number = command.document_number or supplier.document_number
        if (
            (document_type, document_number)
            != (
                supplier.document_type,
                supplier.document_number,
            )
            and document_type
            and document_number
        ):
            clash = await self._suppliers.get_by_document(
                tenant.company_id, document_type, document_number
            )
            if clash is not None and clash.id != supplier.id:
                raise DuplicateSupplierDocumentError()

        if command.name is not None:
            supplier.name = command.name.strip()
        supplier.document_type = document_type
        supplier.document_number = document_number
        if command.email is not None:
            supplier.email = str(command.email)
        if command.phone is not None:
            supplier.phone = command.phone
        if command.address is not None:
            supplier.address = command.address
        if command.is_active is not None:
            supplier.activate() if command.is_active else supplier.deactivate()
        supplier.touch()

        updated = await self._suppliers.update(supplier)
        return SupplierDTO.model_validate(updated, from_attributes=True)


class DeactivateSupplierUseCase:
    """Soft delete: purchases keep pointing at the supplier."""

    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def execute(self, supplier_id: uuid.UUID, *, tenant: TenantContext) -> SupplierDTO:
        supplier = await self._suppliers.get_by_id(tenant.company_id, supplier_id)
        if supplier is None:
            raise SupplierNotFoundError()
        supplier.deactivate()
        updated = await self._suppliers.update(supplier)
        return SupplierDTO.model_validate(updated, from_attributes=True)
