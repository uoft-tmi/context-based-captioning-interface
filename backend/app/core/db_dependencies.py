from typing import Annotated

from asyncpg import Pool
from fastapi import Depends

from app.core.pool import get_pool


DBPool = Annotated[Pool, Depends(get_pool)]