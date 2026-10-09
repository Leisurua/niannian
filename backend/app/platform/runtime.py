import asyncio
import sys


def configure_event_loop() -> None:
    # psycopg 3's async connection requires a selector on Windows / Python 3.12.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
