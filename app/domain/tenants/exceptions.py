from app.shared.exceptions import ConflictError, ForbiddenError, NotFoundError


class CompanyNotFoundError(NotFoundError):
    code = "COMPANY_NOT_FOUND"
    message = "Company not found"


class InvalidCompanyError(ForbiddenError):
    code = "INVALID_COMPANY"
    message = "The selected company is not available"


class MembershipNotFoundError(ForbiddenError):
    code = "INVALID_MEMBERSHIP"
    message = "You do not have access to this company"


class MembershipAlreadyExistsError(ConflictError):
    code = "MEMBERSHIP_ALREADY_EXISTS"
    message = "That user already belongs to this company"


class InsufficientRoleError(ForbiddenError):
    code = "INSUFFICIENT_ROLE"
    message = "Your role does not allow this operation"
