"""Run only the dashboard website (no MCP):  python -m fb_ads_mcp.dashboard"""

import os

import uvicorn

from . import create_dashboard_app


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Dashboard: http://localhost:{port}/dashboard")
    uvicorn.run(create_dashboard_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
