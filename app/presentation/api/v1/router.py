from fastapi import APIRouter

from app.presentation.api.v1 import (
    auth,
    categories,
    companies,
    customers,
    inventory,
    products,
    purchases,
    sales,
    suppliers,
    warehouses,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(warehouses.router)
api_router.include_router(inventory.router)
api_router.include_router(customers.router)
api_router.include_router(suppliers.router)
api_router.include_router(sales.router)
api_router.include_router(purchases.router)
