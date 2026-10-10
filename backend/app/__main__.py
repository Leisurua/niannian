"""Portable API entry point: run `python -m app` from backend/."""

import argparse

from app.platform.runtime import configure_event_loop


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    configure_event_loop()
    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload, log_config=None)


if __name__ == "__main__":
    main()
