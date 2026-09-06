from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import create_session

SessionDep = Annotated[AsyncSession, Depends(create_session)]
