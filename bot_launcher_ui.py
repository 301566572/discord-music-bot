"""Small Tkinter launcher for the Discord music bot."""
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext


PROJECT_DIR = Path(__file__).resolve().parent
BOT_FILE = PROJECT_DIR / "bot.py"
ICON_FILE = PROJECT_DIR / "assets" / "app-icon.ico"
HELP_FILE = PROJECT_DIR / "docs" / "index.html"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0


class BotLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Discord Music Bot")
        self.geometry("760x500")
        self.minsize(640, 420)
        if ICON_FILE.exists():
            self.iconbitmap(ICON_FILE)
        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.status_var = tk.StringVar(value="未启动")
        self.python_var = tk.StringVar(value=str(self._bot_python()))

        self._build_ui()
        self.after(150, self._drain_logs)
        self.after(1000, self._poll_process)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        outer = tk.Frame(self, padx=14, pady=12)
        outer.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(outer)
        header.pack(fill=tk.X)

        tk.Label(header, text="Discord Music Bot", font=("Segoe UI", 16, "bold")).pack(
            side=tk.LEFT
        )
        tk.Label(header, textvariable=self.status_var, fg="#0f766e").pack(
            side=tk.RIGHT
        )

        path_box = tk.Frame(outer)
        path_box.pack(fill=tk.X, pady=(10, 8))
        tk.Label(path_box, text="Python:").pack(side=tk.LEFT)
        tk.Label(path_box, textvariable=self.python_var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        )

        buttons = tk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(0, 10))
        self.start_button = tk.Button(
            buttons, text="启动", width=12, command=self.start_bot
        )
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = tk.Button(
            buttons, text="停止", width=12, command=self.stop_bot, state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="打开项目文件夹", command=self.open_project).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(buttons, text="帮助中心", command=self.open_help).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(buttons, text="清空日志", command=self.clear_logs).pack(
            side=tk.RIGHT
        )

        self.log = scrolledtext.ScrolledText(
            outer,
            wrap=tk.WORD,
            font=("Consolas", 10),
            state=tk.DISABLED,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        self._append_log("准备就绪。点击“启动”运行 bot.py。\n")

    def _bot_python(self) -> Path:
        venv_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return venv_python

        executable = Path(sys.executable)
        if executable.name.lower() == "pythonw.exe":
            python_exe = executable.with_name("python.exe")
            if python_exe.exists():
                return python_exe
        return executable

    def start_bot(self):
        if self.process and self.process.poll() is None:
            return

        python = self._bot_python()
        if not BOT_FILE.exists():
            messagebox.showerror("启动失败", f"找不到 {BOT_FILE}")
            return

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self.process = subprocess.Popen(
                [str(python), str(BOT_FILE)],
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                env=env,
            )
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc))
            return

        self.status_var.set("运行中")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self._append_log(f"\n[{time.strftime('%H:%M:%S')}] 启动 bot.py\n")

        threading.Thread(target=self._read_output, daemon=True).start()

    def stop_bot(self):
        if not self.process or self.process.poll() is not None:
            self._mark_stopped()
            return

        self._append_log(f"\n[{time.strftime('%H:%M:%S')}] 正在停止...\n")
        self.process.terminate()
        threading.Thread(target=self._wait_then_kill, daemon=True).start()

    def _wait_then_kill(self):
        if not self.process:
            return
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def _read_output(self):
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.log_queue.put(line)

    def _drain_logs(self):
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)
        self.after(150, self._drain_logs)

    def _poll_process(self):
        if self.process and self.process.poll() is not None:
            self._mark_stopped()
        self.after(1000, self._poll_process)

    def _mark_stopped(self):
        self.status_var.set("未启动")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def _append_log(self, text: str):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def clear_logs(self):
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)

    def open_project(self):
        if os.name == "nt":
            os.startfile(PROJECT_DIR)
        else:
            subprocess.Popen(["xdg-open", str(PROJECT_DIR)])

    def open_help(self):
        if not HELP_FILE.exists():
            messagebox.showerror("打开失败", f"找不到 {HELP_FILE}")
            return
        if os.name == "nt":
            os.startfile(HELP_FILE)
        else:
            subprocess.Popen(["xdg-open", str(HELP_FILE)])

    def _on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("退出", "机器人仍在运行，要停止并退出吗？"):
                return
            self.stop_bot()
            self.after(400, self.destroy)
        else:
            self.destroy()


if __name__ == "__main__":
    BotLauncher().mainloop()
