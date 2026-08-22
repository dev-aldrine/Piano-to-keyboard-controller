import os
import sys
import webview
from app_bridge import DesktopAppBridge

def main():
    bridge = DesktopAppBridge()
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")

    window = webview.create_window(
        title="HZWU • Neumorphic MIDI Studio & Grand Piano Controller",
        url=html_path,
        js_api=bridge,
        width=1240,
        height=940,
        min_size=(1020, 780),
        background_color="#E0E5EC"
    )
    bridge.set_window(window)
    window.events.closed += bridge.cleanup

    # Start the standalone native desktop app
    webview.start(debug=False)

if __name__ == "__main__":
    main()
