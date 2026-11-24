"""Start the local server: python -m app"""
import os
import socket
import threading
import webbrowser

import uvicorn


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"Ports {preferred}-{preferred + 19} are all busy. Close another app and try again.")


if __name__ == "__main__":
    wanted = int(os.environ.get("SG_PORT", "8765"))
    port = free_port(wanted)
    url = f"http://localhost:{port}"
    if port != wanted:
        print(f"\n  Port {wanted} is busy, so using {port} instead.")
    print(f"\n  Screenshot Graveyard is running at {url}\n  Everything stays on this computer. Press Ctrl+C to stop.\n")
    if os.environ.get("SG_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.server:app", host="127.0.0.1", port=port, log_level="warning")
