import contextlib
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import sys
import tempfile
from threading import Thread
import tkinter as tk
from tkinter import messagebox, ttk

from serial.tools import list_ports

PAYLOAD = Path(__file__).resolve().parent / "firmware"


def flash_args(manifest, port):
    args = ["--chip", "esp32", "--port", port, "--baud", "460800",
            "--before", "default-reset", "--after", "hard-reset", "write-flash",
            *manifest["args"]]
    for image in manifest["images"]:
        path = PAYLOAD / image["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != image["sha256"]:
            raise ValueError(f"固件校验失败：{path.name}")
        args.extend([image["offset"], str(path)])
    return args


class FlashLog:
    """Keep the complete esptool 5.2 log and forward its write events to Tk."""
    def __init__(self, file, manifest, results):
        self.file = file
        self.results = results
        self.images = {}
        self.total = 0
        for image in sorted(manifest["images"], key=lambda item: int(item["offset"], 0)):
            size = (PAYLOAD / image["file"]).stat().st_size
            self.images[int(image["offset"], 0)] = (self.total, size)
            self.total += size
        self.base = None
        self.percent = 0

    def write(self, text):
        count = self.file.write(text)
        # esptool reports the flash address in uncompressed bytes, even when
        # the serial transfer is compressed. Each image starts with 0/N bytes.
        match = re.search(r"Writing at (0x[0-9a-fA-F]+).*?%\s+(\d+)/(\d+) bytes", text)
        if match:
            address = int(match[1], 16)
            sent, length = int(match[2]), int(match[3])
            if sent == 0 and address in self.images:
                self.base = address
            if self.base is not None:
                before, size = self.images[self.base]
                written = size if sent == length else min(size, max(0, address - self.base))
                self.percent = max(self.percent, min(99, (before + written) * 100 // self.total))
                self.results.put(("progress", "正在写入固件", self.percent))
        elif "Verifying written data..." in text:
            self.results.put(("progress", "正在校验已写入的数据", self.percent))
        elif "Hard resetting via RTS" in text:
            self.results.put(("progress", "正在复位设备", self.percent))
        elif "Lost connection, retrying" in text:
            self.results.put(("progress", "连接中断，正在重试", self.percent))
        return count

    def __getattr__(self, name):
        return getattr(self.file, name)


def flash(manifest, port, results):
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                         prefix="HEX-Bridge-", suffix=".log") as log:
            args = flash_args(manifest, port)
            output = FlashLog(log, manifest, results)
            results.put(("progress", f"正在连接 {port}", 0))
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(log):
                import esptool
                esptool.main(args)
    except (Exception, SystemExit) as error:
        detail = str(error)
        if "log" in locals():
            detail += f"\n日志：{log.name}"
        results.put(("error", detail, None))
    else:
        results.put(("done", "更新完成，可以断开设备", 100))


class Updater:
    def __init__(self, root, manifest):
        self.root = root
        self.manifest = manifest
        self.busy = False
        self.results = Queue()
        root.title("HEX-Bridge 固件更新")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(root, padding=24)
        body.grid()
        ttk.Label(body, text="HEX-Bridge 固件更新",
                  font=("Microsoft YaHei UI", 16, "bold")).grid(columnspan=2, sticky="w")
        ttk.Label(body, text=f"内置固件  v{manifest['version']}").grid(columnspan=2, sticky="w")
        ttk.Label(body, text="连接 HEX-Bridge 的 UART0 下载口，选择对应串口。").grid(
            columnspan=2, sticky="w", pady=(22, 6))
        self.port = ttk.Combobox(body, state="readonly", width=41)
        self.port.grid(row=3, column=0, sticky="ew")
        self.port.bind("<<ComboboxSelected>>", lambda _: self.ready())
        self.refresh = ttk.Button(body, text="刷新", command=self.scan)
        self.refresh.grid(row=3, column=1, padx=(8, 0))
        self.status = tk.StringVar()
        ttk.Label(body, textvariable=self.status).grid(row=4, column=0, sticky="w", pady=(16, 4))
        self.percent = tk.StringVar()
        ttk.Label(body, textvariable=self.percent).grid(row=4, column=1, sticky="e", pady=(16, 4))
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.grid(columnspan=2, sticky="ew")
        self.update = ttk.Button(body, text="更新固件", command=self.start)
        self.update.grid(columnspan=2, sticky="ew", pady=(16, 0))
        self.scan()

    def scan(self):
        previous = self.port.get()
        self.ports = {f"{p.device}  ·  {p.description}": p.device
                      for p in sorted(list_ports.comports())}
        self.port.configure(values=list(self.ports))
        self.port.set(previous if previous in self.ports else "")
        self.ready()

    def ready(self):
        self.percent.set("")
        self.progress.configure(value=0)
        self.update.configure(text="更新固件", command=self.start)
        if self.port.get() in self.ports:
            self.status.set("就绪")
            self.update.configure(state="normal")
        else:
            self.status.set("请选择 UART0 串口" if self.ports else "未发现串口，请连接设备后刷新")
            self.update.configure(state="disabled")

    def start(self):
        self.busy = True
        port = self.ports[self.port.get()]
        for widget in (self.update, self.refresh, self.port):
            widget.configure(state="disabled")
        self.status.set("正在检查内置固件")
        self.percent.set("")
        self.progress.configure(value=0)
        self.update.configure(text="更新中，请保持连接")
        Thread(target=flash, args=(self.manifest, port, self.results)).start()
        self.root.after(150, self.poll)

    def poll(self):
        try:
            while True:
                event, message, value = self.results.get_nowait()
                if event == "error":
                    break
                self.status.set(message)
                self.progress.configure(value=value)
                self.percent.set(f"{value}%" if value or message == "正在写入固件" else "")
                if event == "done":
                    break
        except Empty:
            self.root.after(150, self.poll)
            return
        self.busy = False
        self.refresh.configure(state="normal")
        self.port.configure(state="readonly")
        if event == "done":
            self.update.configure(text="完成并关闭", state="normal", command=self.close)
        else:
            self.status.set(self.status.get().replace("正在", "") + "失败")
            self.update.configure(text="重试更新", state="normal")
            messagebox.showerror("更新失败", f"请检查下载口连接，并关闭占用串口的软件。\n\n{message}")

    def close(self):
        if self.busy:
            messagebox.showinfo("正在更新", "请等待写入完成。")
        else:
            self.root.destroy()


def main():
    manifest = json.loads((PAYLOAD / "manifest.json").read_text("utf-8"))
    root = tk.Tk()
    if sys.argv[1:] == ["--self-test"]:
        root.withdraw()
        Updater(root, manifest)
        root.update_idletasks()
        root.destroy()
        args = flash_args(manifest, "offline")
        import esptool
        from esptool.loader import StubFlasher
        from esptool.targets.esp32 import ESP32ROM
        StubFlasher(ESP32ROM)
        esptool.main(["--chip", "esp32", "image-info", args[-1]])
        return
    Updater(root, manifest)
    root.mainloop()


if __name__ == "__main__":
    # A windowed executable has no standard streams. Click and Rich expect them.
    with open(os.devnull, "w", encoding="utf-8") as sink:
        if sys.stdout is None:
            sys.stdout = sink
        if sys.stderr is None:
            sys.stderr = sink
        main()
