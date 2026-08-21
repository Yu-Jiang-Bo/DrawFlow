"""PyInstaller entrypoint for the persistent DrawFlow launcher."""

from src.launcher.main import main


if __name__ == "__main__":
    raise SystemExit(main())
