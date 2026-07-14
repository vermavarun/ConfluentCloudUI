"""
Confluent Cloud ACL Manager — Native Desktop App
SSO via `confluent login --save` (opens browser). No API keys needed.
All data fetched through the Confluent CLI.
"""

import csv
import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import subprocess
import threading
import json
import sys
import os
import re
import webbrowser


def resource_path(relative: str) -> str:
    """Resolve path both in dev and inside a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ─── CLI helpers ──────────────────────────────────────────────────────────────

def _cli_env():
    """Return os.environ with Homebrew bin prepended to PATH.
    Guarantees HOME is set — critical when launched as a packaged .app bundle.
    """
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    if not env.get("HOME"):
        env["HOME"] = os.path.expanduser("~")
    return env


def run_confluent(*args, timeout: int = 30):
    """Run `confluent <args> --output json`. Returns (data, error_str)."""
    cmd = ["confluent"] + list(args) + ["--output", "json"]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=_cli_env()
        )
        if r.returncode != 0:
            return None, (r.stderr.strip() or r.stdout.strip() or "Command failed")
        text = r.stdout.strip()
        if not text:
            return [], None
        return json.loads(text), None
    except subprocess.TimeoutExpired:
        return None, f"Command timed out ({timeout}s)"
    except json.JSONDecodeError:
        return None, "Could not parse CLI output as JSON"
    except FileNotFoundError:
        return None, (
            "Confluent CLI not found.\n"
            "Install: https://docs.confluent.io/confluent-cli/current/install.html"
        )
    except Exception as e:
        return None, str(e)


def sso_login_async(email: str, status_cb, done_cb):
    """
    Drives `confluent login --save` interactively via pexpect:
      1. Detects the Username/Email prompt → sends email automatically.
      2. Detects any https:// URL the CLI emits → opens it in the browser.
      3. Streams every other output line to status_cb.
    Calls done_cb(ok: bool, error: str | None) when finished.
    """
    _url_re = re.compile(r'https?://[^\s\r\n]+')

    def _worker():
        try:
            import pexpect
        except ImportError:
            done_cb(False, "Missing: pip install pexpect")
            return

        browser_opened = False
        try:
            child = pexpect.spawn(
                "confluent login --save",
                env=_cli_env(),
                encoding="utf-8",
                timeout=300,
                echo=False,
            )

            patterns = [
                r"(?i)(username|email)[^\n]*:\s*$",  # 0 – credential prompt
                r"https?://[^\s\r\n]+",               # 1 – SSO URL
                r"[^\r\n]+\r?\n",                     # 2 – any complete line
                pexpect.EOF,                           # 3
            ]

            while True:
                try:
                    idx = child.expect(patterns, timeout=60)
                except pexpect.TIMEOUT:
                    if not child.isalive():
                        break
                    status_cb("Waiting for login…")
                    continue
                except pexpect.EOF:
                    break

                if idx == 0:                          # username / email prompt
                    status_cb(f"Sending email: {email}")
                    child.sendline(email)
                elif idx == 1:                        # SSO URL
                    url = (child.after or "").strip().rstrip(".")
                    if url and not browser_opened:
                        webbrowser.open(url)
                        browser_opened = True
                    status_cb("Browser opened — complete SSO login…")
                elif idx == 2:                        # ordinary line
                    line = (child.before + child.after).strip()
                    if line:
                        status_cb(line)
                        if not browser_opened:
                            for url in _url_re.findall(line):
                                webbrowser.open(url)
                                browser_opened = True
                                break
                elif idx == 3:                        # EOF
                    break

            child.wait()

            # Verify login by querying the active context — more reliable than
            # pexpect's exitstatus (which can be None inside a PyInstaller bundle).
            status_cb("Verifying login…")
            verify = subprocess.run(
                ["confluent", "context", "current"],
                capture_output=True, text=True, env=_cli_env(),
            )
            ok = verify.returncode == 0
            done_cb(ok, None if ok else "Login verification failed. Please try again.")

        except FileNotFoundError:
            done_cb(
                False,
                "Confluent CLI not found.\n"
                "Install: https://docs.confluent.io/confluent-cli/current/install.html",
            )
        except Exception as e:
            done_cb(False, str(e))

    threading.Thread(target=_worker, daemon=True).start()


# ─── Reusable dark table ──────────────────────────────────────────────────────

class DataTable(ctk.CTkFrame):
    """Scrollable dark-themed table built on ttk.Treeview."""

    def __init__(self, parent, columns: list, **kwargs):
        super().__init__(parent, fg_color="#1e1e2e", corner_radius=8, **kwargs)
        self.columns = columns

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.Treeview",
            background="#1e1e2e",
            foreground="#cdd6f4",
            fieldbackground="#1e1e2e",
            rowheight=26,
            font=("Menlo", 11),
            borderwidth=0,
        )
        style.configure(
            "Dark.Treeview.Heading",
            background="#313244",
            foreground="#89b4fa",
            font=("Menlo", 11, "bold"),
            relief="flat",
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", "#45475a")],
            foreground=[("selected", "#cdd6f4")],
        )
        style.configure("Dark.Vertical.TScrollbar",
                        background="#313244", troughcolor="#1e1e2e")
        style.configure("Dark.Horizontal.TScrollbar",
                        background="#313244", troughcolor="#1e1e2e")

        self.tree = ttk.Treeview(
            self, columns=columns, show="headings",
            style="Dark.Treeview", selectmode="browse",
        )
        for col in columns:
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, minwidth=80, width=120, anchor="w")

        self.tree.tag_configure("ALLOW", foreground="#a6e3a1")
        self.tree.tag_configure("DENY",  foreground="#f38ba8")

        vsb = ttk.Scrollbar(self, orient="vertical",   command=self.tree.yview,
                            style="Dark.Vertical.TScrollbar")
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview,
                            style="Dark.Horizontal.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        vsb.grid(row=0, column=1, sticky="ns",  pady=(8, 0))
        hsb.grid(row=1, column=0, sticky="ew",  padx=(8, 0))
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def load(self, rows: list):
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            values = [row.get(c, "") for c in self.columns]
            perm = str(row.get("Permission", row.get("permission", "")))
            tag = "ALLOW" if perm == "ALLOW" else ("DENY" if perm == "DENY" else "")
            self.tree.insert("", "end", values=values, tags=(tag,))
        for col in self.columns:
            max_len = max(
                (len(str(self.tree.set(item, col))) for item in self.tree.get_children()),
                default=0,
            )
            self.tree.column(col, width=max(max_len * 8 + 24, 100))

    def clear(self):
        self.tree.delete(*self.tree.get_children())

    def selected_values(self):
        sel = self.tree.selection()
        return self.tree.item(sel[0])["values"] if sel else None


# ─── Login screen ─────────────────────────────────────────────────────────────

class LoginFrame(ctk.CTkFrame):
    def __init__(self, parent, on_success):
        super().__init__(parent, fg_color="transparent")
        self.on_success = on_success

        card = ctk.CTkFrame(self, width=440, corner_radius=16, fg_color="#1e1e2e")
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            card,
            text="🔐  Confluent ACL Manager",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(36, 6), padx=36)

        ctk.CTkLabel(
            card,
            text="Sign in with your company SSO.\nYour browser will open automatically.",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8",
            justify="center",
        ).pack(padx=36, pady=(0, 28))

        ctk.CTkLabel(
            card, text="Email", font=ctk.CTkFont(size=13), anchor="w"
        ).pack(fill="x", padx=36)

        self.email_entry = ctk.CTkEntry(
            card,
            placeholder_text="you@company.com",
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.email_entry.pack(fill="x", padx=36, pady=(4, 20))
        self.email_entry.bind("<Return>", lambda _: self._start_login())

        self.login_btn = ctk.CTkButton(
            card,
            text="Login with SSO  →",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_login,
        )
        self.login_btn.pack(fill="x", padx=36)

        self.status_lbl = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8",
            wraplength=368,
            justify="center",
        )
        self.status_lbl.pack(padx=36, pady=(14, 0))

        ctk.CTkLabel(
            card,
            text="Requires: Confluent CLI installed locally",
            font=ctk.CTkFont(size=11),
            text_color="#585b70",
        ).pack(pady=(16, 32))

    def _start_login(self):
        email = self.email_entry.get().strip()
        if not email:
            self.status_lbl.configure(
                text="Please enter your email first.", text_color="#f38ba8"
            )
            return
        self.login_btn.configure(state="disabled", text="Connecting…")
        self.status_lbl.configure(text="Starting SSO login…", text_color="#a6adc8")

        def _status(line):
            self.after(0, lambda l=line: self.status_lbl.configure(
                text=l, text_color="#a6adc8"
            ))

        def _done(ok, err):
            self.after(0, lambda: self._on_result(ok, err, email))

        sso_login_async(email, _status, _done)

    def _on_result(self, ok, err, email):
        if ok:
            self.on_success(email)
        else:
            self.login_btn.configure(state="normal", text="Login with SSO  →")
            self.status_lbl.configure(text=f"❌  {err}", text_color="#f38ba8")


# ─── Main shell ───────────────────────────────────────────────────────────────

def _divider(parent):
    ctk.CTkFrame(parent, height=1, fg_color="#313244").pack(fill="x", padx=14, pady=12)


class MainFrame(ctk.CTkFrame):
    def __init__(self, parent, email: str):
        super().__init__(parent, fg_color="transparent")
        self.email = email
        self.env_id = None
        self.cluster_id = None
        self._env_map = {}
        self._cluster_map = {}
        self._pools_all_rows = []

        self._build_sidebar()
        self._build_content()
        self._load_environments()

    # ── Sidebar ────────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color="#181825")
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        ctk.CTkLabel(
            sb, text="Confluent ACL Manager",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(22, 2))
        ctk.CTkLabel(
            sb, text=self.email or "Logged in",
            font=ctk.CTkFont(size=11), text_color="#6c7086",
        ).pack(anchor="w", padx=18)

        _divider(sb)

        ctk.CTkLabel(sb, text="ENVIRONMENT", font=ctk.CTkFont(size=10),
                     text_color="#6c7086").pack(anchor="w", padx=18, pady=(0, 4))
        self.env_var = ctk.StringVar(value="Loading…")
        self.env_menu = ctk.CTkOptionMenu(
            sb, variable=self.env_var, values=["Loading…"],
            width=204, state="disabled",
            command=self._on_env_change,
            fg_color="#313244", button_color="#45475a", dropdown_fg_color="#313244",
        )
        self.env_menu.pack(padx=18, pady=(0, 14))

        ctk.CTkLabel(sb, text="CLUSTER", font=ctk.CTkFont(size=10),
                     text_color="#6c7086").pack(anchor="w", padx=18, pady=(0, 4))
        self.cluster_var = ctk.StringVar(value="Select environment first")
        self.cluster_menu = ctk.CTkOptionMenu(
            sb, variable=self.cluster_var,
            values=["Select environment first"],
            width=204, state="disabled",
            command=self._on_cluster_change,
            fg_color="#313244", button_color="#45475a", dropdown_fg_color="#313244",
        )
        self.cluster_menu.pack(padx=18)

        _divider(sb)

        self.ctx_lbl = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=10, family="Menlo"),
            text_color="#585b70", wraplength=208, justify="left",
        )
        self.ctx_lbl.pack(anchor="w", padx=18)

        # ── About ──────────────────────────────────────────────────────────
        about = ctk.CTkFrame(sb, fg_color="transparent")
        about.pack(side="bottom", fill="x", padx=18, pady=(0, 8))

        ctk.CTkButton(
            sb, text="Logout",
            height=34, width=204,
            fg_color="transparent", border_width=1, border_color="#45475a",
            hover_color="#313244",
            command=self._logout,
        ).pack(side="bottom", padx=18, pady=(0, 10))

        ctk.CTkFrame(sb, height=1, fg_color="#313244").pack(
            side="bottom", fill="x", padx=14, pady=(0, 10)
        )

        ctk.CTkButton(
            about,
            text="https://github.com/vermavarun",
            font=ctk.CTkFont(size=11),
            text_color="#89b4fa",
            fg_color="transparent",
            hover_color="#313244",
            height=20,
            anchor="w",
            command=lambda: webbrowser.open("https://github.com/vermavarun"),
        ).pack(fill="x")

        ctk.CTkLabel(
            about,
            text="Varun Verma",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#a6adc8",
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            about,
            text="About",
            font=ctk.CTkFont(size=10),
            text_color="#585b70",
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

    # ── Tabs ───────────────────────────────────────────────────────────────────

    def _build_content(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(side="right", fill="both", expand=True, padx=16, pady=16)

        self.tabs = ctk.CTkTabview(content, corner_radius=10, fg_color="#1e1e2e")
        self.tabs.pack(fill="both", expand=True)

        for name in [
            "🔑  ACL Permissions",
            "👥  Identity Pools",
            "📋  Role Bindings",
            "🤖  Service Accounts",
        ]:
            self.tabs.add(name)

        self._build_acl_tab()
        self._build_pools_tab()
        self._build_bindings_tab()
        self._build_accounts_tab()

    # ── Tab 1 ── ACL Permissions ───────────────────────────────────────────────

    def _build_acl_tab(self):
        t = self.tabs.tab("🔑  ACL Permissions")

        top = ctk.CTkFrame(t, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))

        ctk.CTkLabel(top, text="Principal:", font=ctk.CTkFont(size=13)).pack(
            side="left", padx=(0, 8)
        )
        self.acl_entry = ctk.CTkEntry(
            top,
            placeholder_text="pool-RkAya  or  User:pool-RkAya  or  User:sa-XXXXX",
            width=380, height=36,
        )
        self.acl_entry.pack(side="left", padx=(0, 8))
        self.acl_entry.bind("<Return>", lambda _: self._search_acls())

        ctk.CTkButton(
            top, text="Search", width=90, height=36, command=self._search_acls
        ).pack(side="left")

        self.acl_status = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11), text_color="#6c7086"
        )
        self.acl_status.pack(side="left", padx=12)

        self.acl_cli_lbl = ctk.CTkLabel(
            t, text="", font=ctk.CTkFont(size=11, family="Menlo"),
            text_color="#585b70", anchor="w",
        )
        self.acl_cli_lbl.pack(fill="x", pady=(0, 6))

        self.acl_table = DataTable(
            t,
            columns=[
                "Principal", "Resource Type", "Resource Name",
                "Pattern Type", "Operation", "Permission", "Host",
            ],
        )
        self.acl_table.pack(fill="both", expand=True)

    def _search_acls(self):
        if not self.cluster_id:
            messagebox.showwarning(
                "No cluster selected", "Please select a cluster in the sidebar."
            )
            return
        raw = self.acl_entry.get().strip()
        # Auto-prefix with "User:" if the user typed just the ID (no colon)
        if raw and ":" not in raw:
            principal = f"User:{raw}"
        else:
            principal = raw
        args = ["kafka", "acl", "list"]
        if principal:
            args += ["--principal", principal]
        self.acl_cli_lbl.configure(text="$ confluent " + " ".join(args))
        self.acl_status.configure(text="Fetching…", text_color="#6c7086")
        self.acl_table.clear()

        def _run():
            data, err = run_confluent(*args)
            self.after(0, lambda: self._render_acls(data, err))

        threading.Thread(target=_run, daemon=True).start()

    def _render_acls(self, data, err):
        if err:
            self.acl_status.configure(text=f"Error: {err}", text_color="#f38ba8")
            return
        items = data if isinstance(data, list) else ([data] if data else [])
        if not items:
            self.acl_status.configure(text="No ACL entries found.", text_color="#6c7086")
            return
        rows = [
            {
                "Principal":    d.get("principal", ""),
                "Resource Type":d.get("resource_type", ""),
                "Resource Name":d.get("resource_name", ""),
                "Pattern Type": d.get("pattern_type", ""),
                "Operation":    d.get("operation", ""),
                "Permission":   d.get("permission", ""),
                "Host":         d.get("host", ""),
            }
            for d in items
        ]
        self.acl_table.load(rows)
        allow = sum(1 for r in rows if r["Permission"] == "ALLOW")
        deny  = sum(1 for r in rows if r["Permission"] == "DENY")
        self.acl_status.configure(
            text=f"{len(rows)} entries  ·  {allow} ALLOW  ·  {deny} DENY",
            text_color="#a6e3a1",
        )

    # ── Tab 2 ── Identity Pools ────────────────────────────────────────────────

    def _build_pools_tab(self):
        t = self.tabs.tab("👥  Identity Pools")

        top = ctk.CTkFrame(t, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))

        ctk.CTkLabel(top, text="Provider ID:", font=ctk.CTkFont(size=13)).pack(
            side="left", padx=(0, 8)
        )
        self.pools_provider_entry = ctk.CTkEntry(
            top, placeholder_text="op-XXXXX", width=180, height=36
        )
        self.pools_provider_entry.pack(side="left", padx=(0, 8))
        self.pools_provider_entry.bind("<Return>", lambda _: self._load_pools())

        ctk.CTkButton(
            top, text="Load Pools", width=100, height=36, command=self._load_pools
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            top,
            text="Check ACLs for selected pool",
            width=210, height=36,
            fg_color="#45475a", hover_color="#585b70",
            command=self._acls_for_selected_pool,
        ).pack(side="left")

        self.pools_status = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11), text_color="#6c7086"
        )
        self.pools_status.pack(side="left", padx=12)

        ctk.CTkButton(
            top, text="⬇ Download CSV", width=130, height=36,
            fg_color="#45475a", hover_color="#585b70",
            command=self._download_pools,
        ).pack(side="right")

        # Filter bar
        filter_row = ctk.CTkFrame(t, fg_color="transparent")
        filter_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(filter_row, text="Filter:",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self.pools_filter_var = ctk.StringVar()
        self.pools_filter_var.trace_add("write", lambda *_: self._apply_pools_filter())
        ctk.CTkEntry(
            filter_row, textvariable=self.pools_filter_var,
            placeholder_text="Search by Pool ID, Name, Description…",
            width=420, height=34,
        ).pack(side="left")
        ctk.CTkButton(
            filter_row, text="✕", width=34, height=34,
            fg_color="#313244", hover_color="#45475a",
            command=lambda: self.pools_filter_var.set(""),
        ).pack(side="left", padx=(4, 0))

        self.pools_table = DataTable(
            t,
            columns=["Pool ID", "Display Name", "Description", "Principal Claim", "Filter"],
        )
        self.pools_table.pack(fill="both", expand=True)

    def _load_pools(self):
        provider_id = self.pools_provider_entry.get().strip()
        if not provider_id:
            messagebox.showwarning(
                "Provider ID required", "Enter an identity provider ID (op-XXXXX)."
            )
            return
        self.pools_status.configure(text="Loading…", text_color="#6c7086")
        self.pools_table.clear()

        def _run():
            data, err = run_confluent("iam", "pool", "list",
                                      "--provider", provider_id)
            self.after(0, lambda: self._render_pools(data, err))

        threading.Thread(target=_run, daemon=True).start()

    def _render_pools(self, data, err):
        if err:
            self.pools_status.configure(text=f"Error: {err}", text_color="#f38ba8")
            return
        items = data if isinstance(data, list) else ([data] if data else [])
        if not items:
            self.pools_status.configure(text="No pools found.", text_color="#6c7086")
            return
        self._pools_all_rows = [
            {
                "Pool ID":        d.get("id", ""),
                "Display Name":   d.get("display_name", ""),
                "Description":    d.get("description", ""),
                "Principal Claim":d.get("principal_claim", ""),
                "Filter":         d.get("filter", ""),
            }
            for d in items
        ]
        self.pools_filter_var.set("")  # reset filter on fresh load
        self._apply_pools_filter()

    def _apply_pools_filter(self):
        rows = getattr(self, "_pools_all_rows", [])
        q = self.pools_filter_var.get().strip().lower()
        if q:
            rows = [
                r for r in rows
                if any(q in str(v).lower() for v in r.values())
            ]
        self.pools_table.load(rows)
        total = len(getattr(self, "_pools_all_rows", []))
        shown = len(rows)
        if q:
            self.pools_status.configure(
                text=f"{shown} of {total} pools", text_color="#a6e3a1"
            )
        else:
            self.pools_status.configure(
                text=f"{total} pools", text_color="#a6e3a1"
            )

    def _download_pools(self):
        rows = getattr(self, "_pools_all_rows", [])
        # Use filtered rows if a filter is active
        q = self.pools_filter_var.get().strip().lower()
        if q:
            rows = [r for r in rows if any(q in str(v).lower() for v in r.values())]
        if not rows:
            messagebox.showinfo("No data", "Load pools first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="identity_pools.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        self.pools_status.configure(
            text=f"Saved {len(rows)} rows → {os.path.basename(path)}",
            text_color="#a6e3a1",
        )

    def _acls_for_selected_pool(self):
        vals = self.pools_table.selected_values()
        if not vals:
            messagebox.showinfo("No pool selected", "Click a pool row first.")
            return
        if not self.cluster_id:
            messagebox.showwarning("No cluster", "Select a cluster in the sidebar first.")
            return
        principal = f"User:{vals[0]}"
        self.tabs.set("🔑  ACL Permissions")
        self.acl_entry.delete(0, "end")
        self.acl_entry.insert(0, principal)
        self._search_acls()

    # ── Tab 3 ── Role Bindings ─────────────────────────────────────────────────

    def _build_bindings_tab(self):
        t = self.tabs.tab("📋  Role Bindings")

        top = ctk.CTkFrame(t, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))

        ctk.CTkLabel(top, text="Principal (optional):",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self.rb_entry = ctk.CTkEntry(
            top, placeholder_text="pool-XXXXX or User:pool-XXXXX", width=280, height=36
        )
        self.rb_entry.pack(side="left", padx=(0, 8))
        self.rb_entry.bind("<Return>", lambda _: self._load_bindings())

        ctk.CTkButton(
            top, text="Load Bindings", width=120, height=36, command=self._load_bindings
        ).pack(side="left")

        self.rb_status = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11), text_color="#6c7086"
        )
        self.rb_status.pack(side="left", padx=12)

        self.rb_table = DataTable(
            t, columns=["Principal", "Role", "Resource Type", "Resource ID"]
        )
        self.rb_table.pack(fill="both", expand=True)

    def _load_bindings(self):
        principal = self.rb_entry.get().strip()
        if principal and ":" not in principal:
            principal = "User:" + principal
        args = ["iam", "rbac", "role-binding", "list"]
        if principal:
            args += ["--principal", principal]
        self.rb_status.configure(text="Loading…", text_color="#6c7086")
        self.rb_table.clear()

        def _run():
            data, err = run_confluent(*args)
            self.after(0, lambda: self._render_bindings(data, err))

        threading.Thread(target=_run, daemon=True).start()

    def _render_bindings(self, data, err):
        if err:
            self.rb_status.configure(text=f"Error: {err}", text_color="#f38ba8")
            return
        items = data if isinstance(data, list) else ([data] if data else [])
        if not items:
            self.rb_status.configure(text="No role bindings found.", text_color="#6c7086")
            return
        rows = [
            {
                "Principal":    d.get("principal", ""),
                "Role":         d.get("role_name", ""),
                "Resource Type":d.get("resource_type", ""),
                "Resource ID":  d.get("resource_id", ""),
            }
            for d in items
        ]
        self.rb_table.load(rows)
        self.rb_status.configure(
            text=f"{len(rows)} role bindings", text_color="#a6e3a1"
        )

    # ── Tab 4 ── Service Accounts ──────────────────────────────────────────────

    def _build_accounts_tab(self):
        t = self.tabs.tab("🤖  Service Accounts")

        top = ctk.CTkFrame(t, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))

        ctk.CTkButton(
            top, text="Load Service Accounts", width=180, height=36,
            command=self._load_accounts,
        ).pack(side="left")

        self.sa_status = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11), text_color="#6c7086"
        )
        self.sa_status.pack(side="left", padx=12)

        self.sa_table = DataTable(t, columns=["ID", "Display Name", "Description"])
        self.sa_table.pack(fill="both", expand=True)

    def _load_accounts(self):
        self.sa_status.configure(text="Loading…", text_color="#6c7086")
        self.sa_table.clear()

        def _run():
            data, err = run_confluent("iam", "service-account", "list")
            self.after(0, lambda: self._render_accounts(data, err))

        threading.Thread(target=_run, daemon=True).start()

    def _render_accounts(self, data, err):
        if err:
            self.sa_status.configure(text=f"Error: {err}", text_color="#f38ba8")
            return
        items = data if isinstance(data, list) else ([data] if data else [])
        if not items:
            self.sa_status.configure(text="No service accounts.", text_color="#6c7086")
            return
        rows = [
            {
                "ID":           d.get("id", ""),
                "Display Name": d.get("display_name", ""),
                "Description":  d.get("description", ""),
            }
            for d in items
        ]
        self.sa_table.load(rows)
        self.sa_status.configure(text=f"{len(rows)} accounts", text_color="#a6e3a1")

    # ── Environment / cluster loading ──────────────────────────────────────────

    def _load_environments(self):
        def _run():
            data, err = run_confluent("environment", "list")
            self.after(0, lambda: self._populate_envs(data, err))

        threading.Thread(target=_run, daemon=True).start()

    def _populate_envs(self, data, err):
        if err or not data:
            self.env_menu.configure(values=[f"Error: {err}"], state="normal")
            return
        items = data if isinstance(data, list) else [data]
        self._env_map = {
            (d.get("display_name") or d.get("name") or d["id"]): d["id"]
            for d in items
        }
        names = list(self._env_map.keys())
        self.env_menu.configure(values=names, state="normal")
        self.env_var.set(names[0])
        self._on_env_change(names[0])

    def _on_env_change(self, name):
        self.env_id = self._env_map.get(name)
        self._load_clusters()

    def _load_clusters(self):
        self.cluster_var.set("Loading…")
        self.cluster_menu.configure(values=["Loading…"], state="disabled")
        self.cluster_id = None

        def _run():
            # Switch environment first (must complete before listing clusters)
            if self.env_id:
                subprocess.run(
                    ["confluent", "environment", "use", self.env_id],
                    capture_output=True, env=_cli_env(),
                )
            data, err = run_confluent("kafka", "cluster", "list")
            self.after(0, lambda: self._populate_clusters(data, err))

        threading.Thread(target=_run, daemon=True).start()

    def _populate_clusters(self, data, err):
        if err or not data:
            self.cluster_menu.configure(
                values=["Error loading clusters"], state="normal"
            )
            self.cluster_var.set("Error loading clusters")
            return
        items = data if isinstance(data, list) else [data]
        self._cluster_map = {
            (d.get("display_name") or d.get("name") or d["id"]): d["id"]
            for d in items
        }
        names = list(self._cluster_map.keys())
        self.cluster_menu.configure(values=names, state="normal")
        self.cluster_var.set(names[0])
        self._on_cluster_change(names[0])

    def _on_cluster_change(self, name):
        self.cluster_id = self._cluster_map.get(name)
        if self.cluster_id:
            def _use():
                subprocess.run(
                    ["confluent", "kafka", "cluster", "use", self.cluster_id],
                    capture_output=True, env=_cli_env(),
                )
            threading.Thread(target=_use, daemon=True).start()
            self.ctx_lbl.configure(
                text=f"env: {self.env_id}\ncluster: {self.cluster_id}"
            )

    def _logout(self):
        if messagebox.askyesno("Logout", "Logout from Confluent Cloud?"):
            subprocess.run(["confluent", "logout"], capture_output=True, env=_cli_env())
            self.master.show_login()


# ─── App window ───────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Confluent ACL Manager")
        self.geometry("1280x780")
        self.minsize(960, 620)
        try:
            _img = ImageTk.PhotoImage(Image.open(resource_path("icon.png")))
            self.iconphoto(True, _img)
        except Exception:
            pass
        self._frame = None
        self.show_login()

    def show_login(self):
        if self._frame:
            self._frame.destroy()
        self._frame = LoginFrame(self, on_success=self._on_login)
        self._frame.pack(fill="both", expand=True)

    def _on_login(self, email: str):
        if self._frame:
            self._frame.destroy()
        self._frame = MainFrame(self, email=email)
        self._frame.pack(fill="both", expand=True)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().mainloop()
