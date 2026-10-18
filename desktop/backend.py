"""Frozen executable entrypoint; jobs reuse the backend runtime, not system Python."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--job":
        del sys.argv[1]
        from app.local_jobs import main
    elif len(sys.argv) > 1 and sys.argv[1] == "--check-package":
        del sys.argv[1]
        from package_probe import main
    else:
        from server import main
    main()
