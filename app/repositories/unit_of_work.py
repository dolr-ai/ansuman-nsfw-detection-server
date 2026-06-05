from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class UnitOfWork:
    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[object]:
        async with self._session_factory() as session:
            async with session.begin():
                yield session

