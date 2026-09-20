import uuid

from app.application.customers.dto.customer import (
    CreateCustomerCommand,
    CustomerDTO,
    CustomerPageDTO,
    ListCustomersQuery,
    UpdateCustomerCommand,
)
from app.domain.customers.entities.customer import Customer
from app.domain.customers.exceptions import (
    CustomerNotFoundError,
    DuplicateCustomerDocumentError,
)
from app.domain.customers.repositories.customer_repository import CustomerRepository
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext


class CreateCustomerUseCase:
    def __init__(self, customers: CustomerRepository) -> None:
        self._customers = customers

    async def execute(
        self, command: CreateCustomerCommand, *, tenant: TenantContext
    ) -> CustomerDTO:
        if command.document_type and command.document_number:
            existing = await self._customers.get_by_document(
                tenant.company_id, command.document_type, command.document_number
            )
            if existing is not None:
                raise DuplicateCustomerDocumentError()

        customer = await self._customers.add(
            Customer(
                company_id=tenant.company_id,
                name=command.name.strip(),
                document_type=command.document_type,
                document_number=command.document_number,
                email=str(command.email) if command.email else None,
                phone=command.phone,
                address=command.address,
            )
        )
        return CustomerDTO.model_validate(customer, from_attributes=True)


class GetCustomerUseCase:
    def __init__(self, customers: CustomerRepository) -> None:
        self._customers = customers

    async def execute(self, customer_id: uuid.UUID, *, tenant: TenantContext) -> CustomerDTO:
        customer = await self._customers.get_by_id(tenant.company_id, customer_id)
        if customer is None:
            raise CustomerNotFoundError()
        return CustomerDTO.model_validate(customer, from_attributes=True)


class ListCustomersUseCase:
    def __init__(self, customers: CustomerRepository) -> None:
        self._customers = customers

    async def execute(self, query: ListCustomersQuery, *, tenant: TenantContext) -> CustomerPageDTO:
        result = await self._customers.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            search=query.search,
            is_active=query.is_active,
        )
        return CustomerPageDTO(
            items=[CustomerDTO.model_validate(row, from_attributes=True) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class UpdateCustomerUseCase:
    def __init__(self, customers: CustomerRepository) -> None:
        self._customers = customers

    async def execute(
        self, customer_id: uuid.UUID, command: UpdateCustomerCommand, *, tenant: TenantContext
    ) -> CustomerDTO:
        customer = await self._customers.get_by_id(tenant.company_id, customer_id)
        if customer is None:
            raise CustomerNotFoundError()

        document_type = command.document_type or customer.document_type
        document_number = command.document_number or customer.document_number
        if (
            (document_type, document_number)
            != (
                customer.document_type,
                customer.document_number,
            )
            and document_type
            and document_number
        ):
            clash = await self._customers.get_by_document(
                tenant.company_id, document_type, document_number
            )
            if clash is not None and clash.id != customer.id:
                raise DuplicateCustomerDocumentError()

        if command.name is not None:
            customer.name = command.name.strip()
        customer.document_type = document_type
        customer.document_number = document_number
        if command.email is not None:
            customer.email = str(command.email)
        if command.phone is not None:
            customer.phone = command.phone
        if command.address is not None:
            customer.address = command.address
        if command.is_active is not None:
            customer.activate() if command.is_active else customer.deactivate()
        customer.touch()

        updated = await self._customers.update(customer)
        return CustomerDTO.model_validate(updated, from_attributes=True)


class DeactivateCustomerUseCase:
    """Soft delete: sales keep pointing at the customer."""

    def __init__(self, customers: CustomerRepository) -> None:
        self._customers = customers

    async def execute(self, customer_id: uuid.UUID, *, tenant: TenantContext) -> CustomerDTO:
        customer = await self._customers.get_by_id(tenant.company_id, customer_id)
        if customer is None:
            raise CustomerNotFoundError()
        customer.deactivate()
        updated = await self._customers.update(customer)
        return CustomerDTO.model_validate(updated, from_attributes=True)
