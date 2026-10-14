from editing_copilot.__main__ import main
if __name__ == '__main__':
    import sys
    try:
        sys.exit(main())
    except Exception as exc:
        if any(flag in sys.argv for flag in ('--resolve-worker', '--self-test', '--diagnostics')):
            sys.exit(1)
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw()
        messagebox.showerror('Editing Copilot', str(exc))
        root.destroy()
        sys.exit(1)
