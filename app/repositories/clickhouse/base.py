from app.repositories.base import BaseRepository


class ClickHouseRepository(BaseRepository):
    def __init__(self, client, database: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.client = client
        self.database = database

    def table(self, table_name: str) -> str:
        return f"{self.database}.{table_name}"

