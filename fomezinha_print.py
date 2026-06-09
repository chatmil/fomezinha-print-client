#!/usr/bin/env python3
"""
Fomezinha Print Client
Auto-impressão de pedidos para impressora térmica/sistema
"""

import json
import os
import sys
import time
import threading
import platform
import subprocess
import queue
import tempfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import requests

# ─── Caminhos de configuração ───────────────────────────────────────────────
APP_NAME = "Fomezinha Print"
CONFIG_DIR = Path.home() / ".fomezinha-print"
CONFIG_FILE = CONFIG_DIR / "config.json"
PRINTED_FILE = CONFIG_DIR / "printed.json"
LOG_FILE = CONFIG_DIR / "app.log"


def _resource_path(filename: str) -> Path:
    """Resolve caminho de recurso — funciona tanto no dev quanto no PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / filename
    return Path(__file__).parent / filename

# ─── Paleta de cores ─────────────────────────────────────────────────────────
C = {
    "primary":     "#FF6B35",
    "primary_dk":  "#E55A24",
    "primary_lt":  "#FF8C5A",
    "success":     "#27AE60",
    "success_dk":  "#1E8449",
    "danger":      "#E74C3C",
    "danger_dk":   "#C0392B",
    "warning":     "#F39C12",
    "bg":          "#F8F9FA",
    "bg_card":     "#FFFFFF",
    "bg_dark":     "#2C3E50",
    "text":        "#2C3E50",
    "text_muted":  "#7F8C8D",
    "text_light":  "#BDC3C7",
    "border":      "#E0E0E0",
    "header_bg":   "#2C3E50",
    "tab_active":  "#FF6B35",
    "green_pill":  "#D5F5E3",
    "green_txt":   "#1E8449",
    "red_pill":    "#FADBD8",
    "red_txt":     "#C0392B",
    "amber_pill":  "#FDEBD0",
    "amber_txt":   "#D35400",
}

DEFAULT_CONFIG = {
    "server_url": "https://fomezinha.com.br",
    "email": "",
    "password": "",
    "restaurant_id": "",
    "restaurant_name": "",
    "access_token": "",
    "refresh_token": "",
    "printer_type": "system",   # system | network | usb | serial
    "printer_name": "",         # nome da impressora do sistema ou IP
    "printer_port": 9100,
    "poll_interval": 15,
    "auto_accept": False,
    "sound_alert": True,
    "print_statuses": ["RECEIVED"],
}


# ─── Config ──────────────────────────────────────────────────────────────────
class Config:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


# ─── Pedidos já impressos ────────────────────────────────────────────────────
class PrintedOrders:
    def __init__(self):
        self.ids: set = set()
        self._load()

    def _load(self):
        if PRINTED_FILE.exists():
            try:
                with open(PRINTED_FILE, encoding="utf-8") as f:
                    self.ids = set(json.load(f).get("ids", []))
            except Exception:
                pass

    def _save(self):
        with open(PRINTED_FILE, "w", encoding="utf-8") as f:
            json.dump({"ids": list(self.ids)}, f)

    def is_printed(self, order_id: str) -> bool:
        return order_id in self.ids

    def mark(self, order_id: str):
        self.ids.add(order_id)
        if len(self.ids) > 2000:
            self.ids = set(sorted(self.ids)[-1000:])
        self._save()


# ─── API Client ─────────────────────────────────────────────────────────────
class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.token: str | None = None
        self.refresh_token_value: str | None = None
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Restaurar tokens salvos
        saved_access = self.config.get("access_token", "")
        saved_refresh = self.config.get("refresh_token", "")
        if saved_access:
            self.token = saved_access
            self.session.headers["Authorization"] = f"Bearer {saved_access}"
        if saved_refresh:
            self.refresh_token_value = saved_refresh

    @property
    def base(self) -> str:
        return self.config.get("server_url", "").rstrip("/")

    def login(self, email=None, password=None):
        r = self.session.post(
            f"{self.base}/api/auth/login",
            json={
                "email": email or self.config.get("email"),
                "password": password or self.config.get("password"),
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        self._apply_tokens(data)
        return data

    def refresh(self):
        if not self.refresh_token_value:
            raise RuntimeError("Sem refresh token — faça login novamente")
        r = self.session.post(
            f"{self.base}/api/auth/refresh",
            json={"refreshToken": self.refresh_token_value},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        self._apply_tokens(data)
        return data

    def _apply_tokens(self, data: dict):
        self.token = data["accessToken"]
        self.refresh_token_value = data.get("refreshToken", self.refresh_token_value)
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.config.set("access_token", self.token)
        self.config.set("refresh_token", self.refresh_token_value or "")
        self.config.save()

    def logout(self):
        self.token = None
        self.refresh_token_value = None
        self.session.headers.pop("Authorization", None)
        self.config.set("access_token", "")
        self.config.set("refresh_token", "")
        self.config.save()

    def get_restaurants(self):
        r = self.session.get(f"{self.base}/api/restaurants", timeout=15)
        r.raise_for_status()
        return r.json()

    def get_orders(self, restaurant_id: str, status: str = "PENDING"):
        r = self.session.get(
            f"{self.base}/api/orders/{restaurant_id}",
            params={"status": status, "limit": 50, "page": 1},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def update_status(self, order_id: str, status: str, cancel_reason: str = ""):
        body: dict = {"status": status}
        if cancel_reason:
            body["cancelReason"] = cancel_reason
        r = self.session.put(
            f"{self.base}/api/orders/{order_id}/status",
            json=body,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()


# ─── Impressora ──────────────────────────────────────────────────────────────
class Printer:
    def __init__(self, config: Config):
        self.config = config

    # -- Formatar pedido como texto plano (80 chars) -------------------------
    def format_receipt(self, order: dict, restaurant_name: str = "") -> str:
        W = 42
        sep = "=" * W
        thin = "-" * W

        def center(txt): return txt.center(W)
        def rjust_pair(left, right, width=W):
            space = width - len(left) - len(right)
            return left + " " * max(1, space) + right

        lines = [sep, center(restaurant_name), sep]

        num = order.get("orderNumber", "?")
        lines.append(center(f"*** PEDIDO #{num} ***"))

        created = order.get("createdAt", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                lines.append(center(dt.strftime("%d/%m/%Y %H:%M")))
            except Exception:
                pass

        type_map = {"DELIVERY": "DELIVERY", "PICKUP": "RETIRADA",
                    "TABLE": "MESA", "COUNTER": "BALCÃO"}
        order_type = type_map.get(order.get("orderType", ""), order.get("orderType", ""))
        lines.append(center(f"[ {order_type} ]"))

        if order.get("table"):
            lines.append(center(f"Mesa: {order['table'].get('name', '')}"))

        lines += [thin, "ITENS:", thin]

        for item in (order.get("items") or []):
            if not isinstance(item, dict):
                continue
            product = item.get("product") or {}
            if isinstance(product, str):
                product = {"name": product}
            prod_name = product.get("name") or item.get("name") or "?"
            qty = item.get("quantity") or 1
            total_price = float(item.get("totalPrice") or 0)
            lines.append(rjust_pair(f"{qty}x {prod_name}", f"R${total_price:.2f}"))

            for fl in (item.get("flavors") or []):
                if isinstance(fl, dict):
                    lines.append(f"  + Sabor: {fl.get('name', '')}")
            for var in (item.get("variations") or []):
                if isinstance(var, dict):
                    lines.append(f"  * {var.get('groupName', '')}: {var.get('name', '')}")
            for ad in (item.get("additionals") or []):
                if not isinstance(ad, dict):
                    continue
                ad_qty = ad.get("quantity") or 1
                ad_name = ad.get("name") or ""
                ad_price = float(ad.get("price") or 0)
                suffix = f" R${ad_price * ad_qty:.2f}" if ad_price > 0 else ""
                lines.append(f"  + {ad_qty}x {ad_name}{suffix}")

            obs = item.get("observations") or ""
            if obs:
                lines.append(f"  >> {obs}")

        lines.append(thin)
        delivery_fee = float(order.get("deliveryFee", 0) or 0)
        if delivery_fee > 0:
            lines.append(rjust_pair("  Frete:", f"R${delivery_fee:.2f}"))

        total = float(order.get("total", 0) or 0)
        lines.append(rjust_pair("  TOTAL:", f"R${total:.2f}"))

        pay_map = {"CASH": "Dinheiro", "CARD": "Cartão", "PIX": "PIX"}
        payment = pay_map.get(order.get("paymentMethod", ""), order.get("paymentMethod", ""))
        lines.append(f"  Pagamento: {payment}")

        change = float(order.get("changeFor", 0) or 0)
        if change > 0:
            lines.append(f"  Troco para: R${change:.2f}")

        lines += [thin, "CLIENTE:"]
        lines.append(f"  {order.get('customerName', '')}")
        phone = order.get("customerPhone", "")
        if phone:
            lines.append(f"  Tel: {phone}")

        if order.get("orderType") == "DELIVERY":
            addr = order.get("deliveryAddress", "")
            if addr:
                lines += ["ENDEREÇO DE ENTREGA:"]
                # Wrap long address
                while len(addr) > W - 2:
                    lines.append(f"  {addr[:W-2]}")
                    addr = addr[W - 2:]
                if addr:
                    lines.append(f"  {addr}")

        obs_geral = order.get("observations", "")
        if obs_geral:
            lines += ["OBSERVAÇÕES:", f"  {obs_geral}"]

        lines += [sep, "", ""]
        return "\n".join(lines)

    # -- ESC/POS térmico -----------------------------------------------------
    def _print_escpos(self, order: dict, restaurant_name: str):
        try:
            from escpos import printer as ep
        except ImportError:
            raise RuntimeError(
                "python-escpos não instalado.\n"
                "Execute: pip install python-escpos"
            )

        ptype = self.config.get("printer_type")
        if ptype == "network":
            p = ep.Network(
                self.config.get("printer_name"),
                self.config.get("printer_port", 9100),
            )
        elif ptype == "usb":
            p = ep.Usb(
                int(self.config.get("printer_usb_vendor", "0x04b8"), 16),
                int(self.config.get("printer_usb_product", "0x0e15"), 16),
            )
        elif ptype == "serial":
            p = ep.Serial(self.config.get("printer_name", "COM1"))
        else:
            raise ValueError("Tipo de impressora ESC/POS inválido")

        W = 32
        sep = "=" * W
        thin = "-" * W

        p.set(align="center", bold=True, double_width=True, double_height=True)
        p.text(restaurant_name + "\n")
        p.set(align="center", bold=False, double_width=False, double_height=False)
        p.text(sep + "\n")
        p.set(align="center", bold=True)
        p.text(f"PEDIDO #{order.get('orderNumber', '?')}\n")

        created = order.get("createdAt", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                p.text(dt.strftime("%d/%m/%Y  %H:%M") + "\n")
            except Exception:
                pass

        type_map = {"DELIVERY": "DELIVERY", "PICKUP": "RETIRADA",
                    "TABLE": "MESA", "COUNTER": "BALCÃO"}
        order_type = type_map.get(order.get("orderType", ""), "")
        p.set(align="center", bold=True)
        p.text(f"[ {order_type} ]\n")

        if order.get("table"):
            p.text(f"Mesa: {order['table'].get('name', '')}\n")

        p.set(align="left", bold=False)
        p.text(thin + "\n")
        p.text("ITENS:\n")
        p.text(thin + "\n")

        for item in (order.get("items") or []):
            if not isinstance(item, dict):
                continue
            product = item.get("product") or {}
            if isinstance(product, str):
                product = {"name": product}
            name = product.get("name") or item.get("name") or "?"
            qty = item.get("quantity") or 1
            price = float(item.get("totalPrice") or 0)
            p.set(bold=True)
            p.text(f"{qty}x {name}\n")
            p.set(bold=False)
            p.text(f"    R${price:.2f}\n")

            for fl in (item.get("flavors") or []):
                if isinstance(fl, dict):
                    p.text(f"  + Sabor: {fl.get('name', '')}\n")
            for var in (item.get("variations") or []):
                if isinstance(var, dict):
                    p.text(f"  * {var.get('groupName', '')}: {var.get('name', '')}\n")
            for ad in (item.get("additionals") or []):
                if not isinstance(ad, dict):
                    continue
                ad_qty = ad.get("quantity") or 1
                ad_name = ad.get("name") or ""
                p.text(f"  + {ad_qty}x {ad_name}\n")

            obs = item.get("observations") or ""
            if obs:
                p.text(f"  >> {obs}\n")

        p.text(thin + "\n")
        delivery_fee = float(order.get("deliveryFee", 0) or 0)
        if delivery_fee > 0:
            p.text(f"Frete: R${delivery_fee:.2f}\n")

        total = float(order.get("total", 0) or 0)
        p.set(bold=True)
        p.text(f"TOTAL: R${total:.2f}\n")
        p.set(bold=False)

        pay_map = {"CASH": "Dinheiro", "CARD": "Cartão", "PIX": "PIX"}
        payment = pay_map.get(order.get("paymentMethod", ""), "")
        p.text(f"Pagamento: {payment}\n")

        change = float(order.get("changeFor", 0) or 0)
        if change > 0:
            p.text(f"Troco: R${change:.2f}\n")

        p.text(thin + "\n")
        p.set(bold=True)
        p.text(f"{order.get('customerName', '')}\n")
        p.set(bold=False)
        phone = order.get("customerPhone", "")
        if phone:
            p.text(f"Tel: {phone}\n")

        if order.get("orderType") == "DELIVERY":
            addr = order.get("deliveryAddress", "")
            if addr:
                p.set(bold=True)
                p.text("ENTREGA:\n")
                p.set(bold=False)
                p.text(f"{addr}\n")

        obs_geral = order.get("observations", "")
        if obs_geral:
            p.set(bold=True)
            p.text("OBS:\n")
            p.set(bold=False)
            p.text(f"{obs_geral}\n")

        p.text(sep + "\n")
        p.cut()
        p.close()

    # -- Impressão via sistema operacional ------------------------------------
    def _print_system(self, order: dict, restaurant_name: str):
        text = self.format_receipt(order, restaurant_name)
        system = platform.system()
        printer_name = self.config.get("printer_name", "")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmpfile = f.name

        try:
            if system == "Windows":
                self._print_windows(tmpfile, printer_name)
            else:
                self._print_unix(tmpfile, printer_name)
        finally:
            try:
                time.sleep(1)
                os.unlink(tmpfile)
            except Exception:
                pass

    def _print_windows(self, filepath: str, printer_name: str):
        try:
            import win32api
            import win32print
            pname = printer_name or win32print.GetDefaultPrinter()
            win32api.ShellExecute(0, "printto", filepath, f'"{pname}"', ".", 0)
        except ImportError:
            # Fallback sem pywin32
            subprocess.run(
                ["notepad.exe", "/p", filepath],
                check=True, timeout=10,
            )

    def _print_unix(self, filepath: str, printer_name: str):
        if not printer_name:
            raise RuntimeError(
                "Nenhuma impressora configurada. "
                "Selecione uma impressora na aba Impressora e salve."
            )
        cmd = ["lp", "-d", printer_name, filepath]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"lp retornou código {result.returncode}")

    # -- Ponto de entrada principal ------------------------------------------
    def print_order(self, order: dict, restaurant_name: str = ""):
        ptype = self.config.get("printer_type", "system")
        if ptype in ("network", "usb", "serial"):
            self._print_escpos(order, restaurant_name)
        else:
            self._print_system(order, restaurant_name)

    # -- Listar impressoras do sistema ----------------------------------------
    def list_system_printers(self) -> list[str]:
        system = platform.system()
        if system == "Windows":
            try:
                import win32print
                return [p[2] for p in win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                )]
            except ImportError:
                pass
            # Fallback via wmic
            try:
                result = subprocess.run(
                    ["wmic", "printer", "get", "name"],
                    capture_output=True, text=True, timeout=5,
                )
                return [
                    line.strip() for line in result.stdout.splitlines()
                    if line.strip() and line.strip().lower() != "name"
                ]
            except Exception:
                return []
        else:
            try:
                result = subprocess.run(
                    ["lpstat", "-a"], capture_output=True, text=True, timeout=5
                )
                return [
                    line.split()[0]
                    for line in result.stdout.splitlines()
                    if " accepting" in line
                ]
            except Exception:
                return []


# ─── Helpers de UI ───────────────────────────────────────────────────────────
def _btn(parent, text, cmd, bg, fg="white", bold=False, padx=18, pady=9, width=0):
    font = ("Segoe UI", 10, "bold") if bold else ("Segoe UI", 10)
    kw = dict(text=text, command=cmd, bg=bg, fg=fg, activebackground=bg,
              activeforeground=fg, relief="flat", cursor="hand2",
              font=font, padx=padx, pady=pady, bd=0)
    if width:
        kw["width"] = width
    b = tk.Button(parent, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_darken(bg)))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def _darken(hex_color):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    factor = 0.85
    return "#{:02x}{:02x}{:02x}".format(int(r*factor), int(g*factor), int(b*factor))

def _card(parent, **kw):
    defaults = dict(bg=C["bg_card"], relief="flat", bd=0,
                    highlightthickness=1, highlightbackground=C["border"],
                    highlightcolor=C["border"])
    defaults.update(kw)
    return tk.Frame(parent, **defaults)

def _label(parent, text, size=10, bold=False, color=None, bg=None, **kw):
    font = ("Segoe UI", size, "bold") if bold else ("Segoe UI", size)
    return tk.Label(parent, text=text, font=font,
                    fg=color or C["text"], bg=bg or C["bg_card"], **kw)

def _entry(parent, var, show="", bg=C["bg_card"]):
    f = tk.Frame(parent, bg=C["border"], padx=1, pady=1)
    e = tk.Entry(f, textvariable=var, font=("Segoe UI", 11),
                 show=show, relief="flat", bd=6,
                 bg=C["bg_card"], fg=C["text"],
                 insertbackground=C["text"],
                 highlightthickness=0)
    e.pack(fill="x")
    return f, e


# ─── Aplicação Principal ─────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.config = Config()
        self.printed = PrintedOrders()
        self.api = APIClient(self.config)
        self.printer = Printer(self.config)

        self.polling = False
        self._poll_thread: threading.Thread | None = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._tray_icon = None
        self._log_text = None

        self.order_count = 0
        self.connected = False

        self.root = tk.Tk()
        self.root.withdraw()
        self._apply_style()
        self._build_ui()
        self._process_queue()

    # ── TTK Style ─────────────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=[0, 0, 0, 0])
        s.configure("TNotebook.Tab",
                    background=C["bg"], foreground=C["text_muted"],
                    font=("Segoe UI", 10), padding=[18, 8], borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", C["bg_card"])],
              foreground=[("selected", C["primary"])],
              expand=[("selected", [1, 1, 1, 0])])
        s.configure("TCombobox", fieldbackground=C["bg_card"], background=C["bg_card"],
                    foreground=C["text"], font=("Segoe UI", 10))
        s.configure("TSpinbox", fieldbackground=C["bg_card"], foreground=C["text"],
                    font=("Segoe UI", 10))
        s.configure("TCheckbutton", background=C["bg_card"], foreground=C["text"],
                    font=("Segoe UI", 10))
        s.configure("TRadiobutton", background=C["bg_card"], foreground=C["text"],
                    font=("Segoe UI", 10))

    # ── Logging ──────────────────────────────────────────────────────────────
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        self._ui_queue.put(("log", line))

    def _process_queue(self):
        try:
            while True:
                item = self._ui_queue.get_nowait()
                kind, data = item
                if kind == "log" and self._log_text:
                    self._log_text.config(state="normal")
                    self._log_text.insert("end", data + "\n")
                    self._log_text.see("end")
                    self._log_text.config(state="disabled")
                elif kind == "status":
                    if hasattr(self, "_status_var"):
                        self._status_var.set(data)
                    if hasattr(self, "_pill_var"):
                        self._pill_var.set(data)
        except queue.Empty:
            pass
        self.root.after(300, self._process_queue)

    def _set_status(self, msg: str):
        self._ui_queue.put(("status", msg))

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = self.root
        root.title(APP_NAME)
        root.configure(bg=C["bg"])
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self._set_window_icon()
        self._show_login_screen()

    def _set_window_icon(self):
        try:
            from PIL import Image, ImageTk
            img = Image.open(_resource_path("icon.png")).resize((32, 32), Image.LANCZOS)
            self._tk_icon = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self._tk_icon)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # TELA DE LOGIN
    # ══════════════════════════════════════════════════════════════════════════
    def _show_login_screen(self):
        for w in self.root.winfo_children():
            w.destroy()

        self.root.geometry("420x520")
        self.root.title(f"{APP_NAME} — Login")

        # Fundo
        bg = tk.Frame(self.root, bg=C["bg"])
        bg.pack(fill="both", expand=True)

        # Topo laranja
        top = tk.Frame(bg, bg=C["primary"], height=130)
        top.pack(fill="x")
        top.pack_propagate(False)
        try:
            from PIL import Image, ImageTk
            logo_img = Image.open(_resource_path("icon.png")).resize((56, 56), Image.LANCZOS)
            self._logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(top, image=self._logo_photo, bg=C["primary"]).pack(pady=(18, 4))
        except Exception:
            tk.Label(top, text="🍕", font=("Segoe UI", 28),
                     bg=C["primary"], fg="white").pack(pady=(18, 0))
        tk.Label(top, text="Fomezinha Print", font=("Segoe UI", 13, "bold"),
                 bg=C["primary"], fg="white").pack()

        # Card branco central
        card = _card(bg)
        card.pack(fill="x", padx=32, pady=24)

        inner = tk.Frame(card, bg=C["bg_card"])
        inner.pack(fill="x", padx=28, pady=24)

        _label(inner, "Bem-vindo de volta", size=13, bold=True).pack(anchor="w")
        _label(inner, "Entre com suas credenciais para continuar",
               size=9, color=C["text_muted"]).pack(anchor="w", pady=(2, 16))

        # E-mail
        _label(inner, "E-mail", size=9, bold=True, color=C["text_muted"]).pack(anchor="w")
        self._login_email_var = tk.StringVar(value=self.config.get("email", ""))
        ef, email_entry = _entry(inner, self._login_email_var)
        ef.pack(fill="x", pady=(3, 12))

        # Senha
        _label(inner, "Senha", size=9, bold=True, color=C["text_muted"]).pack(anchor="w")
        self._login_pass_var = tk.StringVar(value=self.config.get("password", ""))
        pf, pass_entry = _entry(inner, self._login_pass_var, show="●")
        pf.pack(fill="x", pady=(3, 4))

        # Mostrar senha toggle
        self._show_pass = tk.BooleanVar(value=False)
        def _toggle_pass():
            pass_entry.config(show="" if self._show_pass.get() else "●")
        ttk.Checkbutton(inner, text="Mostrar senha", variable=self._show_pass,
                        command=_toggle_pass).pack(anchor="w", pady=(0, 16))

        # Mensagem de erro
        self._login_err_var = tk.StringVar()
        self._login_err_lbl = tk.Label(inner, textvariable=self._login_err_var,
                                       bg=C["bg_card"], fg=C["danger"],
                                       font=("Segoe UI", 9), wraplength=300)
        self._login_err_lbl.pack(fill="x", pady=(0, 8))

        # Botão entrar
        self._login_btn = _btn(inner, "  Entrar  ", self._do_login,
                               C["primary"], bold=True, padx=0, pady=11)
        self._login_btn.pack(fill="x")

        # Lembrar credenciais
        self._remember_var = tk.BooleanVar(value=bool(self.config.get("email")))
        ttk.Checkbutton(inner, text="Lembrar credenciais",
                        variable=self._remember_var).pack(anchor="w", pady=(10, 0))

        # Binds Enter
        email_entry.bind("<Return>", lambda e: pass_entry.focus())
        pass_entry.bind("<Return>", lambda e: self._do_login())

        self.root.deiconify()
        email_entry.focus_set() if not self.config.get("email") else pass_entry.focus_set()

    # ── Ação de login ─────────────────────────────────────────────────────────
    def _do_login(self):
        email = self._login_email_var.get().strip()
        password = self._login_pass_var.get()
        if not email or not password:
            self._login_err_var.set("Preencha e-mail e senha.")
            return

        self._login_err_var.set("")
        self._login_btn.config(state="disabled", text="  Entrando…  ")

        def _login_thread():
            try:
                self.api.login(email=email, password=password)
                restaurants = self.api.get_restaurants()
                if not restaurants:
                    raise RuntimeError("Nenhum restaurante encontrado nesta conta.")
                rest = restaurants[0] if isinstance(restaurants, list) else restaurants
                self.config.set("restaurant_id", rest["id"])
                self.config.set("restaurant_name", rest["name"])
                if self._remember_var.get():
                    self.config.set("email", email)
                    self.config.set("password", password)
                else:
                    self.config.set("email", "")
                    self.config.set("password", "")
                self.config.save()
                self.connected = True
                self.order_count = 0
                self.log(f"Login bem-sucedido — restaurante: {rest['name']}")
                self.root.after(0, lambda: self._show_main_screen(rest["name"]))
                self.root.after(100, self.start_polling)
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                if code == 401:
                    msg = "E-mail ou senha incorretos."
                elif code == 422:
                    msg = "Dados inválidos. Verifique o e-mail."
                else:
                    msg = f"Erro do servidor ({code})."
                self.root.after(0, lambda: (
                    self._login_err_var.set(msg),
                    self._login_btn.config(state="normal", text="  Entrar  "),
                ))
            except Exception as e:
                self.root.after(0, lambda: (
                    self._login_err_var.set(f"Erro: {e}"),
                    self._login_btn.config(state="normal", text="  Entrar  "),
                ))

        threading.Thread(target=_login_thread, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════════
    # TELA PRINCIPAL (pós-login)
    # ══════════════════════════════════════════════════════════════════════════
    def _show_main_screen(self, restaurant_name: str):
        for w in self.root.winfo_children():
            w.destroy()

        self.root.geometry("560x660")
        self.root.title(APP_NAME)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["header_bg"], height=68)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        left = tk.Frame(hdr, bg=C["header_bg"])
        left.pack(side="left", padx=16, pady=12)
        tk.Label(left, text="🍕 Fomezinha Print", font=("Segoe UI", 13, "bold"),
                 bg=C["header_bg"], fg="white").pack(anchor="w")
        tk.Label(left, text=restaurant_name, font=("Segoe UI", 9),
                 bg=C["header_bg"], fg=C["text_light"]).pack(anchor="w")

        right = tk.Frame(hdr, bg=C["header_bg"])
        right.pack(side="right", padx=16, pady=10)

        self._status_var = tk.StringVar(value="Aguardando…")
        tk.Label(right, textvariable=self._status_var,
                 font=("Segoe UI", 8), bg=C["header_bg"],
                 fg=C["text_light"]).pack(anchor="e")

        logout_btn = tk.Label(right, text="Sair  ✕", font=("Segoe UI", 9),
                              bg=C["header_bg"], fg="#aaa", cursor="hand2")
        logout_btn.pack(anchor="e", pady=(4, 0))
        logout_btn.bind("<Button-1>", lambda e: self._do_logout())
        logout_btn.bind("<Enter>", lambda e: logout_btn.config(fg="white"))
        logout_btn.bind("<Leave>", lambda e: logout_btn.config(fg="#aaa"))

        # ── Status pill ───────────────────────────────────────────────────────
        pill_bar = tk.Frame(self.root, bg=C["bg"], pady=10)
        pill_bar.pack(fill="x", padx=16)

        self._pill_frame = tk.Frame(pill_bar, bg=C["green_pill"],
                                    padx=12, pady=4,
                                    highlightthickness=1,
                                    highlightbackground=C["success"])
        self._pill_frame.pack(side="left")
        self._pill_var = tk.StringVar(value="● Monitorando pedidos")
        self._pill_lbl = tk.Label(self._pill_frame, textvariable=self._pill_var,
                                  bg=C["green_pill"], fg=C["green_txt"],
                                  font=("Segoe UI", 9, "bold"))
        self._pill_lbl.pack()

        self._orders_var = tk.StringVar(value="0 pedidos impressos")
        tk.Label(pill_bar, textvariable=self._orders_var,
                 font=("Segoe UI", 9), bg=C["bg"],
                 fg=C["text_muted"]).pack(side="right")

        # ── Notebook ──────────────────────────────────────────────────────────
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._tab_print = tk.Frame(nb, bg=C["bg_card"])
        self._tab_settings = tk.Frame(nb, bg=C["bg_card"])
        self._tab_log = tk.Frame(nb, bg=C["bg_card"])

        nb.add(self._tab_print,    text="  Impressora  ")
        nb.add(self._tab_settings, text="  Configurações  ")
        nb.add(self._tab_log,      text="  Log  ")

        self._build_printer_tab()
        self._build_settings_tab()
        self._build_log_tab()

        # ── Botão parar/iniciar ───────────────────────────────────────────────
        ctrl = tk.Frame(self.root, bg=C["bg"], pady=10)
        ctrl.pack(fill="x", padx=16)

        self._btn_stop = _btn(ctrl, "⏹  Parar monitoramento",
                              self._do_stop, C["danger"], padx=16)
        self._btn_stop.pack(side="left")

        self._btn_restart = _btn(ctrl, "▶  Reiniciar",
                                 self.start_polling, C["success"], padx=16)
        self._btn_restart.pack(side="left", padx=8)

    # ── Aba Impressora ─────────────────────────────────────────────────────────
    def _build_printer_tab(self):
        f = self._tab_print
        outer = tk.Frame(f, bg=C["bg_card"])
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        _label(outer, "Tipo de Impressora", size=11, bold=True,
               bg=C["bg_card"]).pack(anchor="w", pady=(0, 10))

        self._ptype_var = tk.StringVar(value=self.config.get("printer_type", "system"))

        types = [
            ("system",  "💻  Impressora do Sistema (Windows / macOS / Linux)"),
            ("network", "🌐  Térmica de Rede — TCP/IP (ESC/POS)"),
            ("usb",     "🔌  Térmica USB (ESC/POS)"),
            ("serial",  "🔧  Térmica Serial — COM / ttyUSB (ESC/POS)"),
        ]
        for val, label in types:
            rb = ttk.Radiobutton(outer, text=label, variable=self._ptype_var,
                                 value=val, command=self._refresh_printer_ui)
            rb.pack(anchor="w", pady=2)

        sep = tk.Frame(outer, bg=C["border"], height=1)
        sep.pack(fill="x", pady=12)

        # Painel sistema
        self._sys_frame = tk.Frame(outer, bg=C["bg_card"])
        _label(self._sys_frame, "Impressora:", size=9, bold=True,
               color=C["text_muted"], bg=C["bg_card"]).pack(anchor="w")
        self._sys_pname_var = tk.StringVar(value=self.config.get("printer_name", ""))
        self._sys_combo = ttk.Combobox(self._sys_frame, textvariable=self._sys_pname_var,
                                       font=("Segoe UI", 10), state="readonly", width=38)
        self._sys_combo.pack(fill="x", pady=(3, 6))
        _btn(self._sys_frame, "↻  Atualizar lista", self._load_sys_printers,
             C["bg"], C["text_muted"], padx=8, pady=5).pack(anchor="w")

        # Painel rede
        self._net_frame = tk.Frame(outer, bg=C["bg_card"])
        _label(self._net_frame, "Endereço IP:", size=9, bold=True,
               color=C["text_muted"], bg=C["bg_card"]).pack(anchor="w")
        self._net_ip_var = tk.StringVar(value=self.config.get("printer_name", "192.168.1.100"))
        nf, _ = _entry(self._net_frame, self._net_ip_var)
        nf.pack(fill="x", pady=(3, 8))
        _label(self._net_frame, "Porta TCP (padrão 9100):", size=9, bold=True,
               color=C["text_muted"], bg=C["bg_card"]).pack(anchor="w")
        self._net_port_var = tk.IntVar(value=self.config.get("printer_port", 9100))
        ttk.Spinbox(self._net_frame, from_=1, to=65535,
                    textvariable=self._net_port_var, width=10).pack(anchor="w", pady=(3, 0))

        # Painel serial
        self._serial_frame = tk.Frame(outer, bg=C["bg_card"])
        _label(self._serial_frame, "Porta serial (ex: COM3 ou /dev/ttyUSB0):",
               size=9, bold=True, color=C["text_muted"], bg=C["bg_card"]).pack(anchor="w")
        self._serial_var = tk.StringVar(value=self.config.get("printer_name", "COM1"))
        sf, _ = _entry(self._serial_frame, self._serial_var)
        sf.pack(fill="x", pady=(3, 0))

        # Painel USB
        self._usb_frame = tk.Frame(outer, bg=C["bg_card"])
        tk.Label(self._usb_frame, bg=C["amber_pill"], fg=C["amber_txt"],
                 font=("Segoe UI", 9),
                 text="  Certifique-se que o driver da impressora está instalado.  ",
                 padx=8, pady=6).pack(anchor="w")

        self._refresh_printer_ui()
        self._load_sys_printers()

        sep2 = tk.Frame(outer, bg=C["border"], height=1)
        sep2.pack(fill="x", pady=12)

        btn_row = tk.Frame(outer, bg=C["bg_card"])
        btn_row.pack(fill="x")
        _btn(btn_row, "🖨  Imprimir Teste", self._test_print,
             C["primary"], bold=True, padx=14).pack(side="left")
        _btn(btn_row, "💾  Salvar", self._save_printer_config,
             C["success"], padx=14).pack(side="right")

    def _refresh_printer_ui(self):
        ptype = self._ptype_var.get()
        for frm, show in [
            (self._sys_frame,    ptype == "system"),
            (self._net_frame,    ptype == "network"),
            (self._serial_frame, ptype == "serial"),
            (self._usb_frame,    ptype == "usb"),
        ]:
            if show:
                frm.pack(fill="x", pady=4)
            else:
                frm.pack_forget()

    def _load_sys_printers(self):
        printers = self.printer.list_system_printers()
        self._sys_combo["values"] = printers
        if printers and not self._sys_pname_var.get():
            self._sys_pname_var.set(printers[0])

    # ── Aba Configurações ──────────────────────────────────────────────────────
    def _build_settings_tab(self):
        f = self._tab_settings
        outer = tk.Frame(f, bg=C["bg_card"])
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Polling ──
        _label(outer, "Monitoramento", size=11, bold=True,
               bg=C["bg_card"]).pack(anchor="w", pady=(0, 10))

        row1 = tk.Frame(outer, bg=C["bg_card"])
        row1.pack(fill="x", pady=(0, 8))
        _label(row1, "Verificar pedidos a cada (segundos):", size=10,
               bg=C["bg_card"]).pack(side="left")
        self._interval_var = tk.IntVar(value=self.config.get("poll_interval", 15))
        ttk.Spinbox(row1, from_=5, to=300, textvariable=self._interval_var,
                    width=6, font=("Segoe UI", 10)).pack(side="right")

        self._auto_accept_var = tk.BooleanVar(value=self.config.get("auto_accept"))
        ttk.Checkbutton(outer,
                        text="Confirmar pedido automaticamente após imprimir (PENDING → RECEIVED)",
                        variable=self._auto_accept_var).pack(anchor="w", pady=4)

        self._sound_var = tk.BooleanVar(value=self.config.get("sound_alert"))
        ttk.Checkbutton(outer, text="Tocar alerta sonoro ao receber pedido",
                        variable=self._sound_var).pack(anchor="w", pady=4)

        sep = tk.Frame(outer, bg=C["border"], height=1)
        sep.pack(fill="x", pady=12)

        # ── Servidor ──
        _label(outer, "Servidor", size=11, bold=True,
               bg=C["bg_card"]).pack(anchor="w", pady=(0, 10))

        _label(outer, "URL base:", size=9, bold=True, color=C["text_muted"],
               bg=C["bg_card"]).pack(anchor="w")
        self._url_var = tk.StringVar(value=self.config.get("server_url"))
        uf, _ = _entry(outer, self._url_var)
        uf.pack(fill="x", pady=(3, 12))

        sep2 = tk.Frame(outer, bg=C["border"], height=1)
        sep2.pack(fill="x", pady=12)

        # ── Status a monitorar ──
        _label(outer, "Status de pedidos a monitorar", size=11, bold=True,
               bg=C["bg_card"]).pack(anchor="w", pady=(0, 6))
        _label(outer, "Quais status devem disparar impressão/alerta:",
               size=9, color=C["text_muted"], bg=C["bg_card"]).pack(anchor="w", pady=(0, 8))

        saved_statuses = self.config.get("print_statuses", ["RECEIVED"])
        all_statuses = [
            ("PENDING",  "Pendente — pedido recém chegou"),
            ("RECEIVED", "Recebido — já confirmado"),
            ("ACCEPTED", "Aceito"),
            ("PREPARING","Em preparo"),
        ]
        self._status_check_vars: dict[str, tk.BooleanVar] = {}
        for val, desc in all_statuses:
            var = tk.BooleanVar(value=(val in saved_statuses))
            self._status_check_vars[val] = var
            ttk.Checkbutton(outer, text=f"{val} — {desc}",
                            variable=var).pack(anchor="w", pady=1)

        sep3 = tk.Frame(outer, bg=C["border"], height=1)
        sep3.pack(fill="x", pady=12)

        btn_row = tk.Frame(outer, bg=C["bg_card"])
        btn_row.pack(fill="x")
        _btn(btn_row, "💾  Salvar Configurações", self._save_settings,
             C["success"], padx=14).pack(side="right")

    # ── Aba Log ────────────────────────────────────────────────────────────────
    def _build_log_tab(self):
        f = self._tab_log

        toolbar = tk.Frame(f, bg=C["bg_card"], pady=6)
        toolbar.pack(fill="x", padx=12)
        _label(toolbar, "Log de atividade", size=10, bold=True,
               bg=C["bg_card"]).pack(side="left")
        _btn(toolbar, "🗑  Limpar", self._clear_log,
             C["bg"], C["text_muted"], padx=8, pady=4).pack(side="right")

        self._log_text = scrolledtext.ScrolledText(
            f, font=("Consolas", 9), state="disabled",
            bg="#1A1D2E", fg="#A8FF78",
            insertbackground="white", relief="flat",
            padx=10, pady=10, wrap="word",
        )
        self._log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _clear_log(self):
        if self._log_text:
            self._log_text.config(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.config(state="disabled")

    # ── Ações ──────────────────────────────────────────────────────────────────
    def _save_settings(self):
        self.config.set("server_url", self._url_var.get().rstrip("/"))
        self.config.set("poll_interval", int(self._interval_var.get()))
        self.config.set("auto_accept", self._auto_accept_var.get())
        self.config.set("sound_alert", self._sound_var.get())
        selected = [s for s, v in self._status_check_vars.items() if v.get()]
        if not selected:
            selected = ["RECEIVED"]
        self.config.set("print_statuses", selected)
        self.config.save()
        messagebox.showinfo("Salvo", "✅ Configurações salvas com sucesso!")

    def _save_printer_config(self):
        ptype = self._ptype_var.get()
        self.config.set("printer_type", ptype)
        if ptype == "system":
            self.config.set("printer_name", self._sys_pname_var.get())
        elif ptype == "network":
            self.config.set("printer_name", self._net_ip_var.get().strip())
            self.config.set("printer_port", int(self._net_port_var.get()))
        elif ptype == "serial":
            self.config.set("printer_name", self._serial_var.get().strip())
        self.config.save()
        messagebox.showinfo("Salvo", "✅ Configuração de impressora salva!")

    def _do_stop(self):
        self.stop_polling()
        self._set_status("Monitoramento parado")
        self.log("Monitoramento parado pelo usuário")
        if hasattr(self, "_pill_frame"):
            self._pill_frame.config(bg=C["red_pill"],
                                    highlightbackground=C["danger"])
            self._pill_lbl.config(bg=C["red_pill"], fg=C["red_txt"])
            self._pill_var.set("● Parado")

    def _do_logout(self):
        if messagebox.askyesno("Sair", "Deseja sair e voltar à tela de login?"):
            self.stop_polling()
            self.api.logout()
            self.connected = False
            self._log_text = None
            self._show_login_screen()

    def _update_pill(self, active: bool):
        if not hasattr(self, "_pill_frame"):
            return
        if active:
            self._pill_frame.config(bg=C["green_pill"],
                                    highlightbackground=C["success"])
            self._pill_lbl.config(bg=C["green_pill"], fg=C["green_txt"])
            self._pill_var.set("● Monitorando pedidos")
        else:
            self._pill_frame.config(bg=C["red_pill"],
                                    highlightbackground=C["danger"])
            self._pill_lbl.config(bg=C["red_pill"], fg=C["red_txt"])
            self._pill_var.set("● Parado")

    def _test_print(self):
        self._save_printer_config()
        test = {
            "id": "TEST",
            "orderNumber": 9999,
            "orderType": "DELIVERY",
            "status": "PENDING",
            "createdAt": datetime.now().isoformat(),
            "customerName": "Cliente Teste",
            "customerPhone": "(11) 99999-9999",
            "deliveryAddress": "Rua das Flores, 123 – Centro",
            "paymentMethod": "PIX",
            "total": 49.90,
            "deliveryFee": 5.00,
            "changeFor": 0,
            "observations": "Sem cebola, por favor!",
            "items": [
                {
                    "quantity": 2,
                    "totalPrice": 29.90,
                    "observations": "Ponto médio",
                    "product": {"name": "X-Bacon Especial"},
                    "flavors": [],
                    "additionals": [{"quantity": 1, "name": "Bacon Extra", "price": 3.00}],
                    "variations": [{"groupName": "Tamanho", "name": "Grande"}],
                }
            ],
        }
        try:
            rest_name = self.config.get("restaurant_name", "Restaurante")
            self.printer.print_order(test, rest_name)
            messagebox.showinfo("Teste", "✅ Impressão de teste enviada!")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao imprimir:\n\n{e}")

    # ── Polling ────────────────────────────────────────────────────────────────
    def start_polling(self):
        if self.polling:
            return
        self.polling = True
        self.root.after(0, lambda: self._update_pill(True))
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        self.polling = False
        self.root.after(0, lambda: self._update_pill(False))

    def _poll_loop(self):
        restaurant_id = self.config.get("restaurant_id")
        restaurant_name = self.config.get("restaurant_name", "")
        self.log("Monitoramento iniciado.")

        while self.polling:
            try:
                statuses = self.config.get("print_statuses", ["PENDING"])
                new_orders = []
                total_api = 0
                cutoff = time.time() - 86400  # ignora pedidos com mais de 24h
                for status in statuses:
                    data = self.api.get_orders(restaurant_id, status)
                    batch = data.get("orders", [])
                    total_api += len(batch)
                    for order in batch:
                        if self.printed.is_printed(order["id"]):
                            continue
                        created = order.get("createdAt", "")
                        if created:
                            try:
                                ts = datetime.fromisoformat(
                                    created.replace("Z", "+00:00")
                                ).timestamp()
                                if ts < cutoff:
                                    self.printed.mark(order["id"])  # silencia pedido antigo
                                    continue
                            except Exception:
                                pass
                        new_orders.append(order)

                self.log(
                    f"Poll [{', '.join(statuses)}]: "
                    f"{total_api} na API, {len(new_orders)} novo(s)"
                )

                for order in sorted(new_orders, key=lambda o: o.get("createdAt", "")):
                    num = order.get("orderNumber", "?")
                    self.log(f"Novo pedido #{num} recebido!")

                    # Marca como visto ANTES de imprimir — evita loop caso impressão falhe
                    self.printed.mark(order["id"])
                    self.order_count += 1
                    self.root.after(0, lambda c=self.order_count: (
                        self._orders_var.set(f"{c} pedido(s) recebido(s)")
                        if hasattr(self, "_orders_var") else None
                    ))

                    # Notificação visual na janela
                    self.root.after(0, lambda o=order: self._show_order_toast(o))

                    # Alerta sonoro sempre que chega pedido novo
                    if self.config.get("sound_alert"):
                        self._beep()

                    # Confirmação automática
                    if self.config.get("auto_accept") and order.get("status") == "PENDING":
                        try:
                            self.api.update_status(order["id"], "RECEIVED")
                            self.log(f"Pedido #{num} confirmado automaticamente")
                        except Exception as ae:
                            self.log(f"Erro ao confirmar #{num}: {ae}")

                    # Impressão (falha não interrompe o fluxo)
                    try:
                        self.printer.print_order(order, restaurant_name)
                        self.log(f"Pedido #{num} impresso ✓")
                    except Exception as err:
                        self.log(f"Aviso: impressão do pedido #{num} falhou — {err}")

                self._set_status(f"Ativo — {self.order_count} pedido(s) impresso(s)")

            except requests.exceptions.ConnectionError:
                self.log("Sem conexão com o servidor. Tentando novamente…")
                self._set_status("Sem conexão!")
                time.sleep(10)
                continue

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                if code == 401:
                    self.log("Token expirado — tentando refresh…")
                    try:
                        self.api.refresh()
                        self.log("Token renovado com sucesso.")
                        continue
                    except Exception:
                        pass
                    self.log("Refresh falhou — tentando login novamente…")
                    try:
                        self.api.login()
                        self.log("Re-login com sucesso.")
                        continue
                    except requests.exceptions.HTTPError as re2:
                        if re2.response is not None and re2.response.status_code == 401:
                            self.log("Credenciais inválidas — encerrando monitoramento.")
                            self.polling = False
                            self._set_status("Sessão expirada")
                            self.root.after(0, lambda: (
                                self._update_pill(False),
                                messagebox.showerror(
                                    "Sessão expirada",
                                    "Sua sessão expirou e não foi possível renovar.\n"
                                    "Faça login novamente.",
                                ),
                                self._do_logout(),
                            ))
                            break
                    except Exception as re3:
                        self.log(f"Falha ao reautenticar: {re3}")
                else:
                    self.log(f"Erro HTTP {code}: {e}")

            except Exception as e:
                self.log(f"Erro inesperado: {e}")

            interval = self.config.get("poll_interval", 15)
            time.sleep(interval)

        self.log("Monitoramento encerrado.")

    # ── Toast de novo pedido ───────────────────────────────────────────────────
    def _show_order_toast(self, order: dict):
        try:
            num   = order.get("orderNumber", "?")
            name  = order.get("customerName", "")
            total = float(order.get("total", 0) or 0)
            otype_map = {"DELIVERY": "🛵 Delivery", "PICKUP": "🏃 Retirada",
                         "TABLE": "🪑 Mesa", "COUNTER": "🏠 Balcão"}
            otype = otype_map.get(order.get("orderType", ""), order.get("orderType", ""))
            items_count = sum(i.get("quantity", 1) for i in order.get("items", []))

            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.configure(bg=C["bg_dark"])

            # Posiciona no canto inferior direito da janela principal
            self.root.update_idletasks()
            rx = self.root.winfo_x() + self.root.winfo_width()
            ry = self.root.winfo_y() + self.root.winfo_height()
            tw, th = 320, 140
            toast.geometry(f"{tw}x{th}+{rx - tw - 10}+{ry - th - 10}")

            # Barra laranja no topo
            bar = tk.Frame(toast, bg=C["primary"], height=4)
            bar.pack(fill="x")

            body = tk.Frame(toast, bg=C["bg_dark"], padx=16, pady=12)
            body.pack(fill="both", expand=True)

            # Linha 1: ícone + número
            top_row = tk.Frame(body, bg=C["bg_dark"])
            top_row.pack(fill="x")
            tk.Label(top_row, text=f"🔔  NOVO PEDIDO #{num}",
                     font=("Segoe UI", 11, "bold"),
                     bg=C["bg_dark"], fg=C["primary"]).pack(side="left")
            close_lbl = tk.Label(top_row, text="✕", font=("Segoe UI", 10),
                                 bg=C["bg_dark"], fg=C["text_muted"], cursor="hand2")
            close_lbl.pack(side="right")
            close_lbl.bind("<Button-1>", lambda e: toast.destroy())

            # Linha 2: tipo + cliente
            tk.Label(body, text=f"{otype}  •  {name}",
                     font=("Segoe UI", 9), bg=C["bg_dark"],
                     fg=C["text_light"]).pack(anchor="w", pady=(4, 0))

            # Linha 3: itens + total
            tk.Label(body,
                     text=f"{items_count} item(ns)  •  R$ {total:.2f}",
                     font=("Segoe UI", 10, "bold"),
                     bg=C["bg_dark"], fg="white").pack(anchor="w", pady=(4, 0))

            # Progresso (barra que some em 8s)
            prog_bg = tk.Frame(body, bg=C["text_muted"], height=3)
            prog_bg.pack(fill="x", pady=(10, 0))
            prog_fill = tk.Frame(prog_bg, bg=C["primary"], height=3)
            prog_fill.place(relwidth=1.0, relheight=1.0)

            DURATION_MS = 8000
            steps = 80
            step_ms = DURATION_MS // steps

            def _tick(step=0):
                if not toast.winfo_exists():
                    return
                ratio = 1.0 - (step / steps)
                prog_fill.place(relwidth=ratio, relheight=1.0)
                if step < steps:
                    toast.after(step_ms, lambda: _tick(step + 1))
                else:
                    toast.destroy()

            toast.after(step_ms, lambda: _tick(1))
        except Exception:
            pass

    # ── Utilitários ────────────────────────────────────────────────────────────
    def _beep(self):
        try:
            system = platform.system()
            if system == "Windows":
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            elif system == "Darwin":
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"],
                               capture_output=True)
            else:
                subprocess.run(
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                    capture_output=True)
        except Exception:
            pass

    def _hide_to_tray(self):
        self.root.withdraw()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit(self):
        self.stop_polling()
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass
        self.root.quit()
        sys.exit(0)

    # ── Bandeja do sistema ─────────────────────────────────────────────────────
    def _start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            size = 64
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 0, size-1, size-1], radius=12,
                                 fill=(255, 107, 53, 255))
            d.rectangle([10, 26, 54, 46], fill="white")
            d.rectangle([16, 14, 48, 28], fill="white")
            d.rectangle([22, 36, 42, 54], fill="white")
            d.rectangle([26, 40, 38, 50], fill=(255, 107, 53, 255))

            menu = pystray.Menu(
                pystray.MenuItem("Abrir painel",
                                 lambda: self.root.after(0, self._show_window),
                                 default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Sair", lambda: self.root.after(0, self._quit)),
            )
            self._tray_icon = pystray.Icon("fomezinha_print", img, APP_NAME, menu)
            self._tray_icon.run()
        except Exception:
            self._tray_icon = None
            self.root.after(0, self._show_window)

    # ── Run ────────────────────────────────────────────────────────────────────
    def run(self):
        self._tray_icon = None

        # Auto-login com tokens salvos se disponíveis
        if self.api.token and self.config.get("restaurant_id"):
            def _auto():
                try:
                    restaurants = self.api.get_restaurants()
                    if restaurants:
                        rest = restaurants[0] if isinstance(restaurants, list) else restaurants
                        name = rest.get("name", self.config.get("restaurant_name", ""))
                        self.connected = True
                        self.order_count = 0
                        self.log(f"Sessão restaurada — {name}")
                        self.root.after(0, lambda: self._show_main_screen(name))
                        self.root.after(100, self.start_polling)
                    else:
                        self.root.after(0, self._show_login_screen)
                except Exception:
                    # Token expirado — tenta refresh
                    try:
                        self.api.refresh()
                        restaurants = self.api.get_restaurants()
                        rest = (restaurants[0] if isinstance(restaurants, list)
                                else restaurants) if restaurants else None
                        if rest:
                            name = rest.get("name", self.config.get("restaurant_name", ""))
                            self.connected = True
                            self.order_count = 0
                            self.log(f"Sessão renovada — {name}")
                            self.root.after(0, lambda: self._show_main_screen(name))
                            self.root.after(100, self.start_polling)
                            return
                    except Exception:
                        pass
                    self.root.after(0, self._show_login_screen)

            threading.Thread(target=_auto, daemon=True).start()
        else:
            self.root.after(100, self._show_login_screen)

        tray_thread = threading.Thread(target=self._start_tray, daemon=True)
        tray_thread.start()

        self.root.mainloop()


# ─── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.run()
