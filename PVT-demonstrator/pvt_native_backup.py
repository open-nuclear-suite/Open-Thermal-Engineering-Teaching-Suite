"""Native, browser-free P-v-T teaching application.

Requires: numpy, matplotlib, CoolProp
Run: python pvt_native_app.py
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tkinter import ttk, messagebox

import numpy as np
from CoolProp.CoolProp import PropsSI
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from PIL import Image, ImageTk


ISOTHERM_COLOR = "#174EA6"


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
        self.title("P-v-T Surface Slicing Demonstrator")
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
            text="maxisnote20, 2026",
            anchor="center",
            padding=(8, 6),
            font=("", 9),
        ).pack(side="bottom", fill="x")

        left = ttk.Frame(self, padding=10)
        left.pack(side="left", fill="y")
        right = ttk.Frame(self)
        right.pack(side="right", expand=True, fill="both")

        logo_path = Path(__file__).with_name("hiref.logo.png")
        self.logo_image = None
        if logo_path.is_file():
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((285, 95), Image.Resampling.LANCZOS)
            self.logo_image = ImageTk.PhotoImage(logo)
            ttk.Label(left, image=self.logo_image).pack(anchor="center", pady=(0, 10))

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

        ttk.Label(left, text="Show").pack(anchor="w", pady=(12, 2))
        for text, var in (("Surface / two-phase fill", self.show_surface), ("Saturation boundary", self.show_sat),
                          ("Constant-pressure slice", self.show_p), ("Constant-temperature slice", self.show_t)):
            ttk.Checkbutton(left, text=text, variable=var, command=self.draw).pack(anchor="w")

        ttk.Button(left, text="Redraw", command=self.draw).pack(fill="x", pady=(15, 4))
        ttk.Button(left, text="Clear calculation cache", command=self.clear_cache).pack(fill="x")
        ttk.Label(left, text="Mouse: rotate/zoom with toolbar\n3D axes use log₁₀(v) and log₁₀(P).",
                  foreground="#555").pack(anchor="w", pady=(15, 0))

        self.fig = Figure(figsize=(10, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        toolbar = NavigationToolbar2Tk(self.canvas, right, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="top", fill="x")
        self.canvas.get_tk_widget().pack(expand=True, fill="both")
        self._job = None
        self.configure_ranges()
        self.after(50, self.draw)

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

    def draw(self):
        self._job = None
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
            X, Y = np.meshgrid(np.log10(vols), temps)
            if self.show_surface.get():
                ax.plot_surface(X, Y, np.log10(press), cmap="plasma", alpha=.68, linewidth=0, antialiased=True)
                if len(sat):
                    q = np.linspace(0, 1, 50)
                    vm = sat[:, 2, None] + q * (sat[:, 3, None] - sat[:, 2, None])
                    ax.plot_surface(np.log10(vm), np.repeat(sat[:, 0, None], len(q), 1),
                                    np.repeat(np.log10(sat[:, 1, None]), len(q), 1),
                                    color="#8dd35f", alpha=.30, linewidth=0)
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
            ax.view_init(25, -55)
        else:
            ax = self.fig.add_subplot(111)
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
    App().mainloop()
