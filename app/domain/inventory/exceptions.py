from app.shared.exceptions import BusinessRuleError, ConflictError, NotFoundError


class WarehouseNotFoundError(NotFoundError):
    code = "WAREHOUSE_NOT_FOUND"
    message = "Warehouse not found"


class DuplicateWarehouseNameError(ConflictError):
    code = "DUPLICATE_WAREHOUSE_NAME"
    message = "A warehouse with that name already exists in this company"


class InactiveWarehouseError(BusinessRuleError):
    code = "INACTIVE_WAREHOUSE"
    message = "That warehouse is not active"


class InsufficientStockError(BusinessRuleError):
    code = "INSUFFICIENT_STOCK"
    message = "Insufficient stock"


class InvalidMovementError(BusinessRuleError):
    code = "INVALID_STOCK_MOVEMENT"
    message = "Invalid stock movement"


class SameWarehouseTransferError(BusinessRuleError):
    code = "SAME_WAREHOUSE_TRANSFER"
    message = "Source and destination warehouses must be different"
