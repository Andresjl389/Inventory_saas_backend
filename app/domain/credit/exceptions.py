from app.shared.exceptions import BusinessRuleError, NotFoundError


class InvalidAccountEntryError(BusinessRuleError):
    code = "INVALID_ACCOUNT_ENTRY"
    message = "Movimiento de cuenta inválido"


class CreditSaleNeedsCustomerError(BusinessRuleError):
    code = "CREDIT_SALE_NEEDS_CUSTOMER"
    message = "Una venta fiada necesita un cliente: no se le fía a nadie"


class OverpaidSaleError(BusinessRuleError):
    code = "OVERPAID_SALE"
    message = "Lo pagado no puede superar el total de la venta"


class CreditLimitExceededError(BusinessRuleError):
    code = "CREDIT_LIMIT_EXCEEDED"
    message = "Esta venta supera el cupo de fiado del cliente"


class InvalidPaymentError(BusinessRuleError):
    code = "INVALID_PAYMENT"
    message = "El abono debe ser mayor que cero"


class PaymentExceedsBalanceError(BusinessRuleError):
    code = "PAYMENT_EXCEEDS_BALANCE"
    message = "El abono es mayor que lo que debe el cliente"


class AccountNotFoundError(NotFoundError):
    code = "ACCOUNT_NOT_FOUND"
    message = "Ese cliente no tiene cuenta de fiado"
