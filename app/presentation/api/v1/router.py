from fastapi import APIRouter

from app.presentation.api.v1 import auth, categories, companies, products

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
