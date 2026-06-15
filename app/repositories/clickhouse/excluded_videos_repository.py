from app.repositories.clickhouse.base import ClickHouseRepository
from app.schemas.clickhouse import ExcludedVideoRow


class ClickHouseExcludedVideosRepository(ClickHouseRepository):
    def insert_rows(self, table_name: str, rows: list[ExcludedVideoRow]) -> None:
        self.insert_model_rows(table_name, rows)
