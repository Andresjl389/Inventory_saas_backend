from fastapi import APIRouter

from app.presentation.api.v1 import (
    admin,
    auth,
    categories,
    companies,
    customers,
    files,
    inventory,
    notifications,
    products,
    purchases,
    reports,
    roles,
    sales,
    suppliers,
    warehouses,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(roles.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(warehouses.router)
api_router.include_router(inventory.router)
api_router.include_router(customers.router)
api_router.include_router(suppliers.router)
api_router.include_router(sales.router)
api_router.include_router(purchases.router)
api_router.include_router(reports.router)
api_router.include_router(notifications.router)
api_router.include_router(files.router)
api_router.include_router(admin.router)
