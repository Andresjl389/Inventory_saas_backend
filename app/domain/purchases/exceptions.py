from app.shared.exceptions import BusinessRuleError, NotFoundError


class PurchaseNotFoundError(NotFoundError):
    code = "PURCHASE_NOT_FOUND"
    message = "Purchase not found"


class EmptyPurchaseError(BusinessRuleError):
    code = "EMPTY_PURCHASE"
    message = "A purchase needs at least one item"


class InvalidPurchaseTransitionError(BusinessRuleError):
    code = "INVALID_PURCHASE_TRANSITION"
    message = "That purchase cannot change to the requested status"


class InvalidPurchaseItemError(BusinessRuleError):
    code = "INVALID_PURCHASE_ITEM"
    message = "Invalid purchase item"
