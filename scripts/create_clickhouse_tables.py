from pathlib import Path

from app.clients.clickhouse import create_clickhouse_client
from app.config.settings import Settings


def main() -> None:
    settings = Settings()
    client = create_clickhouse_client(settings)
    for ddl_file in sorted(Path("db/clickhouse").glob("*.sql")):
        client.command(ddl_file.read_text(encoding="utf-8"))
        print(f"applied {ddl_file}")


if __name__ == "__main__":
    main()

