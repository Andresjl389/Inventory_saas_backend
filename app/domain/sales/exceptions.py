from app.shared.exceptions import BusinessRuleError, NotFoundError


class SaleNotFoundError(NotFoundError):
    code = "SALE_NOT_FOUND"
    message = "Sale not found"


class EmptySaleError(BusinessRuleError):
    code = "EMPTY_SALE"
    message = "A sale needs at least one item"


class InvalidSaleTransitionError(BusinessRuleError):
    code = "INVALID_SALE_TRANSITION"
    message = "That sale cannot change to the requested status"


class InvalidSaleItemError(BusinessRuleError):
    code = "INVALID_SALE_ITEM"
    message = "Invalid sale item"
