"""Native, browser-free P-v-T teaching application.

Requires: numpy, matplotlib, CoolProp

Thermophysical properties are calculated using CoolProp:
Bell et al. (2014), https://doi.org/10.1021/ie4033999
Run: python pvt_native_app.py
"""
from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tkinter import ttk, messagebox

import numpy as np
import matplotlib as mpl
from CoolProp.CoolProp import PropsSI
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from PIL import Image, ImageTk


ISOTHERM_COLOR = "#174EA6"
ABOUT_TEXT = """We would be delighted to hear from educators, students, researchers, and other users of this software.

Please consider sending us a postcard or a short thank-you email describing:

• where you are using the software;
• how it is being used, such as for teaching, laboratory exercises, demonstrations, or self-study; and
• any comments or experiences you would like to share.

Postcards may be sent to:

Dean
Faculty of Mechanical Engineering
Universiti Teknologi Malaysia
81310 UTM Skudai
Johor
Malaysia

Email: mech@utm.my

Please mention that the software was developed by the Sustainable Energy & Reacting Flow Research Group, Universiti Teknologi Malaysia.

Your message will help us understand the educational reach of the software and encourage its continued development. Thank you for using our software!"""
ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
FKM_LOGO_PATH = ASSET_DIR / "utm.fkm.logo.png"
HIREF_LOGO_PATH = ASSET_DIR / "hiref.logo.png"
mpl.rcParams["axes3d.mouserotationstyle"] = "azel"


def logo_image(path, max_size):
    """Load a logo at an aspect-preserving size for a Tk widget."""
    if not path.is_file():
        return None
    image = Image.open(path).convert("RGBA")
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image)


class StartupSplash(tk.Tk):
    """Borderless FKM/HiREF startup panel shown for three seconds."""

    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.configure(background="#15181d", highlightbackground="#7d1238",
                       highlightthickness=3)
        self.attributes("-topmost", True)

        panel = tk.Frame(self, background="#15181d", padx=36, pady=28)
        panel.pack()

        self.fkm_image = logo_image(FKM_LOGO_PATH, (850, 140))
        if self.fkm_image:
            tk.Label(panel, image=self.fkm_image, background="#15181d").pack()
        else:
            tk.Label(
                panel, text="UTM Faculty of Mechanical Engineering",
                background="#7d1238", foreground="white",
                font=("", 24, "bold"), padx=10, pady=10,
            ).pack(fill="x")

        self.hiref_image = logo_image(HIREF_LOGO_PATH, (250, 155))
        if self.hiref_image:
            tk.Label(
                panel, image=self.hiref_image, background="#15181d"
            ).pack(pady=(10, 8))
        else:
            tk.Label(
                panel, text="HiREF", background="#15181d",
                foreground="white", font=("", 22, "bold"),
            ).pack(pady=(10, 8))

        tk.Label(
            panel, text="P-v-T Surface Slicing Demonstrator",
            background="#15181d", foreground="#f3f5f7",
            font=("", 21, "bold"),
        ).pack(pady=(2, 0))
        tk.Label(
            panel, text="Mohsin Mohd Sies, HiREF, UTM - 2026",
            background="#15181d", foreground="#c7d1db", font=("", 10),
        ).pack(pady=(5, 0))

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        self.after(3000, self.destroy)


@dataclass(frozen=True)
class Fluid:
    key: str
    label: str
    vmin: float
    vmax: float
    pmin: float
    pmax: float
    tmin: float
    tmax: float
    p0: float
    tc0: float


FLUIDS = {
    "Water": Fluid("Water", "Water / steam", 6e-4, 1e2, 7e-4, 80, 274, 820, .101325, 150),
    "R134a": Fluid("R134a", "R134a", 4.5e-4, 2, .005, 8, 180, 440, .7, 25),
    "CarbonDioxide": Fluid("CarbonDioxide", "Carbon dioxide / CO₂", 5e-4, .30, .50, 20, 218, 390, 5, 20),
    "Propane": Fluid("Propane", "Propane", 7e-4, 3, .005, 8, 190, 440, .9, 25),
    "Ammonia": Fluid("Ammonia", "Ammonia", 7e-4, 2, .01, 20, 200, 480, 1, 25),
}


def prop(output, a, av, b, bv, fluid):
    try:
        value = float(PropsSI(output, a, float(av), b, float(bv), fluid))
        return value if np.isfinite(value) else np.nan
    except Exception:
        return np.nan


