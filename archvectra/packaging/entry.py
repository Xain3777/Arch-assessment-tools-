"""PyInstaller entry point: builds archvectra.exe (no Python needed on the target PC)."""

from archvectra.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
