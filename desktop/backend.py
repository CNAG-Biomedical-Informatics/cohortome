"""Frozen executable entrypoint; jobs reuse the backend runtime, not system Python."""
import sys

if __name__ == "__main__":
    # Scientific dependencies can spawn Python helpers. Divert frozen children
    # before our CLI parser/server starts, as in Pheno-Ranker's desktop worker.
    from multiprocessing import freeze_support
    freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--job":
        del sys.argv[1]
        from app.local_jobs import main
    elif len(sys.argv) > 1 and sys.argv[1] == "--check-package":
        del sys.argv[1]
        from package_probe import main
    else:
        from server import main
    main()