@lru_cache(maxsize=10)
def fluid_data(key):
    f = FLUIDS[key]
    tcrit = float(PropsSI("Tcrit", f.key))
    pcrit = float(PropsSI("pcrit", f.key)) / 1e6
    vcrit = 1 / float(PropsSI("rhocrit", f.key))
    try:
        ttriple = float(PropsSI("Ttriple", f.key))
    except Exception:
        ttriple = f.tmin

    ts = np.linspace(max(f.tmin, ttriple + .05), min(f.tmax, tcrit - .05), 220)
    sat = []
    for t in ts:
        p = prop("P", "T", t, "Q", 0, f.key) / 1e6
        dl = prop("Dmass", "T", t, "Q", 0, f.key)
        dg = prop("Dmass", "T", t, "Q", 1, f.key)
        if np.isfinite(p * dl * dg) and f.pmin <= p <= f.pmax:
            vf, vg = 1 / dl, 1 / dg
            if f.vmin <= vf <= f.vmax and f.vmin <= vg <= f.vmax:
                sat.append((t - 273.15, p, vf, vg))
    sat = np.asarray(sat)

    temps = np.linspace(f.tmin, f.tmax, 70)
    vols = np.logspace(np.log10(f.vmin), np.log10(f.vmax), 100)
    pressure = np.full((len(temps), len(vols)), np.nan)
    for i, t in enumerate(temps):
        for j, v in enumerate(vols):
            p = prop("P", "T", t, "Dmass", 1 / v, f.key) / 1e6
            if np.isfinite(p) and p >= f.pmin:
                pressure[i, j] = min(p, f.pmax)
    return f, tcrit, pcrit, vcrit, sat, temps - 273.15, vols, pressure


def pressure_slice(key, p):
    f = FLUIDS[key]
    t = np.linspace(f.tmin, f.tmax, 180)
    points = []
    for tk in t:
        rho = prop("Dmass", "P", p * 1e6, "T", tk, f.key)
        if np.isfinite(rho) and rho > 0 and f.vmin <= 1 / rho <= f.vmax:
            points.append((1 / rho, tk - 273.15, p))
    return np.asarray(points)


