import asyncio
import logging


async def run() -> None:
    logging.getLogger(__name__).info("video worker skeleton started")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

