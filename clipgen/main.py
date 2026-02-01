"""Main entry point for ClipGen application."""

import sys
import time
import traceback


def exception_hook(exctype, value, tb):
    """Handle uncaught exceptions by logging to file."""
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        f.write(f"Exception: {exctype.__name__}: {value}\n")
        f.write("".join(traceback.format_tb(tb)))

    # Call default hook
    sys.__excepthook__(exctype, value, tb)


def main():
    """Main entry point."""
    # Install exception hook
    sys.excepthook = exception_hook

    try:
        from clipgen.app import ClipGenApp

        app = ClipGenApp()
        sys.exit(app.run())

    except Exception as e:
        print(f"Failed to start: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
