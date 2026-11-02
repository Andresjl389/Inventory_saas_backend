"""Comprobar que lo que la revisión menciona existe y está activo.

La compra que se crea al confirmar valida lo mismo, pero fallar ahí daría un
error a mitad de camino sobre una factura que el usuario creía lista. Es mejor
decirlo cuando se guarda la decisión.
"""

import uuid

from app.domain.inventory.exceptions import InactiveWarehouseError, WarehouseNotFoundError
from app.domain.inventory.repositories.warehouse_repository import WarehouseRepository
from app.domain.products.exceptions import ProductNotFoundError
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.suppliers.exceptions import InactiveSupplierError, SupplierNotFoundError
from app.domain.suppliers.repositories.supplier_repository import SupplierRepository


class ReferenceCheck:
    def __init__(
        self,
        warehouses: WarehouseRepository,
        suppliers: SupplierRepository,
        products: ProductRepository,
    ) -> None:
        self._warehouses = warehouses
        self._suppliers = suppliers
        self._products = products

    async def assert_warehouse(self, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> None:
        warehouse = await self._warehouses.get_by_id(company_id, warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        if not warehouse.is_active:
            raise InactiveWarehouseError(f"La bodega '{warehouse.name}' no está activa")

    async def assert_supplier(self, company_id: uuid.UUID, supplier_id: uuid.UUID) -> None:
        supplier = await self._suppliers.get_by_id(company_id, supplier_id)
        if supplier is None:
            raise SupplierNotFoundError()
        if not supplier.is_active:
            raise InactiveSupplierError(f"El proveedor '{supplier.name}' no está activo")

    async def assert_product(self, company_id: uuid.UUID, product_id: uuid.UUID) -> None:
        product = await self._products.get_by_id(company_id, product_id)
        if product is None:
            raise ProductNotFoundError(
                "Producto no encontrado", details={"product_id": str(product_id)}
            )
