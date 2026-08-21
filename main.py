import sys
from gui_app import RobloxMidiApp

def main():
    app = RobloxMidiApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

if __name__ == "__main__":
    main()
