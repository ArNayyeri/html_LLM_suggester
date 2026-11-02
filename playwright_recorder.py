import os
import sys
import time
import json
import uuid
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright


def get_snapshot_dir(project_dir: Path) -> Path:
    """
    Finds or creates the active snapshots session directory.
    If recorder_server.py is running, reuses the active server RUN_ID.
    Otherwise, generates a new run directory in 'snapshots/'.
    """
    snapshots_dir = project_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)

    run_id = None
    try:
        req = urllib.request.Request(
            "http://localhost:5000/health",
            headers={"User-Agent": "PlaywrightRecorder"}
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            run_id = data.get("run_id")
            if run_id:
                print(f"[*] Attached to active server session: {run_id}")
    except Exception:
        pass

    if not run_id:
        timestamp = int(time.time())
        uid = uuid.uuid4().hex[:8]
        run_id = f"run_{timestamp}_{uid}"
        print(f"[*] Server not running. Created standalone session: {run_id}")

    run_dir = snapshots_dir / run_id
    run_dir.mkdir(exist_ok=True)
    return run_dir


def record_with_extension(url: str = "https://example.com"):
    """
    Launches Chromium with the project's Manifest V3 extension loaded,
    starts Playwright Tracing & Video recording, and opens the Playwright Inspector.
    All artifacts (trace, video, test code) are automatically saved to snapshots/ on exit.
    """
    project_dir = Path(__file__).resolve().parent
    extension_path = project_dir / "my_recorder_extension"
    user_data_dir = project_dir / ".playwright_profile"

    if not extension_path.exists():
        raise FileNotFoundError(f"Extension not found at {extension_path}")

    # Prepare session folder in snapshots/
    run_dir = get_snapshot_dir(project_dir)
    videos_dir = run_dir / "videos"
    videos_dir.mkdir(exist_ok=True)

    print("=" * 65)
    print("🚀 Launching Playwright with Chromium Extension")
    print("=" * 65)
    print(f"Extension path : {extension_path}")
    print(f"Profile path   : {user_data_dir}")
    print(f"Target URL     : {url}")
    print(f"Snapshot folder: {run_dir}")
    print("-" * 65)

    with sync_playwright() as p:
        # Launch Chromium persistent context with extension loaded and video recording
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            record_video_dir=str(videos_dir),
            record_video_size={"width": 1280, "height": 720},
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
            ],
        )

        # Start Playwright Tracing (captures DOM snapshots, network, console, screenshots)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

        # Identify extension ID from background service worker (Manifest V3)
        extension_id = None
        try:
            if context.service_workers:
                sw = context.service_workers[0]
            else:
                sw = context.wait_for_event("serviceworker", timeout=3000)
            extension_id = sw.url.split("/")[2]
            print(f"Extension ID   : {extension_id}")
            print(f"Extension Popup: chrome-extension://{extension_id}/popup.html")
        except Exception:
            print("Note: Service worker not detected immediately; extension is still loaded.")

        page = context.pages[0] if context.pages else context.new_page()

        print(f"\nNavigating to {url}...")
        page.goto(url)

        print("\n" + "=" * 65)
        print("💡 Playwright Inspector & Recorder Active:")
        print("  1. Click 'Record' in Playwright Inspector to generate code.")
        print("  2. In the browser, click the extension icon to Suggest Inputs (AI).")
        print("  3. Click 'Start Recording' in the extension popup to generate")
        print("     both Katalon and Playwright test scripts.")
        print("  4. Close the browser / resume in Inspector to end the session.")
        print("=" * 65 + "\n")

        # page.pause() activates the Playwright Inspector recorder
        page.pause()

        # Stop tracing and save trace file
        trace_path = run_dir / "playwright_trace.zip"
        context.tracing.stop(path=str(trace_path))

        # Close context to finalize video file
        context.close()

    print("\n" + "=" * 65)
    print("📁 Session Finished! Saved Artifacts in Snapshots:")
    print("=" * 65)
    print(f"Session Folder : {run_dir}")
    if trace_path.exists():
        print(f"Playwright Trace: {trace_path}")
        print(f"  👉 View trace with: uv run playwright show-trace \"{trace_path}\"")

    video_files = list(videos_dir.glob("*.webm"))
    if video_files:
        print(f"Session Video  : {video_files[0]}")

    playwright_test_path = run_dir / "playwright_test.py"
    if playwright_test_path.exists():
        print(f"Playwright Test : {playwright_test_path}")
        print(f"  👉 Run test with : uv run python \"{playwright_test_path}\"")

    katalon_test_path = run_dir / "katalon_test.html"
    if katalon_test_path.exists():
        print(f"Katalon Test    : {katalon_test_path}")
    print("=" * 65 + "\n")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    record_with_extension(target)


if __name__ == "__main__":
    main()
