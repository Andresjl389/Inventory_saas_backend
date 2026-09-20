"""Writing mapped rows into a company.

Every loader upserts: a row whose key already exists updates the record rather
than failing, so re-uploading a corrected file is a normal thing to do instead
of a cleanup exercise.

Problems a loader can anticipate (a missing category, an unknown warehouse)
become row issues and the import continues. Anything else -- a constraint the
application did not know to check -- aborts the whole load, with the row that
caused it named. Half an import is worse than none.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.application.imports.services.row_mapper import MappedRow, RowIssue
from app.application.inventory.services.stock_service import StockService
from app.domain.customers.entities.customer import Customer
from app.domain.customers.repositories.customer_repository import CustomerRepository
from app.domain.imports.entities.import_job import ImportStats
from app.domain.imports.schemas import ImportEntity
from app.domain.inventory.entities.stock_movement import MovementType, ReferenceType
from app.domain.inventory.entities.warehouse import Warehouse
from app.domain.inventory.repositories.stock_repository import StockRepository
from app.domain.inventory.repositories.warehouse_repository import WarehouseRepository
from app.domain.products.entities.category import Category
from app.domain.products.entities.product import Product
from app.domain.products.repositories.category_repository import CategoryRepository
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.shared.document import DocumentType
from app.domain.suppliers.entities.supplier import Supplier
from app.domain.suppliers.repositories.supplier_repository import SupplierRepository
from app.domain.tenants.tenant_context import TenantContext


@dataclass
class LoadResult:
    stats: ImportStats
    issues: list[RowIssue]


class _Loader:
    async def load(
        self, rows: list[MappedRow], *, tenant: TenantContext, options: dict
    ) -> LoadResult:
        raise NotImplementedError


class CategoryLoader(_Loader):
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def load(self, rows, *, tenant, options) -> LoadResult:
        stats, issues = ImportStats(total_rows=len(rows)), []
        for row in rows:
            name = str(row.get("name")).strip()
            existing = await self._categories.get_by_name(tenant.company_id, name)
            if existing is None:
                await self._categories.add(
                    Category(
                        company_id=tenant.company_id,
                        name=name,
                        description=row.get("description"),
                    )
                )
                stats.created += 1
            else:
                existing.description = row.get("description") or existing.description
                existing.touch()
                await self._categories.update(existing)
                stats.updated += 1
        return LoadResult(stats, issues)


class WarehouseLoader(_Loader):
    def __init__(self, warehouses: WarehouseRepository) -> None:
        self._warehouses = warehouses

    async def load(self, rows, *, tenant, options) -> LoadResult:
        stats, issues = ImportStats(total_rows=len(rows)), []
        for row in rows:
            name = str(row.get("name")).strip()
            existing = await self._warehouses.get_by_name(tenant.company_id, name)
            is_active = row.get("is_active")
            if existing is None:
                await self._warehouses.add(
                    Warehouse(
                        company_id=tenant.company_id,
                        name=name,
                        address=row.get("address"),
                        is_active=True if is_active is None else bool(is_active),
                    )
                )
                stats.created += 1
            else:
                existing.address = row.get("address") or existing.address
                if is_active is not None:
                    existing.is_active = bool(is_active)
                existing.touch()
                await self._warehouses.update(existing)
                stats.updated += 1
        return LoadResult(stats, issues)


class ProductLoader(_Loader):
    def __init__(self, products: ProductRepository, categories: CategoryRepository) -> None:
        self._products = products
        self._categories = categories

    async def load(self, rows, *, tenant, options) -> LoadResult:
        stats, issues = ImportStats(total_rows=len(rows)), []
        create_categories = bool(options.get("create_missing_categories", True))
        # Categories repeat constantly across a product file; one lookup each.
        resolved: dict[str, uuid.UUID | None] = {}
        seen_barcodes: set[str] = set()

        for row in rows:
            category_id = None
            category_name = (row.get("category") or "").strip() if row.get("category") else ""
            if category_name:
                key = category_name.lower()
                if key not in resolved:
                    resolved[key] = await self._resolve_category(
                        category_name, tenant=tenant, create=create_categories
                    )
                category_id = resolved[key]
                if category_id is None:
                    issues.append(
                        RowIssue(
                            row_number=row.row_number,
                            message=(
                                f"La categoría «{category_name}» no existe. "
                                "Impórtala primero o activa la creación automática."
                            ),
                            field_key="category",
                            value=category_name,
                        )
                    )
                    stats.skipped += 1
                    continue

            sku = str(row.get("sku")).strip().upper()
            existing = await self._products.get_by_sku(tenant.company_id, sku)

            barcode = await self._usable_barcode(
                row, sku=sku, tenant=tenant, seen=seen_barcodes, issues=issues
            )

            if existing is None:
                await self._products.add(
                    Product(
                        company_id=tenant.company_id,
                        sku=sku,
                        name=str(row.get("name")).strip(),
                        description=row.get("description"),
                        barcode=barcode,
                        category_id=category_id,
                        cost_price=row.get("cost_price") or Decimal("0"),
                        sale_price=row.get("sale_price") or Decimal("0"),
                        min_stock=row.get("min_stock") or Decimal("0"),
                        is_active=(
                            True if row.get("is_active") is None else bool(row.get("is_active"))
                        ),
                    )
                )
                stats.created += 1
            else:
                # Only columns present in the file overwrite; a template with
                # three columns must not blank out everything else.
                for key in ("name", "description"):
                    if row.get(key) is not None:
                        setattr(existing, key, row.get(key))
                if barcode is not None:
                    existing.barcode = barcode
                for key in ("cost_price", "sale_price", "min_stock"):
                    if row.get(key) is not None:
                        setattr(existing, key, row.get(key))
                if category_id is not None:
                    existing.category_id = category_id
                if row.get("is_active") is not None:
                    existing.is_active = bool(row.get("is_active"))
                existing.touch()
                await self._products.update(existing)
                stats.updated += 1

        return LoadResult(stats, issues)

    async def _usable_barcode(
        self, row, *, sku: str, tenant: TenantContext, seen: set[str], issues: list[RowIssue]
    ) -> str | None:
        """Barcodes are unique per company, and files repeat them constantly.

        A clash used to abort the whole import on a database constraint. The
        product is more valuable than its barcode, so the row loads without one
        and the conflict is reported -- the user fixes the codes afterwards
        instead of losing the catalogue.
        """
        raw = row.get("barcode")
        if raw in (None, ""):
            return None

        barcode = str(raw).strip()
        if barcode in seen:
            issues.append(
                RowIssue(
                    row_number=row.row_number,
                    message=(
                        f"El código de barras «{barcode}» se repite en el archivo; "
                        "el producto se importó sin código de barras."
                    ),
                    field_key="barcode",
                    value=barcode,
                )
            )
            return None

        clash = await self._products.get_by_barcode(tenant.company_id, barcode)
        if clash is not None and clash.sku != sku:
            issues.append(
                RowIssue(
                    row_number=row.row_number,
                    message=(
                        f"El código de barras «{barcode}» ya lo usa el producto "
                        f"{clash.sku}; el producto se importó sin código de barras."
                    ),
                    field_key="barcode",
                    value=barcode,
                )
            )
            return None

        seen.add(barcode)
        return barcode

    async def _resolve_category(
        self, name: str, *, tenant: TenantContext, create: bool
    ) -> uuid.UUID | None:
        found = await self._categories.get_by_name(tenant.company_id, name)
        if found is not None:
            return found.id
        if not create:
            return None
        created = await self._categories.add(Category(company_id=tenant.company_id, name=name))
        return created.id


class PartyLoader(_Loader):
    """Customers and suppliers: same shape, same upsert rule."""

    def __init__(self, repository: CustomerRepository | SupplierRepository, *, is_customer: bool):
        self._repository = repository
        self._is_customer = is_customer

    async def load(self, rows, *, tenant, options) -> LoadResult:
        stats, issues = ImportStats(total_rows=len(rows)), []
        for row in rows:
            document_type = row.get("document_type")
            document_number = row.get("document_number")
            existing = None
            if document_type and document_number:
                existing = await self._repository.get_by_document(
                    tenant.company_id, DocumentType(document_type), str(document_number)
                )

            fields = dict(
                name=str(row.get("name")).strip(),
                document_type=DocumentType(document_type) if document_type else None,
                document_number=str(document_number) if document_number else None,
                email=row.get("email"),
                phone=row.get("phone"),
                address=row.get("address"),
                is_active=True if row.get("is_active") is None else bool(row.get("is_active")),
            )

            if existing is None:
                entity = (
                    Customer(company_id=tenant.company_id, **fields)
                    if self._is_customer
                    else Supplier(company_id=tenant.company_id, **fields)
                )
                await self._repository.add(entity)
                stats.created += 1
            else:
                for key, value in fields.items():
                    if value is not None:
                        setattr(existing, key, value)
                existing.touch()
                await self._repository.update(existing)
                stats.updated += 1

        return LoadResult(stats, issues)


class StockLoader(_Loader):
    """Opening balances.

    Each row becomes an ADJUSTMENT movement rather than a direct write, so a
    company that imports its starting stock still has a ledger that explains
    every unit from day one.
    """

    def __init__(
        self,
        products: ProductRepository,
        warehouses: WarehouseRepository,
        stock: StockRepository,
        stock_service: StockService,
    ) -> None:
        self._products = products
        self._warehouses = warehouses
        self._stock = stock
        self._stock_service = stock_service

    async def load(self, rows, *, tenant, options) -> LoadResult:
        stats, issues = ImportStats(total_rows=len(rows)), []
        replace = bool(options.get("replace_existing", True))
        products: dict[str, uuid.UUID | None] = {}
        warehouses: dict[str, uuid.UUID | None] = {}

        for row in rows:
            sku = str(row.get("sku")).strip().upper()
            warehouse_name = str(row.get("warehouse")).strip()

            if sku not in products:
                found = await self._products.get_by_sku(tenant.company_id, sku)
                products[sku] = found.id if found else None
            if warehouse_name.lower() not in warehouses:
                found_warehouse = await self._warehouses.get_by_name(
                    tenant.company_id, warehouse_name
                )
                warehouses[warehouse_name.lower()] = found_warehouse.id if found_warehouse else None

            product_id = products[sku]
            warehouse_id = warehouses[warehouse_name.lower()]

            if product_id is None or warehouse_id is None:
                missing = "producto" if product_id is None else "bodega"
                issues.append(
                    RowIssue(
                        row_number=row.row_number,
                        message=(
                            f"No existe la {missing} «"
                            f"{sku if product_id is None else warehouse_name}». "
                            "Impórtala antes del stock."
                        ),
                        field_key="sku" if product_id is None else "warehouse",
                    )
                )
                stats.skipped += 1
                continue

            target = row.get("quantity") or Decimal("0")
            delta = target
            if replace:
                current = await self._stock.get(tenant.company_id, product_id, warehouse_id)
                delta = target - (current.quantity if current else Decimal("0"))

            if delta == 0:
                stats.skipped += 1
                continue

            await self._stock_service.apply_movement(
                company_id=tenant.company_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                delta=delta,
                movement_type=MovementType.ADJUSTMENT,
                reference_type=ReferenceType.MANUAL,
                notes=f"Carga inicial (fila {row.row_number})",
                created_by=tenant.user_id,
                # An opening balance is allowed to be whatever the count says.
                allow_negative=True,
            )
            stats.created += 1

        return LoadResult(stats, issues)


def loader_for(entity: ImportEntity, *, repositories: dict) -> _Loader:
    """Wire the loader an entity needs from the repositories on offer."""
    if entity is ImportEntity.CATEGORIES:
        return CategoryLoader(repositories["categories"])
    if entity is ImportEntity.WAREHOUSES:
        return WarehouseLoader(repositories["warehouses"])
    if entity is ImportEntity.PRODUCTS:
        return ProductLoader(repositories["products"], repositories["categories"])
    if entity is ImportEntity.CUSTOMERS:
        return PartyLoader(repositories["customers"], is_customer=True)
    if entity is ImportEntity.SUPPLIERS:
        return PartyLoader(repositories["suppliers"], is_customer=False)
    if entity is ImportEntity.STOCK:
        return StockLoader(
            repositories["products"],
            repositories["warehouses"],
            repositories["stock"],
            repositories["stock_service"],
        )
    raise ValueError(f"No loader for {entity}")
