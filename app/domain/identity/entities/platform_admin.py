"""Platform administration.

`User.is_superuser` marks an operator of the SaaS itself rather than a member
of any tenant. A platform admin is not, and never becomes, a company member:
they create companies, assign the first owner, manage plans and roles, and read
the audit log. To touch a company's business data they must step *into* that
company (X-Company-ID), which puts them on the same single-tenant RLS path as
everybody else -- so there is no request that can read two tenants at once.
"""

from app.domain.identity.entities.user import User
from app.shared.exceptions import ForbiddenError


class NotAPlatformAdminError(ForbiddenError):
    code = "NOT_PLATFORM_ADMIN"
    message = "This endpoint is restricted to platform administrators"


def require_platform_admin(user: User) -> User:
    if not user.is_superuser:
        raise NotAPlatformAdminError()
    return user
