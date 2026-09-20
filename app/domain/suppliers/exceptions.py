from app.shared.exceptions import BusinessRuleError, ConflictError, NotFoundError


class SupplierNotFoundError(NotFoundError):
    code = "SUPPLIER_NOT_FOUND"
    message = "Supplier not found"


class DuplicateSupplierDocumentError(ConflictError):
    code = "DUPLICATE_SUPPLIER_DOCUMENT"
    message = "A supplier with that document already exists in this company"


class InactiveSupplierError(BusinessRuleError):
    code = "INACTIVE_SUPPLIER"
    message = "That supplier is not active"
