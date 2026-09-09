"""Small multi-monitor GUI for Neumann SSC devices.

Discovery is read-only.  Device changes happen only after pressing an action
button, which makes this useful as a first diagnostic/control surface.
"""

import argparse
import json
import queue
import pathlib
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

# Allow running directly from a source checkout as well as from an installed package.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pyssc  # noqa: E402


class App(tk.Tk):
    def __init__(self, interface: str) -> None:
        super().__init__()
        self.title("Neumann SSC Control")
        self.geometry("860x480")
        self.interface = interface
        self.devices = []
        self.events: queue.Queue = queue.Queue()
        self.status = tk.StringVar(value="Ready — discovery is read-only")
        self._build()
        self.after(100, self._drain_events)

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="IPv6 interface zone:").pack(side=tk.LEFT)
        self.interface_entry = ttk.Entry(toolbar, width=14)
        self.interface_entry.insert(0, self.interface)
        self.interface_entry.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(toolbar, text="Discover", command=self.discover).pack(side=tk.LEFT)
        ttk.Label(toolbar, textvariable=self.status).pack(side=tk.LEFT, padx=16)

        columns = ("name", "address", "status", "level", "mute")
        self.table = ttk.Treeview(self, columns=columns, show="headings", height=14)
        headings = {
            "name": "Monitor",
            "address": "IPv6 address",
            "status": "Connection",
            "level": "Level",
            "mute": "Mute",
        }
        widths = {"name": 180, "address": 300, "status": 110, "level": 90, "mute": 90}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], anchor=tk.W)
        self.table.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        actions = ttk.Frame(self, padding=8)
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Read state", command=self.read_state).pack(side=tk.LEFT)
        ttk.Button(actions, text="Mute", command=lambda: self.set_mute(True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Unmute", command=lambda: self.set_mute(False)).pack(side=tk.LEFT)
        ttk.Label(actions, text="Level dB:").pack(side=tk.LEFT, padx=(24, 4))
        self.level = ttk.Entry(actions, width=8)
        self.level.insert(0, "0")
        self.level.pack(side=tk.LEFT)
        ttk.Button(actions, text="Set level", command=self.set_level).pack(side=tk.LEFT, padx=6)

    def discover(self) -> None:
        self.status.set("Discovering SSC devices…")
        threading.Thread(target=self._discover, daemon=True).start()

    def _discover(self) -> None:
        try:
            setup = pyssc.scan(scan_time_seconds=2)
            self.events.put(("devices", setup.ssc_devices))
        except Exception as error:  # discovery must not take down the UI
            self.events.put(("error", f"Discovery failed: {error}"))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "devices":
                    self.devices = payload
                    self.table.delete(*self.table.get_children())
                    for index, device in enumerate(self.devices):
                        self.table.insert("", tk.END, iid=str(index), values=(device.name, device.ip, "discovered", "—", "—"))
                    self.status.set(f"Found {len(self.devices)} monitor(s); no changes made")
                elif kind == "state":
                    index, level, mute = payload
                    item = self.table.item(str(index))
                    values = list(item["values"])
                    values[2], values[3], values[4] = "connected", level, mute
                    self.table.item(str(index), values=values)
                    self.status.set(f"Read state from {self.devices[index].name}")
                else:
                    self.status.set(payload)
                    messagebox.showerror("Neumann SSC", payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _selected(self):
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo("Neumann SSC", "Select a monitor first")
            return None
        return int(selection[0]), self.devices[int(selection[0])]

    def _send(self, command: str, action: str) -> None:
        selected = self._selected()
        if selected is None:
            return
        index, device = selected
        threading.Thread(target=self._send_worker, args=(index, device, command, action), daemon=True).start()

    def _send_worker(self, index, device, command, action) -> None:
        try:
            zone = self.interface_entry.get().strip()
            if zone and not zone.startswith("%"):
                zone = "%" + zone
            if not device.connect(interface=zone):
                raise RuntimeError(str(device.error))
            response = device.send_ssc(command, interface=zone)
            if not response:
                raise RuntimeError(str(device.error))
            self.events.put(("status", f"{action} sent to {device.name}"))
        except Exception as error:
            self.events.put(("error", f"{action} failed: {error}"))
        finally:
            if device.connected:
                device.disconnect()

    def read_state(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        index, device = selected
        threading.Thread(target=self._read_worker, args=(index, device), daemon=True).start()

    def _read_worker(self, index, device) -> None:
        try:
            zone = self.interface_entry.get().strip()
            if zone and not zone.startswith("%"):
                zone = "%" + zone
            if not device.connect(interface=zone):
                raise RuntimeError(str(device.error))
            response = device.send_ssc('{"audio":{"out":null}}', interface=zone)
            if not response:
                raise RuntimeError(str(device.error))
            payload = json.loads(response.RX)
            audio = payload.get("audio", {}).get("out", {})
            self.events.put(("state", (index, audio.get("level", "—"), audio.get("mute", "—"))))
        except Exception as error:
            self.events.put(("error", f"Read state failed: {error}"))
        finally:
            if device.connected:
                device.disconnect()

    def set_mute(self, value: bool) -> None:
        self._send(json.dumps({"audio": {"out": {"mute": value}}}, separators=(",", ":")), "Mute" if value else "Unmute")

    def set_level(self) -> None:
        try:
            value = float(self.level.get())
        except ValueError:
            messagebox.showerror("Neumann SSC", "Level must be a number")
            return
        self._send(json.dumps({"audio": {"out": {"level": value}}}, separators=(",", ":")), "Set level")


def main() -> None:
    parser = argparse.ArgumentParser(description="Neumann SSC multi-monitor control surface")
    parser.add_argument("--interface", default="", help="IPv6 zone (for example %%en0 or %%14 on Windows)")
    args = parser.parse_args()
    App(args.interface).mainloop()


if __name__ == "__main__":
    main()
