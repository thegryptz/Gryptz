#!/usr/bin/env python3
import asyncio
import logging

from gryptz.bot import run_bot
from gryptz.scanner_loop import scan_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    await asyncio.gather(
        scan_loop(),
        run_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
