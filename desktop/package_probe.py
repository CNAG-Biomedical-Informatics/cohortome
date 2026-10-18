"""Exercise a real packaged worker without requiring external analysis runtimes."""
import time
from server import configure_environment, runtime_directory


def main():
    configure_environment(runtime_directory())
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


if __name__ == "__main__":
    main()
