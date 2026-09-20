from app.shared.exceptions import BusinessRuleError, ConflictError, NotFoundError


class PlanNotFoundError(NotFoundError):
    code = "PLAN_NOT_FOUND"
    message = "Plan not found"


class DuplicatePlanCodeError(ConflictError):
    code = "DUPLICATE_PLAN_CODE"
    message = "A plan with that code already exists"


class SubscriptionNotFoundError(NotFoundError):
    code = "SUBSCRIPTION_NOT_FOUND"
    message = "This company has no subscription"


class PlanLimitReachedError(BusinessRuleError):
    code = "PLAN_LIMIT_REACHED"
    message = "Your plan's limit for this resource has been reached"
