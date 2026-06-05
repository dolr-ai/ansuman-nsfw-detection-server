from app.repositories.base import BaseRepository


class PostgresRepository(BaseRepository):
    def __init__(self, session) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.session = session

    async def execute(self, statement):  # type: ignore[no-untyped-def]
        return await self.session.execute(statement)