def temperature_slice(key, tc):
    f = FLUIDS[key]
    tk = tc + 273.15
    points = []
    for p in np.logspace(np.log10(f.pmin), np.log10(f.pmax), 180):
        rho = prop("Dmass", "P", p * 1e6, "T", tk, f.key)
        if np.isfinite(rho) and rho > 0 and f.vmin <= 1 / rho <= f.vmax:
            points.append((1 / rho, tc, p))
    return np.asarray(points)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("P-v-T Surface Slicing Demonstrator — AZEL rotation")
        self.geometry("1350x850")
        self.minsize(1000, 650)

        self.fluid = tk.StringVar(value="Water")
        self.view = tk.StringVar(value="3D P-v-T")
        self.p = tk.DoubleVar(value=np.log10(FLUIDS["Water"].p0))
        self.tc = tk.DoubleVar(value=FLUIDS["Water"].tc0)
        self.show_surface = tk.BooleanVar(value=True)
        self.show_sat = tk.BooleanVar(value=True)
        self.show_p = tk.BooleanVar(value=True)
        self.show_t = tk.BooleanVar(value=True)

        ttk.Label(
            self,
            text="Mohsin Mohd Sies, Nuclear Engineering, 2026",
            anchor="center",
            padding=(8, 6),
            font=("", 9),
        ).pack(side="bottom", fill="x")

        header = tk.Frame(
            self, background="#0e1013",
            highlightbackground="#7d1238", highlightthickness=0,
        )
        header.pack(side="top", fill="x")
        header.configure(padx=14, pady=8)

        self.fkm_logo_image = logo_image(FKM_LOGO_PATH, (560, 70))
        self.hiref_logo_image = logo_image(HIREF_LOGO_PATH, (110, 70))
        if self.fkm_logo_image:
            tk.Label(
                header, image=self.fkm_logo_image, background="#0e1013"
            ).pack(side="left")
        else:
            tk.Label(
                header, text="UTM Faculty of Mechanical Engineering",
                background="#7d1238", foreground="white",
                font=("", 16, "bold"), padx=20, pady=8,
            ).pack(side="left")
        if self.hiref_logo_image:
            tk.Label(
                header, image=self.hiref_logo_image, background="#0e1013"
            ).pack(side="left", padx=(10, 0))
        else:
            tk.Label(
                header, text="HiREF", background="#0e1013",
                foreground="white", font=("", 16, "bold"),
            ).pack(side="left", padx=(10, 0))
        tk.Button(
            header, text="About", command=self.show_about,
            background="#7d1238", foreground="white",
            activebackground="#98204b", activeforeground="white",
            relief="flat", cursor="hand2", font=("", 10, "bold"),
            padx=16, pady=7,
        ).pack(side="right", padx=(14, 0))
        tk.Label(
            header, text="P-v-T Surface Slicing Demonstrator",
            background="#0e1013", foreground="#f3f5f7",
            font=("", 18, "bold"), anchor="e",
        ).pack(side="right", expand=True, fill="x")
        tk.Frame(self, background="#7d1238", height=3).pack(
            side="top", fill="x"
        )

        content = ttk.Frame(self)
        content.pack(expand=True, fill="both")
        left = ttk.Frame(content, padding=10)
        left.pack(side="left", fill="y")
        right = ttk.Frame(content)
        right.pack(side="right", expand=True, fill="both")

        ttk.Label(left, text="Controls", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(left, text="Fluid").pack(anchor="w", pady=(12, 2))
        box = ttk.Combobox(left, textvariable=self.fluid, state="readonly", values=list(FLUIDS), width=25)
        box.pack(fill="x")
        box.bind("<<ComboboxSelected>>", self.reset_fluid)

        ttk.Label(left, text="Pressure, log₁₀(P/MPa)").pack(anchor="w", pady=(12, 2))
        self.pscale = ttk.Scale(left, variable=self.p, command=lambda _: self.schedule())
        self.pscale.pack(fill="x")
        self.plabel = ttk.Label(left)
        self.plabel.pack(anchor="w")

        ttk.Label(left, text="Temperature, T [°C]").pack(anchor="w", pady=(12, 2))
        self.tscale = ttk.Scale(left, variable=self.tc, command=lambda _: self.schedule())
        self.tscale.pack(fill="x")
        self.tlabel = ttk.Label(left)
        self.tlabel.pack(anchor="w")

        ttk.Label(left, text="View").pack(anchor="w", pady=(12, 2))
        for name in ("3D P-v-T", "2D P-v", "2D T-v", "2D P-T"):
            ttk.Radiobutton(left, text=name, variable=self.view, value=name, command=self.draw).pack(anchor="w")

        ttk.Label(left, text="3D camera").pack(anchor="w", pady=(12, 2))
        cameras = ttk.Frame(left)
        cameras.pack(fill="x")
        for column, (text, elevation, azimuth) in enumerate((
            ("Reset", 25, -55), ("Front", 0, -90), ("Side", 0, 0),
            ("Top", 90, -90), ("Iso", 30, -45),
        )):
            ttk.Button(
                cameras,
                text=text,
                width=6,
                command=lambda e=elevation, a=azimuth: self.set_camera(e, a),
            ).grid(row=column // 3, column=column % 3, padx=1, pady=1, sticky="ew")

        ttk.Label(left, text="Show").pack(anchor="w", pady=(12, 2))
        for text, var in (("Surface / two-phase fill", self.show_surface), ("Saturation boundary", self.show_sat),
                          ("Constant-pressure slice", self.show_p), ("Constant-temperature slice", self.show_t)):
            ttk.Checkbutton(left, text=text, variable=var, command=self.draw).pack(anchor="w")

        ttk.Button(left, text="Redraw", command=self.draw).pack(fill="x", pady=(15, 4))
        ttk.Button(left, text="Clear calculation cache", command=self.clear_cache).pack(fill="x")
        ttk.Label(left, text="3D: left-drag rotates without roll.\nRight-drag zooms; presets reset the view.\nAxes use log₁₀(v) and log₁₀(P).",
                  foreground="#555").pack(anchor="w", pady=(15, 0))

        self.fig = Figure(figsize=(10, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        toolbar = NavigationToolbar2Tk(self.canvas, right, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="top", fill="x")
        self.canvas.get_tk_widget().pack(expand=True, fill="both")
        self._job = None
        self.ax = None
        self._camera = (25, -55, 0)
        self.configure_ranges()
        self.after(50, self.draw)

    def show_about(self):
        dialog = tk.Toplevel(self)
        dialog.title("About")
        dialog.geometry("660x620")
        dialog.minsize(520, 480)
        dialog.transient(self)
        dialog.grab_set()

        body = ttk.Frame(dialog, padding=20)
        body.pack(expand=True, fill="both")
        ttk.Label(
            body, text="Let Us Know Where This Software Is Used",
            font=("", 16, "bold"), anchor="center",
        ).pack(fill="x", pady=(0, 14))
        message = tk.Text(
            body, wrap="word", relief="flat", background=dialog.cget("background"),
            padx=4, pady=4, font=("", 10), cursor="arrow",
        )
        message.pack(expand=True, fill="both")
        message.insert("1.0", ABOUT_TEXT)
        email_start = message.search("mech@utm.my", "1.0")
        if email_start:
            email_end = f"{email_start}+{len('mech@utm.my')}c"
            message.tag_add("email", email_start, email_end)
            message.tag_config("email", foreground="#174EA6", underline=True)
            message.tag_bind(
                "email", "<Button-1>",
                lambda _event: webbrowser.open("mailto:mech@utm.my"),
            )
            message.tag_bind("email", "<Enter>", lambda _event: message.config(cursor="hand2"))
            message.tag_bind("email", "<Leave>", lambda _event: message.config(cursor="arrow"))
        message.config(state="disabled")
        ttk.Button(body, text="Close", command=dialog.destroy).pack(
            anchor="e", pady=(14, 0)
        )
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def configure_ranges(self):
        f = FLUIDS[self.fluid.get()]
        self.pscale.configure(from_=np.log10(f.pmin), to=np.log10(f.pmax))
        self.tscale.configure(from_=f.tmin - 273.15, to=f.tmax - 273.15)

    def reset_fluid(self, *_):
        f = FLUIDS[self.fluid.get()]
        self.p.set(np.log10(f.p0))
        self.tc.set(f.tc0)
        self.configure_ranges()
        self.draw()

    def schedule(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(120, self.draw)

    def clear_cache(self):
        fluid_data.cache_clear()
        self.draw()

    def set_camera(self, elevation, azimuth):
        if self.view.get() != "3D P-v-T" or self.ax is None:
            return
        self._camera = (elevation, azimuth, 0)
        self.ax.view_init(elev=elevation, azim=azimuth, roll=0)
        self.canvas.draw_idle()

    def draw(self):
        self._job = None
        # Preserve mouse-selected orientation when slider changes rebuild the
        # axes. Camera preset buttons remain the deliberate way to reset it.
        if self.ax is not None and getattr(self.ax, "name", "") == "3d":
            self._camera = (
                float(self.ax.elev),
                float(self.ax.azim),
                float(getattr(self.ax, "roll", 0)),
            )
        try:
            f, tcrit, pcrit, vcrit, sat, temps, vols, press = fluid_data(self.fluid.get())
        except Exception as exc:
            messagebox.showerror("Thermodynamic calculation failed", str(exc))
            return
        p0, tc0 = 10 ** self.p.get(), self.tc.get()
        self.plabel.configure(text=f"P = {p0:.6g} MPa")
        self.tlabel.configure(text=f"T = {tc0:.2f} °C")
        ps, ts = pressure_slice(f.key, p0), temperature_slice(f.key, tc0)
        self.fig.clear()
        view = self.view.get()

        if view == "3D P-v-T":
            ax = self.fig.add_subplot(111, projection="3d")
            self.ax = ax
            X, Y = np.meshgrid(np.log10(vols), temps)
            if self.show_surface.get():
                ax.plot_surface(X, Y, np.log10(press), cmap="plasma", alpha=.68, linewidth=0, antialiased=True)
                if len(sat):
                    q = np.linspace(0, 1, 50)
                    vm = sat[:, 2, None] + q * (sat[:, 3, None] - sat[:, 2, None])
                    ax.plot_surface(np.log10(vm), np.repeat(sat[:, 0, None], len(q), 1),
                                    np.repeat(np.log10(sat[:, 1, None]), len(q), 1),
                                    color="#8dd35f", alpha=.30, linewidth=0)

            xmin, xmax = np.log10(f.vmin), np.log10(f.vmax)
            ymin, ymax = f.tmin - 273.15, f.tmax - 273.15
            zmin, zmax = np.log10(f.pmin), np.log10(f.pmax)
            if self.show_p.get():
                plane_x, plane_y = np.meshgrid([xmin, xmax], [ymin, ymax])
                ax.plot_surface(
                    plane_x,
                    plane_y,
                    np.full_like(plane_x, np.log10(p0)),
                    color="#ff4f87",
                    alpha=.14,
                    edgecolor="#ff4f87",
                    linewidth=.6,
                    shade=False,
                )
            if self.show_t.get():
                plane_x, plane_z = np.meshgrid([xmin, xmax], [zmin, zmax])
                ax.plot_surface(
                    plane_x,
                    np.full_like(plane_x, tc0),
                    plane_z,
                    color=ISOTHERM_COLOR,
                    alpha=.12,
                    edgecolor=ISOTHERM_COLOR,
                    linewidth=.6,
                    shade=False,
                )

            if self.show_sat.get() and len(sat):
                ax.plot(np.log10(sat[:, 2]), sat[:, 0], np.log10(sat[:, 1]), color="#ff8c42", lw=2.5)
                ax.plot(np.log10(sat[:, 3]), sat[:, 0], np.log10(sat[:, 1]), color="#00b7d3", lw=2.5)
            if self.show_p.get() and len(ps):
                ax.plot(np.log10(ps[:, 0]), ps[:, 1], np.log10(ps[:, 2]), color="#ff4f87", lw=3)
            if self.show_t.get() and len(ts):
                ax.plot(np.log10(ts[:, 0]), ts[:, 1], np.log10(ts[:, 2]), color=ISOTHERM_COLOR, lw=3)
            ax.scatter(np.log10(vcrit), tcrit - 273.15, np.log10(pcrit), c="#7744cc", s=40)
            ax.set_xlabel("log₁₀(v / m³ kg⁻¹)")
            ax.set_ylabel("T [°C]")
            ax.set_zlabel("log₁₀(P / MPa)")
            ax.set_box_aspect((1.2, 1.0, 1.0))
            ax.view_init(elev=self._camera[0], azim=self._camera[1], roll=self._camera[2])
        else:
            ax = self.fig.add_subplot(111)
            self.ax = ax
            if view == "2D P-v":
                if self.show_surface.get() and len(sat):
                    ax.fill_between(sat[:, 2], sat[:, 1], f.pmin, color="#9ade72", alpha=.25)
                    ax.fill_between(sat[:, 3], sat[:, 1], f.pmin, color="#9ade72", alpha=.25)
                if self.show_sat.get() and len(sat):
                    ax.plot(sat[:, 2], sat[:, 1], "#ff8c42", lw=2); ax.plot(sat[:, 3], sat[:, 1], "#00b7d3", lw=2)
                if self.show_p.get() and len(ps): ax.plot(ps[:, 0], ps[:, 2], "#ff4f87", lw=3)
                if self.show_t.get() and len(ts): ax.plot(ts[:, 0], ts[:, 2], color=ISOTHERM_COLOR, lw=3)
                ax.set(xscale="log", yscale="log", xlabel="v [m³/kg]", ylabel="P [MPa]", xlim=(f.vmin, f.vmax), ylim=(f.pmin, f.pmax))
            elif view == "2D T-v":
                if self.show_sat.get() and len(sat):
                    ax.plot(sat[:, 2], sat[:, 0], "#ff8c42", lw=2); ax.plot(sat[:, 3], sat[:, 0], "#00b7d3", lw=2)
                if self.show_p.get() and len(ps): ax.plot(ps[:, 0], ps[:, 1], "#ff4f87", lw=3)
                if self.show_t.get() and len(ts): ax.plot(ts[:, 0], ts[:, 1], color=ISOTHERM_COLOR, lw=3)
                ax.set(xscale="log", xlabel="v [m³/kg]", ylabel="T [°C]", xlim=(f.vmin, f.vmax))
            else:
                if self.show_sat.get() and len(sat): ax.plot(sat[:, 0], sat[:, 1], "#00a6c6", lw=2.5)
                if self.show_p.get() and len(ps): ax.plot(ps[:, 1], ps[:, 2], "#ff4f87", lw=3)
                if self.show_t.get() and len(ts): ax.plot(ts[:, 1], ts[:, 2], color=ISOTHERM_COLOR, lw=3)
                ax.set(yscale="log", xlabel="T [°C]", ylabel="P [MPa]", ylim=(f.pmin, f.pmax))
            ax.grid(True, which="both", alpha=.25)
        ax.set_title(f"P-v-T surface slicing demonstrator — {f.label}")
        self.fig.tight_layout()
        self.canvas.draw_idle()


if __name__ == "__main__":
    StartupSplash().mainloop()
    App().mainloop()
