from app.shared.exceptions import BusinessRuleError, ConflictError, NotFoundError


class CustomerNotFoundError(NotFoundError):
    code = "CUSTOMER_NOT_FOUND"
    message = "Customer not found"


class DuplicateCustomerDocumentError(ConflictError):
    code = "DUPLICATE_CUSTOMER_DOCUMENT"
    message = "A customer with that document already exists in this company"


class InactiveCustomerError(BusinessRuleError):
    code = "INACTIVE_CUSTOMER"
    message = "That customer is not active"
