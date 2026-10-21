"""Exercise a real packaged worker without requiring external analysis runtimes."""
import time
from server import configure_environment, runtime_directory


def main():
    runtime = runtime_directory()
    configure_environment(runtime)
    from app import jobs, local_jobs
    children = []
    launch = local_jobs.subprocess.Popen

    def tracked_launch(*args, **kwargs):
        child = launch(*args, **kwargs)
        children.append(child)
        return child

    local_jobs.subprocess.Popen = tracked_launch
    local_jobs.start()
    try:
        for _ in range(2):
            item = jobs.create_job_record(job_type="analysis", user_id="local",
                                         data={"catalog_item_id": "missing-package-probe"})
            local_jobs.enqueue("analysis", item["job_id"], "local", 20)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                record = jobs._load_job_record_raw(item["job_id"], "local")
                if record["status"] == "failed" and children and children[-1].poll() is not None:
                    break
                time.sleep(.05)
            assert "Unknown analysis catalog item" in record.get("error", ""), record.get("error")
            assert children[-1].returncode == 0, "Packaged worker did not exit cleanly"
            assert (jobs.job_dir(item["job_id"], "local") / "error.txt").is_file()
        print("PASS: packaged job subprocess, persisted failure, queue reuse, clean child exit")
    finally:
        local_jobs.stop()
        local_jobs.subprocess.Popen = launch
    from app.r_runtime import rscript_binary
    if rscript_binary():
        from server import ROOT
        from r_package_probe import check
        check(ROOT, runtime)
    import os
    import sys
    from pathlib import Path
    tools = Path(sys.executable).resolve().parent / "runtimes/perl"
    if (tools / "runtime-manifest.json").is_file():
        from preparation_probe import check
        clean = {"PATH": "", "HOME": str(runtime), "LANG": "C.UTF-8"}
        if os.name == "nt":
            clean.update({key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ})
            clean.update(USERPROFILE=str(runtime), TEMP=str(runtime), TMP=str(runtime),
                         PATH=str(tools / "perl/bin"))
        check(tools, runtime / "preparation-probe", clean)
        print("PASS: packaged CSV-to-BFF mapping and ClarID round trips")


if __name__ == "__main__":
    main()
