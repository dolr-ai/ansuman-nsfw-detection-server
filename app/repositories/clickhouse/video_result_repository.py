from app.repositories.clickhouse.base import ClickHouseRepository
from app.schemas.clickhouse import VideoNsfwDetectionRow


class ClickHouseVideoResultRepository(ClickHouseRepository):
    def insert_rows(self, table_name: str, rows: list[VideoNsfwDetectionRow]) -> None:
        if not rows:
            return
        payload = [row.model_dump(mode="json") for row in rows]
        self.client.insert(self.table(table_name), payload)

