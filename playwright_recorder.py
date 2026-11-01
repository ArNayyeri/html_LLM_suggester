import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def record_with_extension(url: str = "https://example.com"):
    """
    Launches Chromium with the project's Manifest V3 extension loaded
    and opens the Playwright Inspector (Codegen) recorder.
    """
    project_dir = Path(__file__).resolve().parent
    extension_path = project_dir / "my_recorder_extension"
    user_data_dir = project_dir / ".playwright_profile"

    if not extension_path.exists():
        raise FileNotFoundError(f"Extension not found at {extension_path}")

    print("=" * 65)
    print("🚀 Launching Playwright with Chromium Extension")
    print("=" * 65)
    print(f"Extension path : {extension_path}")
    print(f"Profile path   : {user_data_dir}")
    print(f"Target URL     : {url}")
    print("-" * 65)

    with sync_playwright() as p:
        # Chrome extensions require a persistent context and headless=False
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
            ],
        )

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
        print("  1. The Playwright Inspector window opens alongside Chromium.")
        print("  2. Click 'Record' in the inspector to generate Playwright code.")
        print("  3. The extension is active in the browser toolbar.")
        print("  4. Make sure recorder_server.py is running on port 5000.")
        if extension_id:
            print(f"  5. You can also open the extension popup tab at:")
            print(f"     chrome-extension://{extension_id}/popup.html")
        print("=" * 65 + "\n")

        # page.pause() activates the Playwright Inspector recorder
        page.pause()

        context.close()

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    record_with_extension(target)

if __name__ == "__main__":
    main()
