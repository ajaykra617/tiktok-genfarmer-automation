#!/usr/bin/env python3
"""Local desktop control plane for authorized automation.

This is intentionally a thin operator surface over the tested Python scripts.
It does not duplicate automation logic and does not store credentials. Current
interactive execution is TikTok Warm-up and Boost; the Scheduler tab validates
multi-device/app barrier plans while additional app adapters are developed.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.audit_log import AuditRecord, append_csv, append_jsonl  # noqa: E402
from genfarmer_automation.control_console import (  # noqa: E402
    build_boost_command,
    build_warmup_command,
    command_preview,
    parse_adb_devices,
)
from genfarmer_automation.schedule_policy import (  # noqa: E402
    SchedulePolicyError,
    load_schedule_plan,
    plan_summary,
)

AUDIT_JSONL = ROOT / "logs" / "automation-audit.jsonl"
AUDIT_CSV = ROOT / "logs" / "automation-audit.csv"


class AutomationConsole(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Automation Control Center")
        self.geometry("1180x820")
        self.minsize(980, 680)
        self.proc: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.device_values: list[str] = []

        self._build_style()
        self._build_header()
        self._build_tabs()
        self._build_footer()
        self.after(80, self._drain_output)
        self.refresh_devices()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build_header(self) -> None:
        frame = ttk.Frame(self, padding=(14, 12, 14, 8))
        frame.pack(fill="x")
        ttk.Label(frame, text="Automation Control Center", style="Title.TLabel").pack(side="left")
        ttk.Label(
            frame,
            text="  TikTok Warm-up + Boost · device/proxy scheduler planning · local evidence",
            style="Sub.TLabel",
        ).pack(side="left", padx=(8, 0), pady=(7, 0))
        ttk.Button(frame, text="Refresh devices", command=self.refresh_devices).pack(side="right")

    def _build_tabs(self) -> None:
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.dashboard_tab = ttk.Frame(self.tabs, padding=12)
        self.warmup_tab = ttk.Frame(self.tabs, padding=12)
        self.boost_tab = ttk.Frame(self.tabs, padding=12)
        self.scheduler_tab = ttk.Frame(self.tabs, padding=12)
        self.logs_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.dashboard_tab, text="Dashboard")
        self.tabs.add(self.warmup_tab, text="Warm-up")
        self.tabs.add(self.boost_tab, text="Boost")
        self.tabs.add(self.scheduler_tab, text="Scheduler")
        self.tabs.add(self.logs_tab, text="Logs")
        self._build_dashboard()
        self._build_warmup()
        self._build_boost()
        self._build_scheduler()
        self._build_logs()

    def _build_dashboard(self) -> None:
        intro = ttk.LabelFrame(self.dashboard_tab, text="Current scope", style="Section.TLabelframe", padding=12)
        intro.pack(fill="x")
        ttk.Label(
            intro,
            justify="left",
            text=(
                "Account mode: deferred.\n"
                "Warm-up: passive feed sessions, presets, bounded recovery, checkpoints and evidence.\n"
                "Boost: explore + approved-media publishing with duplicate guard and READY gate.\n"
                "Scheduler: barrier-wave and same-app proxy-identity validation.\n"
                "Engagement coordination, DMs, mass follow/unfollow and checkpoint/captcha bypass remain disabled."
            ),
        ).pack(anchor="w")

        devices = ttk.LabelFrame(self.dashboard_tab, text="ADB devices", style="Section.TLabelframe", padding=10)
        devices.pack(fill="both", expand=True, pady=(12, 0))
        self.device_tree = ttk.Treeview(devices, columns=("state", "model", "product"), show="headings", height=12)
        for key, label, width in (
            ("state", "State", 100),
            ("model", "Model", 220),
            ("product", "Product", 220),
        ):
            self.device_tree.heading(key, text=label)
            self.device_tree.column(key, width=width, anchor="w")
        self.device_tree.pack(fill="both", expand=True)

    def _path_row(self, parent, row: int, label: str, variable: tk.StringVar, *, directory: bool = False) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)

        def browse() -> None:
            if directory:
                value = filedialog.askdirectory(initialdir=str(ROOT))
            else:
                value = filedialog.askopenfilename(initialdir=str(ROOT))
            if value:
                variable.set(value)

        ttk.Button(parent, text="Browse", command=browse).grid(row=row, column=2, padx=(8, 0), pady=5)

    def _device_combo(self, parent, row: int, variable: tk.StringVar) -> ttk.Combobox:
        ttk.Label(parent, text="Device").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
        combo = ttk.Combobox(parent, textvariable=variable, state="normal")
        combo.grid(row=row, column=1, sticky="ew", pady=5)
        return combo

    def _build_warmup(self) -> None:
        form = ttk.LabelFrame(self.warmup_tab, text="Warm-up session", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.w_device = tk.StringVar()
        self.w_preset_file = tk.StringVar(value=str(ROOT / "config" / "tiktok-warmup-presets.example.json"))
        self.w_preset = tk.StringVar(value="standard")
        self.w_compiled = tk.StringVar(value=str(Path.home() / "Downloads" / "GF Lab - TikTok Browse One READY.genfarm"))
        self.w_candidates = tk.StringVar()
        self.w_candidate = tk.IntVar(value=8)
        self.w_apply = tk.BooleanVar(value=True)
        self.w_combo = self._device_combo(form, 0, self.w_device)
        self._path_row(form, 1, "Preset file", self.w_preset_file)
        ttk.Label(form, text="Preset").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(form, textvariable=self.w_preset, values=("short", "standard", "long"), state="normal").grid(row=2, column=1, sticky="ew", pady=5)
        self._path_row(form, 3, "Compiled .genfarm", self.w_compiled)
        self._path_row(form, 4, "Ranked candidates", self.w_candidates)
        ttk.Label(form, text="Candidate").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Spinbox(form, from_=1, to=500, textvariable=self.w_candidate, width=8).grid(row=5, column=1, sticky="w", pady=5)
        ttk.Checkbutton(form, text="Apply / execute", variable=self.w_apply).grid(row=6, column=1, sticky="w", pady=5)
        buttons = ttk.Frame(form)
        buttons.grid(row=7, column=1, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Preview command", command=self.preview_warmup).pack(side="left")
        ttk.Button(buttons, text="Start Warm-up", style="Accent.TButton", command=self.start_warmup).pack(side="left", padx=8)

    def _build_boost(self) -> None:
        form = ttk.LabelFrame(self.boost_tab, text="Boost explore + publish", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.b_device = tk.StringVar()
        self.b_media = tk.StringVar()
        self.b_candidates = tk.StringVar()
        self.b_candidate = tk.IntVar(value=8)
        self.b_caption = tk.StringVar()
        self.b_explore_type = tk.StringVar(value="keyword")
        self.b_explore_value = tk.StringVar()
        self.b_ready = tk.BooleanVar(value=True)
        self.b_publish = tk.BooleanVar(value=False)
        self.b_apply = tk.BooleanVar(value=True)
        self.b_combo = self._device_combo(form, 0, self.b_device)
        self._path_row(form, 1, "Approved media", self.b_media)
        self._path_row(form, 2, "Ranked candidates", self.b_candidates)
        ttk.Label(form, text="Candidate").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Spinbox(form, from_=1, to=500, textvariable=self.b_candidate, width=8).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Label(form, text="Explore type").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Combobox(form, textvariable=self.b_explore_type, values=("keyword", "hashtag", "account", "link"), state="readonly").grid(row=4, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="Explore value").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.b_explore_value).grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="Caption").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.b_caption).grid(row=6, column=1, sticky="ew", pady=5)
        flags = ttk.Frame(form)
        flags.grid(row=7, column=1, sticky="w", pady=5)
        ttk.Checkbutton(flags, text="Account/device READY", variable=self.b_ready).pack(side="left")
        ttk.Checkbutton(flags, text="Final publish", variable=self.b_publish).pack(side="left", padx=14)
        ttk.Checkbutton(flags, text="Apply / execute", variable=self.b_apply).pack(side="left")
        ttk.Label(
            form,
            text="Tip: leave Final publish OFF for READY_TO_PUBLISH qualification.",
        ).grid(row=8, column=1, sticky="w", pady=(2, 5))
        buttons = ttk.Frame(form)
        buttons.grid(row=9, column=1, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Preview command", command=self.preview_boost).pack(side="left")
        ttk.Button(buttons, text="Start Boost", style="Accent.TButton", command=self.start_boost).pack(side="left", padx=8)

    def _build_scheduler(self) -> None:
        form = ttk.LabelFrame(self.scheduler_tab, text="Barrier scheduler plan", style="Section.TLabelframe", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.s_file = tk.StringVar(value=str(ROOT / "config" / "scheduler.example.json"))
        self._path_row(form, 0, "Schedule JSON", self.s_file)
        ttk.Button(form, text="Validate schedule", style="Accent.TButton", command=self.validate_schedule).grid(row=1, column=1, sticky="w", pady=(10, 0))
        ttk.Label(
            form,
            wraplength=950,
            justify="left",
            text=(
                "Validation enforces a barrier between waves, one task per device per wave, and distinct proxy IDs for concurrent devices running the same app. "
                "Execution of Instagram/Reddit/X waves will be enabled only when those adapters exist; the planner can already model them safely."
            ),
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.schedule_output = ScrolledText(self.scheduler_tab, height=22, font=("Consolas", 10))
        self.schedule_output.pack(fill="both", expand=True, pady=(12, 0))

    def _build_logs(self) -> None:
        tools = ttk.Frame(self.logs_tab)
        tools.pack(fill="x")
        ttk.Button(tools, text="Refresh audit log", command=self.refresh_audit_log).pack(side="left")
        ttk.Button(tools, text="Open evidence folder", command=lambda: self._open_folder(ROOT / "evidence")).pack(side="left", padx=8)
        ttk.Button(tools, text="Open logs folder", command=lambda: self._open_folder(ROOT / "logs")).pack(side="left")
        self.log_text = ScrolledText(self.logs_tab, height=30, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, pady=(10, 0))

    def _build_footer(self) -> None:
        frame = ttk.Frame(self, padding=(12, 0, 12, 10))
        frame.pack(fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status).pack(side="left")
        ttk.Button(frame, text="Stop active process", command=self.stop_process).pack(side="right")

    def _open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["explorer", str(path)])
        except OSError as exc:
            messagebox.showerror("Open folder", str(exc))

    def refresh_devices(self) -> None:
        try:
            proc = subprocess.run(
                ["adb", "devices", "-l"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=8,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"adb exited {proc.returncode}")
            rows = parse_adb_devices(proc.stdout)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            self.status.set(f"Device refresh failed: {exc}")
            return

        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        values: list[str] = []
        for row in rows:
            self.device_tree.insert("", "end", values=(row.state, row.model or "", row.product or ""), text=row.serial, iid=row.serial)
            if row.state == "device":
                values.append(row.serial)
        # Treeview show=headings hides iid/serial, so add serial into model display title via first column replacement.
        self.device_tree.configure(columns=("state", "model", "product"))
        self.device_values = values
        for combo in (getattr(self, "w_combo", None), getattr(self, "b_combo", None)):
            if combo is not None:
                combo["values"] = values
        if values:
            if not self.w_device.get():
                self.w_device.set(values[0])
            if not self.b_device.get():
                self.b_device.set(values[0])
        self.status.set(f"{len(values)} ready ADB device(s)")

    def _warmup_cmd(self) -> list[str]:
        return build_warmup_command(
            python_exe=sys.executable,
            root=ROOT,
            preset_file=Path(self.w_preset_file.get()),
            preset=self.w_preset.get().strip(),
            compiled=Path(self.w_compiled.get()),
            candidates=Path(self.w_candidates.get()),
            candidate=int(self.w_candidate.get()),
            device=self.w_device.get().strip(),
            apply=bool(self.w_apply.get()),
        )

    def _boost_cmd(self) -> list[str]:
        explore_value = self.b_explore_value.get().strip()
        return build_boost_command(
            python_exe=sys.executable,
            root=ROOT,
            device=self.b_device.get().strip(),
            media=Path(self.b_media.get()),
            candidates=Path(self.b_candidates.get()),
            candidate=int(self.b_candidate.get()),
            caption=self.b_caption.get(),
            explore_type=self.b_explore_type.get().strip() if explore_value else None,
            explore_value=explore_value or None,
            ready=bool(self.b_ready.get()),
            publish=bool(self.b_publish.get()),
            apply=bool(self.b_apply.get()),
        )

    def preview_warmup(self) -> None:
        try:
            self._append_log("\nWARM-UP PREVIEW\n" + command_preview(self._warmup_cmd()) + "\n")
            self.tabs.select(self.logs_tab)
        except Exception as exc:
            messagebox.showerror("Warm-up", str(exc))

    def preview_boost(self) -> None:
        try:
            self._append_log("\nBOOST PREVIEW\n" + command_preview(self._boost_cmd()) + "\n")
            self.tabs.select(self.logs_tab)
        except Exception as exc:
            messagebox.showerror("Boost", str(exc))

    def start_warmup(self) -> None:
        try:
            self._start_process(self._warmup_cmd(), mode="warmup", action="session", app="tiktok")
        except Exception as exc:
            messagebox.showerror("Warm-up", str(exc))

    def start_boost(self) -> None:
        try:
            self._start_process(self._boost_cmd(), mode="boost", action="explore_publish", app="tiktok")
        except Exception as exc:
            messagebox.showerror("Boost", str(exc))

    def _audit(self, *, app: str, mode: str, action: str, result: str) -> None:
        record = AuditRecord.now(
            account="local",
            app=app,
            mode=mode,
            action=action,
            proxy="unassigned",
            result=result,
        )
        append_jsonl(AUDIT_JSONL, record)
        append_csv(AUDIT_CSV, record)

    def _start_process(self, cmd: list[str], *, mode: str, action: str, app: str) -> None:
        if self.proc is not None and self.proc.poll() is None:
            raise RuntimeError("another automation process is already running")
        if not cmd or not cmd[0]:
            raise ValueError("invalid command")
        self.tabs.select(self.logs_tab)
        self._append_log("\n" + "=" * 80 + "\n" + command_preview(cmd) + "\n" + "=" * 80 + "\n")
        self.status.set(f"Running {mode}...")
        self._audit(app=app, mode=mode, action=action, result="started")

        def worker() -> None:
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                )
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    self.output_queue.put(line)
                code = self.proc.wait()
                self.output_queue.put(f"\n[process exit={code}]\n")
                self._audit(app=app, mode=mode, action=action, result="ok" if code == 0 else "error")
                self.output_queue.put("__DONE_OK__" if code == 0 else "__DONE_ERROR__")
            except Exception as exc:
                self.output_queue.put(f"\n[launcher error] {exc}\n")
                self._audit(app=app, mode=mode, action=action, result="error")
                self.output_queue.put("__DONE_ERROR__")
            finally:
                self.proc = None

        threading.Thread(target=worker, daemon=True).start()

    def stop_process(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self.status.set("No active process")
            return
        try:
            proc.terminate()
            self.status.set("Stop requested")
        except OSError as exc:
            self.status.set(f"Stop failed: {exc}")

    def _drain_output(self) -> None:
        try:
            while True:
                value = self.output_queue.get_nowait()
                if value == "__DONE_OK__":
                    self.status.set("Automation completed successfully")
                elif value == "__DONE_ERROR__":
                    self.status.set("Automation stopped with an error")
                else:
                    self._append_log(value)
        except queue.Empty:
            pass
        self.after(80, self._drain_output)

    def _append_log(self, text: str) -> None:
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def validate_schedule(self) -> None:
        self.schedule_output.delete("1.0", "end")
        try:
            payload = json.loads(Path(self.s_file.get()).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise SchedulePolicyError("schedule root must be an object")
            plan = load_schedule_plan(payload)
            summary = plan_summary(plan)
            self.schedule_output.insert("end", "VALID\n\n")
            self.schedule_output.insert("end", json.dumps(summary, indent=2) + "\n\n")
            for wave in plan.waves:
                self.schedule_output.insert("end", f"{wave.name}  [barrier after completion]\n")
                for task in wave.tasks:
                    self.schedule_output.insert(
                        "end",
                        f"  {task.device:16}  app={task.app:10} mode={task.mode:10} proxy={task.proxy_id} preset={task.preset or '-'}\n",
                    )
                self.schedule_output.insert("end", "\n")
        except (OSError, json.JSONDecodeError, SchedulePolicyError) as exc:
            self.schedule_output.insert("end", f"INVALID\n\n{exc}\n")

    def refresh_audit_log(self) -> None:
        self.log_text.delete("1.0", "end")
        if not AUDIT_JSONL.exists():
            self.log_text.insert("end", "No audit log yet.\n")
            return
        lines = AUDIT_JSONL.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        self.log_text.insert("end", "\n".join(lines) + "\n")
        self.log_text.see("end")


def main() -> int:
    try:
        app = AutomationConsole()
        app.mainloop()
        return 0
    except tk.TclError as exc:
        print(f"ERROR: Tk desktop UI is unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
