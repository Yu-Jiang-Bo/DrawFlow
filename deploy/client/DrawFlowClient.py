"""PyInstaller entrypoint for DrawFlowClient.exe."""

from src.service.local_gateway import main


if __name__ == "__main__":
    raise SystemExit(main())
