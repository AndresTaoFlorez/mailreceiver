"""
Agent launcher — forces ProactorEventLoop for Playwright on Windows.
Usage: python -m agent --host localhost --port 8001 --reload
"""

import asyncio
import sys

import uvicorn

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    uvicorn.run(
        "agent.core:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="none",
    )
