from app.repositories.clickhouse.base import ClickHouseRepository
from app.schemas.legacy import LegacyNsfwAggRow


class ClickHouseLegacyNsfwAggRepository(ClickHouseRepository):
    def insert_rows(self, table_name: str, rows: list[LegacyNsfwAggRow]) -> None:
        if not rows:
            return
        payload = [row.model_dump(mode="json") for row in rows]
        self.client.insert(self.table(table_name), payload)

