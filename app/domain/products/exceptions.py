from app.shared.exceptions import BusinessRuleError, ConflictError, NotFoundError


class ProductNotFoundError(NotFoundError):
    code = "PRODUCT_NOT_FOUND"
    message = "Product not found"


class CategoryNotFoundError(NotFoundError):
    code = "CATEGORY_NOT_FOUND"
    message = "Category not found"


class DuplicateSkuError(ConflictError):
    code = "DUPLICATE_SKU"
    message = "A product with that SKU already exists in this company"


class DuplicateBarcodeError(ConflictError):
    code = "DUPLICATE_BARCODE"
    message = "A product with that barcode already exists in this company"


class DuplicateCategoryNameError(ConflictError):
    code = "DUPLICATE_CATEGORY_NAME"
    message = "A category with that name already exists in this company"


class InvalidProductPriceError(BusinessRuleError):
    code = "INVALID_PRODUCT_PRICE"
    message = "Invalid product price"
