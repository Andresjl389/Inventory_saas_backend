"""Port for a nested transaction.

An import needs to answer "what would this do?" without doing it. Running the
real loader inside a savepoint and rolling it back gives an answer that
includes database constraints -- unique SKUs, check constraints, foreign keys
-- which a separate validation pass would have to re-implement and would
eventually get wrong.
"""

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class UnitOfWork(Protocol):
    def savepoint(self, *, commit: bool) -> AbstractAsyncContextManager[None]:
        """Run a block inside a savepoint.

        `commit=False` rolls it back whatever happens, which is what a dry run
        is. Exceptions always roll back, committed or not.
        """
        ...
