# Desktop development

Desktop shares the Python backend, templates and styles with Web. Tauri supplies
the native window, menus and file dialogs. See the
[installation guide](../getting-started/desktop.md) for source setup.

## Local process boundary

The backend binds a random loopback port, requires a per-launch cookie, rejects
foreign origins, and exits when its parent input closes. The native window
cannot navigate outside that origin; external HTTP(S) links open in the system
browser. These controls do not replace host access controls or a security review.

Only one desktop instance may own a runtime. Background analyses use subprocesses
without Redis, with the same runners and result format as Web. Closing the app
interrupts work; interrupted jobs are marked failed rather than rerun.
Timeouts stop the analysis process tree.

Supported numerical libraries use one-thread limits; pathway enrichment uses a
serial backend. These settings are not an OS-level CPU quota for arbitrary
external programs. The custom-script sandbox has a separate one-CPU quota.

## Check navigation during a background run


For a controlled one-minute test, select **Synthetic cross-sectional demo**, then
**Custom Python / R script (synthetic prototype)** in Analysis. This requires
Docker and the configured sandbox image; the Inputs checks show their availability.
Choose Python and paste this complete script. Input preparation happens when you
click Run; generating or copying a template is not required:

```python
import time
from pathlib import Path

print("Background-run diagnostic started", flush=True)
time.sleep(60)
output = Path('/work/output')
output.mkdir(parents=True, exist_ok=True)
(output / "diagnostic.txt").write_text(
    "One-minute background-run diagnostic completed. No scientific analysis performed.\n"
)
```

Run it, visit Dashboard or Query, then return to Analysis. Check the running
status in Jobs and the completed result/files afterwards. Keep the desktop open.
The script deliberately waits rather than doing scientific work; it tests UI
responsiveness and completion delivery, not computational performance. Keep the
delay below the sandbox's 90-second execution limit.
