"""Separate P-v-T solid/fluid teaching demonstrator.

The fluid surface comes from the unchanged pvt_native_azel module.  Solid
properties and fusion coexistence sheets are qualitative engineering models;
for water the larger volume of ice and negative fusion-line slope reproduce
the characteristic folded solid+liquid region.
"""
from functools import lru_cache

import numpy as np
from CoolProp.CoolProp import PropsSI

from pvt_native_azel import App as FluidApp, FLUIDS, StartupSplash


# Tmin [K], solid density at triple point [kg/m3], solid expansion [1/K],
# solid compressibility [1/MPa], dTm/dP [K/MPa], liquid density [kg/m3].
SOLID_MODELS = {
    "Water": (220.0, 917.0, 1.5e-4, 1.2e-4, -0.074, 999.8),
    "R134a": (130.0, 1590.0, 3.5e-4, 1.0e-4, 0.20, 1410.0),
    "CarbonDioxide": (150.0, 1560.0, 2.5e-4, 8.0e-5, 0.10, 1180.0),
    "Propane": (60.0, 730.0, 4.0e-4, 1.5e-4, 0.30, 600.0),
    "Ammonia": (150.0, 820.0, 3.5e-4, 1.4e-4, 0.25, 680.0),
}


@lru_cache(maxsize=10)
def solid_phase_data(key):
    """Build the solid sheet and the folded solid-liquid coexistence sheet."""
    f = FLUIDS[key]
    tmin, rho_s, alpha_s, kappa_s, melt_slope, rho_l = SOLID_MODELS[key]
    ttriple = float(PropsSI("Ttriple", f.key))
    ptriple = float(PropsSI("ptriple", f.key)) / 1e6

    pressure = np.logspace(np.log10(max(f.pmin, ptriple)), np.log10(f.pmax), 70)
    tm = ttriple + melt_slope * (pressure - ptriple)

    # Solid single-phase sheet, terminating at the fusion line.
    fraction = np.linspace(0.0, 1.0, 55)[:, None]
    temperature = tmin + fraction * (tm[None, :] - tmin)
    pgrid = np.broadcast_to(pressure[None, :], temperature.shape)
    vs = (1.0 / rho_s) * (
        1.0 + alpha_s * (temperature - ttriple)
        - kappa_s * (pgrid - ptriple)
    )

    # Volumes on both sides of the fusion line.  Water is exceptional:
    # ice has the larger volume, so this ruled coexistence sheet folds back
    # toward the liquid surface as pressure rises.
    vs_fusion = (1.0 / rho_s) * (
        1.0 + alpha_s * (tm - ttriple) - kappa_s * (pressure - ptriple)
    )
    liquid_kappa = 4.6e-4 if key == "Water" else 8.0e-4
    liquid_alpha = -6.8e-5 if key == "Water" else 4.0e-4
    vl_fusion = (1.0 / rho_l) * (
        1.0 + liquid_alpha * (tm - ttriple)
        - liquid_kappa * (pressure - ptriple)
    )
    mix = np.linspace(0.0, 1.0, 35)[:, None]
    coexist_v = vl_fusion[None, :] + mix * (vs_fusion - vl_fusion)[None, :]
    coexist_t = np.broadcast_to((tm - 273.15)[None, :], coexist_v.shape)
    coexist_p = np.broadcast_to(pressure[None, :], coexist_v.shape)

    return {
        "solid_t": temperature - 273.15,
        "solid_p": pgrid,
        "solid_v": np.maximum(vs, 1e-8),
        "fold_t": coexist_t,
        "fold_p": coexist_p,
        "fold_v": np.maximum(coexist_v, 1e-8),
        "tm": tm - 273.15,
        "p": pressure,
        "vs": vs_fusion,
        "vl": vl_fusion,
    }


class SolidFluidApp(FluidApp):
    """Fluid demonstrator with separately overlaid solid and fusion sheets."""

    def __init__(self):
        super().__init__()
        self.title("P-v-T Solid + Fluid Demonstrator — folded fusion region")

    def configure_ranges(self):
        super().configure_ranges()
        f = FLUIDS[self.fluid.get()]
        self.tscale.configure(from_=SOLID_MODELS[f.key][0] - 273.15)

    def draw(self):
        super().draw()
        if self.ax is None:
            return
        f = FLUIDS[self.fluid.get()]
        d = solid_phase_data(f.key)
        view = self.view.get()

        if view == "3D P-v-T":
            self.ax.plot_surface(
                np.log10(d["solid_v"]), d["solid_t"], np.log10(d["solid_p"]),
                color="#244f86", alpha=.76, linewidth=.12,
                edgecolor="#173653", shade=True,
            )
            self.ax.plot_surface(
                np.log10(d["fold_v"]), d["fold_t"], np.log10(d["fold_p"]),
                color="#90b7d5", alpha=.88, linewidth=.18,
                edgecolor="#385f7c", shade=True,
            )
            self.ax.plot(np.log10(d["vs"]), d["tm"], np.log10(d["p"]),
                         color="#dcefff", lw=2.5)
            self.ax.plot(np.log10(d["vl"]), d["tm"], np.log10(d["p"]),
                         color="#f5fbff", lw=2.5)
            self.ax.set_ylim(SOLID_MODELS[f.key][0] - 273.15, f.tmax - 273.15)
        elif view == "2D P-v":
            self.ax.fill_betweenx(d["p"], d["vl"], d["vs"],
                                  color="#90b7d5", alpha=.55)
            self.ax.plot(d["vs"], d["p"], color="#244f86", lw=2.5)
            self.ax.plot(d["vl"], d["p"], color="#5f91b5", lw=2.5)
        elif view == "2D T-v":
            self.ax.fill_betweenx(d["tm"], d["vl"], d["vs"],
                                  color="#90b7d5", alpha=.55)
            self.ax.plot(d["vs"], d["tm"], color="#244f86", lw=2.5)
            self.ax.plot(d["vl"], d["tm"], color="#5f91b5", lw=2.5)
            self.ax.set_ylim(bottom=SOLID_MODELS[f.key][0] - 273.15)
        else:
            self.ax.plot(d["tm"], d["p"], color="#244f86", lw=3)

        qualifier = "folded ice + liquid sheet" if f.key == "Water" else "solid + liquid sheet"
        self.ax.set_title(f"P-v-T demonstrator — {f.label} ({qualifier}; approximate)")
        self.fig.tight_layout()
        self.canvas.draw_idle()


if __name__ == "__main__":
    StartupSplash().mainloop()
    SolidFluidApp().mainloop()
