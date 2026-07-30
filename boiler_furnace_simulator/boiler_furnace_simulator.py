import sys
import csv
import math
from pathlib import Path

# Water/steam property helpers in this teaching simulator are simplified
# approximations informed by IAPWS-IF97. They are not a complete, validated,
# or standards-conforming implementation of IAPWS-IF97.
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QCheckBox, QComboBox,
    QLineEdit, QSlider, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox, QTabWidget,
    QMessageBox, QInputDialog, QSizePolicy, QScrollArea, QToolButton, QFrame, QSplitter,
    QDialog
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


PROJECT_NAME = 'Live Boiler/Furnace Transient Simulator'
AUTHOR_LINE = 'Mohsin Mohd Sies, HiREF, UTM - 2026'
ASSET_DIR = Path(__file__).resolve().parent.parent
FKM_LOGO_PATH = ASSET_DIR / 'utm.fkm.logo.png'
HIREF_LOGO_PATH = ASSET_DIR / 'hiref.logo.png'


def logo_pixmap(path, max_width, max_height):
    """Load a logo without cropping or changing its aspect ratio."""
    if not path.is_file():
        return QPixmap()
    image = QPixmap(str(path))
    if image.isNull():
        return image
    return image.scaled(
        max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


class StartupSplash(QDialog):
    """Borderless UTM-branded startup panel displayed before the dashboard."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName('startupSplash')
        self.setStyleSheet(
            '#startupSplash { background:#15181d; border:3px solid #7d1238; }'
            'QLabel { color:#f3f5f7; background:transparent; }'
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(10)

        fkm_logo = QLabel()
        fkm_logo.setAlignment(Qt.AlignCenter)
        fkm_pixmap = logo_pixmap(FKM_LOGO_PATH, 850, 140)
        if fkm_pixmap.isNull():
            fkm_logo.setText('UTM Faculty of Mechanical Engineering')
            fkm_logo.setStyleSheet(
                'background:#7d1238; color:white; padding:10px;'
                'font-size:24px; font-weight:bold;'
            )
        else:
            fkm_logo.setPixmap(fkm_pixmap)
        layout.addWidget(fkm_logo)

        hiref_logo = QLabel()
        hiref_logo.setAlignment(Qt.AlignCenter)
        hiref_pixmap = logo_pixmap(HIREF_LOGO_PATH, 250, 155)
        if hiref_pixmap.isNull():
            hiref_logo.setText('HiREF')
            hiref_logo.setStyleSheet(
                'color:#f3f5f7; font-size:22px; font-weight:bold;'
            )
        else:
            hiref_logo.setPixmap(hiref_pixmap)
        layout.addWidget(hiref_logo)

        title = QLabel(PROJECT_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('font-size:21px; font-weight:bold;')
        layout.addWidget(title)

        subtitle = QLabel(AUTHOR_LINE)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet('color:#c7d1db; font-size:11px;')
        layout.addWidget(subtitle)
        self.adjustSize()


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fmt(v):
    if abs(v) >= 100 or abs(v - round(v)) < 1e-8:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.2f}"
    return f"{v:.3f}"


def lag(yold, yt, tau):
    return yold + (yt - yold) / max(tau, 1)


def shift(v, x):
    return v[1:] + [x]


def clean_csv(s):
    return str(s).replace(',', ';')


def water_dew_point_c(water_mole_fraction, total_pressure_kpa=101.325):
    """Return the flue-gas water dew point from its H2O partial pressure.

    The Magnus correlation is inverted using the wet-basis water mole fraction.
    It is suitable for the atmospheric-pressure stack conditions represented by
    this teaching simulator.
    """
    water_fraction = clamp(water_mole_fraction, 1e-9, 0.999999)
    water_partial_pressure = water_fraction * max(total_pressure_kpa, 1e-9)
    log_ratio = math.log(max(water_partial_pressure, 1e-9) / 0.61094)
    return 243.04 * log_ratio / (17.625 - log_ratio)


def IF97_Tsat_p(pMPa):
    pbar = pMPa * 10.0
    return (100 + 3.0 * (pbar - 1)) + 273.15


def IF97_hL_p(pMPa):
    Ts = IF97_Tsat_p(pMPa) - 273.15
    return 4.22 * Ts


def IF97_hV_p(pMPa):
    Ts = IF97_Tsat_p(pMPa) - 273.15
    return IF97_hL_p(pMPa) + max(1200, 2257 - 5 * (Ts - 100))


def IF97_h_pT(pMPa, TK):
    Ts = IF97_Tsat_p(pMPa)
    TC = TK - 273.15
    if TK <= Ts:
        return 4.22 * TC
    return IF97_hV_p(pMPa) + 2.3 * (TK - Ts)


def IF97_v_pT(pMPa, TK):
    Ts = IF97_Tsat_p(pMPa)
    if TK <= Ts:
        rho = max(650, 1000 - 0.35 * (TK - 273.15) + 8 * pMPa)
        return 1 / rho
    R = 0.4615
    return max(0.001, R * TK / max(pMPa * 1000, 1))


def IF97_T_ph(pMPa, h):
    hf = IF97_hL_p(pMPa)
    hg = IF97_hV_p(pMPa)
    Ts = IF97_Tsat_p(pMPa)
    if h <= hf:
        return h / 4.22 + 273.15
    if h < hg:
        return Ts
    return Ts + (h - hg) / 2.3


def IF97_region_pT(pMPa, TK):
    Ts = IF97_Tsat_p(pMPa)
    if TK <= Ts:
        return 'Region1/4-side'
    if TK < 1073.15:
        return 'Region2'
    return 'Region5'


def pi_ctrl(uold, pv, sp, kp, ki, previous_error, dt, umin, umax):
    """Velocity-form PI controller with simple saturation anti-windup."""
    e = sp - pv
    proportional_step = kp * (e - previous_error)
    integral_step = ki * e * dt
    candidate = uold + proportional_step + integral_step
    if (candidate > umax and e > 0) or (candidate < umin and e < 0):
        # Do not integrate farther into saturation.
        candidate = uold + proportional_step
    return clamp(candidate, umin, umax), e


def fuel_catalog():
    return [
        dict(name='Natural Gas', phase='gas', flow_unit='Nm3/hr', density=0.717, Nm3_to_kmol=0.04464, MW=16.8, C=1.00, H=4.00, O=0.00, S=0.00, LHV=838, note='Natural gas surrogate'),
        dict(name='Methane (CH4)', phase='gas', flow_unit='Nm3/hr', density=0.717, Nm3_to_kmol=0.04464, MW=16.04, C=1, H=4, O=0, S=0, LHV=802, note='Pure methane'),
        dict(name='Ethane (C2H6)', phase='gas', flow_unit='Nm3/hr', density=1.356, Nm3_to_kmol=0.04464, MW=30.07, C=2, H=6, O=0, S=0, LHV=1428, note='Pure ethane'),
        dict(name='Propane (C3H8)', phase='gas', flow_unit='Nm3/hr', density=1.967, Nm3_to_kmol=0.04464, MW=44.10, C=3, H=8, O=0, S=0, LHV=2043, note='Pure propane'),
        dict(name='n-Butane (C4H10)', phase='gas', flow_unit='Nm3/hr', density=2.48, Nm3_to_kmol=0.04464, MW=58.12, C=4, H=10, O=0, S=0, LHV=2658, note='Butane surrogate'),
        dict(name='LPG (60% C3H8 / 40% C4H10)', phase='gas', flow_unit='Nm3/hr', density=2.17, Nm3_to_kmol=0.04464, MW=49.71, C=3.4, H=8.8, O=0, S=0, LHV=2289, note='LPG surrogate'),
        dict(name='Hydrogen (H2)', phase='gas', flow_unit='Nm3/hr', density=0.0899, Nm3_to_kmol=0.04464, MW=2.016, C=0, H=2, O=0, S=0, LHV=242, note='Pure hydrogen'),
        dict(name='Carbon Monoxide (CO)', phase='gas', flow_unit='Nm3/hr', density=1.25, Nm3_to_kmol=0.04464, MW=28.01, C=1, H=0, O=1, S=0, LHV=283, note='Pure CO'),
        dict(name='Syngas (40H2/35CO/15CH4/10CO2)', phase='gas', flow_unit='Nm3/hr', density=0.90, Nm3_to_kmol=0.04464, MW=17.0, C=0.50, H=1.10, O=0.50, S=0, LHV=430, note='Syngas surrogate'),
        dict(name='Biogas (60CH4/40CO2)', phase='gas', flow_unit='Nm3/hr', density=1.20, Nm3_to_kmol=0.04464, MW=27.2, C=0.60, H=2.40, O=0.80, S=0, LHV=482, note='Biogas surrogate'),
        dict(name='Fuel Oil Surrogate', phase='liquid', flow_unit='kg/hr', density=960, Nm3_to_kmol=float('nan'), MW=167, C=12, H=23, O=0, S=0.02, LHV=7510, note='Heavy fuel oil surrogate'),
        dict(name='Diesel Surrogate', phase='liquid', flow_unit='kg/hr', density=830, Nm3_to_kmol=float('nan'), MW=170, C=12, H=23, O=0, S=0.01, LHV=7300, note='Diesel-like surrogate'),
        dict(name='Gasoline Surrogate (Iso-octane)', phase='liquid', flow_unit='kg/hr', density=740, Nm3_to_kmol=float('nan'), MW=114.23, C=8, H=18, O=0, S=0, LHV=5471, note='Iso-octane'),
        dict(name='Kerosene Surrogate', phase='liquid', flow_unit='kg/hr', density=800, Nm3_to_kmol=float('nan'), MW=156, C=11, H=24, O=0, S=0.005, LHV=4700, note='Kerosene surrogate'),
        dict(name='Coal Surrogate', phase='solid', flow_unit='kg/hr', density=1300, Nm3_to_kmol=float('nan'), MW=20.2, C=1.00, H=0.80, O=0.05, S=0.02, LHV=380, note='Coal pseudo-fuel'),
        dict(name='Biomass Surrogate', phase='solid', flow_unit='kg/hr', density=650, Nm3_to_kmol=float('nan'), MW=24.0, C=1.00, H=1.40, O=0.60, S=0.005, LHV=450, note='Biomass pseudo-fuel'),
        dict(name='Petcoke Surrogate', phase='solid', flow_unit='kg/hr', density=950, Nm3_to_kmol=float('nan'), MW=13.5, C=1.00, H=0.25, O=0.01, S=0.05, LHV=420, note='Petcoke pseudo-fuel'),
        dict(name='User-defined elemental fuel', phase='custom', flow_unit='kg/hr', density=900, Nm3_to_kmol=float('nan'), MW=30.0, C=1, H=4, O=0, S=0, LHV=900, note='User edits C/H/O/S/MW/LHV'),
        dict(name='User-defined gas mixture', phase='mixgas', flow_unit='Nm3/hr', density=1.0, Nm3_to_kmol=0.04464, MW=20.0, C=1, H=4, O=0, S=0, LHV=700, note='Edit gas species fractions'),
        dict(name='User-defined liquid blend', phase='mixliquid', flow_unit='kg/hr', density=850, Nm3_to_kmol=float('nan'), MW=160.0, C=11, H=22, O=0, S=0.01, LHV=5000, note='Edit liquid blend fractions'),
    ]


def default_mixture():
    return dict(CH4=60, C2H6=5, C3H8=5, H2=0, CO=0, CO2=25, N2=5, H2S=0)


def default_liquid_blend():
    return dict(FuelOil=40, Diesel=30, Gasoline=15, Kerosene=15)


def mixture_to_fuel(mix):
    x = [mix['CH4'], mix['C2H6'], mix['C3H8'], mix['H2'], mix['CO'], mix['CO2'], mix['N2'], mix['H2S']]
    x = [v / 100 for v in x]
    MWs = [16.04, 30.07, 44.10, 2.016, 28.01, 44.01, 28.014, 34.08]
    C = [1, 2, 3, 0, 1, 1, 0, 0]
    H = [4, 6, 8, 2, 0, 0, 0, 2]
    O = [0, 0, 0, 0, 1, 2, 0, 0]
    S = [0, 0, 0, 0, 0, 0, 0, 1]
    LHV = [802, 1428, 2043, 242, 283, 0, 0, 520]
    return dict(name='User-defined gas mixture', phase='mixgas', flow_unit='Nm3/hr', density=1.0, Nm3_to_kmol=0.04464, MW=sum(a*b for a, b in zip(x, MWs)), C=sum(a*b for a, b in zip(x, C)), H=sum(a*b for a, b in zip(x, H)), O=sum(a*b for a, b in zip(x, O)), S=sum(a*b for a, b in zip(x, S)), LHV=sum(a*b for a, b in zip(x, LHV)), note='Custom gas mixture')


def liquid_blend_to_fuel(mixl):
    x = [mixl['FuelOil'], mixl['Diesel'], mixl['Gasoline'], mixl['Kerosene']]
    x = [v / 100 for v in x]
    MWs = [167, 170, 114.23, 156]
    C = [12, 12, 8, 11]
    H = [23, 23, 18, 24]
    O = [0, 0, 0, 0]
    S = [0.02, 0.01, 0, 0.005]
    LHV = [7510, 7300, 5471, 4700]
    return dict(name='User-defined liquid blend', phase='mixliquid', flow_unit='kg/hr', density=850, Nm3_to_kmol=float('nan'), MW=sum(a*b for a, b in zip(x, MWs)), C=sum(a*b for a, b in zip(x, C)), H=sum(a*b for a, b in zip(x, H)), O=sum(a*b for a, b in zip(x, O)), S=sum(a*b for a, b in zip(x, S)), LHV=sum(a*b for a, b in zip(x, LHV)), note='Custom liquid blend')


def fuel_defaults(idx):
    fuel = fuel_catalog()[idx - 1]
    return dict(C=fuel['C'], H=fuel['H'], O=fuel['O'], S=fuel['S'], MW=fuel['MW'], LHV=fuel['LHV'], moist=0, ash=0)


def plant_calc_if97(p, state, phase, dens_on):
    """Simplified boiler/furnace model with flue-gas combustion diagnostics.

    This is not a detailed CFD/burner model. It is an operator-training model
    designed to make the important flue-gas trends visible:
      * too little air -> falling O2 and rapidly rising CO
      * too much air -> high O2, diluted CO2, larger stack loss
      * poor burner mixing -> CO can rise even when O2 looks acceptable
      * post-furnace air ingress -> measured O2 rises and CO2/CO are diluted
      * tube fouling -> higher stack temperature and poorer heat capture
    """
    nu_O2_st = max(p['C'] + p['H'] / 4 + p['S'] - p['O'] / 2, 1e-9)
    lambda_ = 1 + p['ea'] / 100
    phi = 1 / max(lambda_, 0.05)
    nf = p['nf']
    O2in = nf * lambda_ * nu_O2_st
    N2in = 3.76 * O2in

    # Carbon-to-CO fraction.  A low lambda causes a non-linear CO breakthrough.
    # Poor burner mixing adds CO even when measured O2 is not especially low.
    base_incomplete = 0.25 * max(0.0, 1.0 - clamp(p['eta_comb'], 0.80, 1.0))
    air_deficit = max(0.0, 1.04 - lambda_)
    rich_breakthrough = 0.42 * (air_deficit / 0.20) ** 1.45 if air_deficit > 0 else 0.0
    mixing_quality = clamp(p.get('burner_mixing', 95.0) / 100.0, 0.30, 1.00)
    mixing_penalty = 0.08 * (1.0 - mixing_quality) ** 1.35
    co_carbon_frac = clamp(base_incomplete + rich_breakthrough + mixing_penalty, 0.0, 0.85)
    ce = clamp(1.0 - co_carbon_frac, 0.15, 1.0)

    CO2 = nf * p['C'] * (1.0 - co_carbon_frac)
    CO = nf * p['C'] * co_carbon_frac
    combustion_water = nf * (p['H'] / 2)
    fuel_moisture_water = (
        p.get('fuel_mass_kgps', 0.0) * max(p.get('fuelmoist', 0.0), 0.0)
        / 0.018015
    )
    H2O = combustion_water + fuel_moisture_water
    SO2 = nf * p['S']
    O2used = nf * (p['C'] * (1.0 - co_carbon_frac) + 0.5 * p['C'] * co_carbon_frac + p['H'] / 4 + p['S'] - p['O'] / 2)
    O2out = max(O2in - O2used, 0)

    # Post-furnace leakage: adds air to the sample path/duct after combustion.
    dry_before_leak = max(CO2 + CO + O2out + N2in + SO2, 1e-12)
    combustion_dry_o2 = 100 * O2out / dry_before_leak
    leak_air = dry_before_leak * max(p.get('flue_air_leak', 0.0), 0.0) / 100.0
    O2_sample = O2out + 0.21 * leak_air
    N2_sample = N2in + 0.79 * leak_air
    dry = CO2 + CO + O2_sample + N2_sample + SO2
    flue_total = dry + H2O
    water_mole_fraction = H2O / max(flue_total, 1e-12)
    dew_point = water_dew_point_c(water_mole_fraction)
    dry_O2 = 100 * O2_sample / max(dry, 1e-12)
    dry_CO2 = 100 * CO2 / max(dry, 1e-12)
    dry_CO = 100 * CO / max(dry, 1e-12)
    co_ppm = dry_CO * 10000.0

    # Fouling reduces effective heat capture and raises stack temperature.
    fouling = clamp(p.get('tube_fouling', 0.0), 0.0, 100.0)
    effective_capture = clamp(p['capture'] * (1.0 - 0.0035 * fouling), 0.30, 0.95)
    qrel = nf * p['lhv'] * ce
    qwall = qrel * p['loss'] / 100
    qstack = (qrel - qwall) * (1 - effective_capture) + 0.25 * qrel * (0.10 + 0.0025 * max(p['ea'], 0) + 0.00018 * max(p['tair'] - 25, 0))
    qstack += 0.003 * qrel * max(p.get('flue_air_leak', 0.0), 0.0)  # extra warm dilution air effect
    qboiler = max(qrel - qwall - qstack, 0)
    eta = 100 * qboiler / max(nf * p['lhv'], 1e-12)
    tstack = max(85, 140 + 3.1 * max(p['ea'], 0) + 45 * (1 - effective_capture) + 120 * p['loss'] / 100 + 1.7 * fouling)

    # Teaching-level NOx estimate. This is a transparent trend model, not a
    # regulatory emissions calculation. Thermal NOx rises exponentially with a
    # flame-temperature proxy and available oxygen; fuel NOx scales with the
    # user-entered fuel nitrogen; prompt NOx represents a small hydrocarbon-rich
    # flame-front contribution. Downstream leakage dilutes measured ppm.
    flame_temp = clamp(
        1950
        + 0.35 * (p['tair'] - 25)
        + 0.15 * (p['tfuel'] - 25)
        - 2.2 * max(p['ea'], 0)
        - 260 * (1 - ce)
        - 160 * max(p.get('fuelmoist', 0.0), 0.0),
        900,
        2150,
    )
    # Use furnace-exit O2 for formation chemistry. Air entering downstream may
    # dilute the analyzer sample, but it cannot create additional thermal NOx.
    oxygen_factor = math.sqrt(max(combustion_dry_o2, 0.2) / 3.0)
    load_factor = clamp(p.get('demand', 1.0), 0.4, 1.35) ** 0.35
    thermal_nox = clamp(
        35
        * math.exp((flame_temp - 1700) / 220)
        * oxygen_factor
        * load_factor
        * (0.85 + 0.15 * mixing_quality),
        0,
        1500,
    )
    fuel_nox = 180 * max(p.get('fuel_nitrogen', 0.0), 0.0)
    prompt_nox = (
        12
        * clamp(p.get('C', 0.0), 0.0, 3.0)
        * (1.0 + 0.8 * (1.0 - mixing_quality))
    )
    nox_dilution = dry_before_leak / max(dry, 1e-12)
    nox_ppm = (thermal_nox + fuel_nox + prompt_nox) * nox_dilution
    nox_corrected_3pct = nox_ppm * (20.9 - 3.0) / max(20.9 - dry_O2, 1.0)

    # Teaching-level unburned-hydrocarbon estimate, reported as ppmC. The
    # estimate responds to incomplete/rich combustion, poor mixing, low flame
    # temperature, and the greater burnout challenge of liquid/solid fuels.
    richness = max(0.0, 1.05 - lambda_)
    quench_factor = clamp((1450 - flame_temp) / 450, 0.0, 1.0)
    phase_factor = {
        'gas': 1.0,
        'mixgas': 1.0,
        'liquid': 1.35,
        'mixliquid': 1.35,
        'solid': 1.75,
        'custom': 1.2,
    }.get(p.get('fuel_phase', 'gas'), 1.0)
    uhc_ppmc = phase_factor * (
        15
        + 8000 * co_carbon_frac ** 1.2
        + 12000 * richness ** 1.5
        + 2500 * (1.0 - mixing_quality) ** 1.4
        + 1200 * quench_factor
    ) * nox_dilution
    uhc_ppmc = clamp(uhc_ppmc, 0, 50000)

    P = p['pbar'] * 0.1
    Tsat = IF97_Tsat_p(P) - 273.15
    hf = IF97_hL_p(P)
    hg = IF97_hV_p(P)
    hfw = IF97_h_pT(P, p['tfw'] + 273.15)
    hspray = IF97_h_pT(P, p['tspray'] + 273.15)
    hsh_sp = IF97_h_pT(P, max(p['tsteam_sp'], Tsat + 5) + 273.15)
    rho_steam = max(0.5, 1 / IF97_v_pT(P, max(p['tsteam_sp'], Tsat + 5) + 273.15))
    rho_fw = max(50, 1 / IF97_v_pT(P, min(p['tfw'], Tsat - 2) + 273.15))
    steam_capacity = max(0.0, qboiler / max(hsh_sp - hfw, 300))
    if p.get('coordinated_firing', False):
        # Firing has already followed load demand, so generated steam is the
        # energy-supported capacity rather than demand-scaled a second time.
        msteam_target = steam_capacity
    else:
        # Manual/uncoordinated firing retains the training mismatch: steam
        # demand may differ from the heat being released by the furnace.
        msteam_target = max(0.0, p['demand'] * steam_capacity)
    qsteam_need = msteam_target * max(hsh_sp - hfw, 0)
    qeconom = 0.18 * qboiler
    qevap = 0.60 * qboiler
    qsh = 0.22 * qboiler
    h1 = hfw + qeconom / max(msteam_target, 1e-12)
    h2 = min(h1 + qevap / max(msteam_target, 1e-12), hg)
    hmid = h2 + qsh / max(msteam_target, 1e-12)
    tmid = max(Tsat, IF97_T_ph(P, hmid) - 273.15)
    sf = clamp(p['spray_manual'] / 100, 0, 0.35)
    hout = ((msteam_target * hmid) + (msteam_target * sf * hspray)) / max(msteam_target * (1 + sf), 1e-12)
    tout = max(Tsat, IF97_T_ph(P, hout) - 273.15)
    adequacy = 100 * qboiler / max(qsteam_need, 1e-12)
    msteam_actual = msteam_target * (1 + p['steam_ft_bias'] / 100)
    mfw_actual = p['fwcmd'] * (1 + p['fw_ft_bias'] / 100)
    steam_dp = p['steam_dp'] * (msteam_actual / 20.0) ** 2 * max(rho_steam, 0.5) / 5
    fw_dp = p['fw_dp'] * (mfw_actual / 20.0) ** 2 * max(rho_fw, 1) / 1000
    steam_noise = p['steam_ft_noise'] / 100 * msteam_actual * math.sin(1.7 * phase)
    fw_noise = p['fw_ft_noise'] / 100 * mfw_actual * math.cos(1.3 * phase)
    if dens_on == 1:
        # Invert the DP-generation relationships above so a healthy,
        # density-compensated transmitter reports the actual mass flow.
        msteam_comp = max(
            0,
            20
            * math.sqrt(
                max(steam_dp, 0)
                * 5
                / max(p['steam_dp'] * rho_steam, 1e-12)
            )
            + steam_noise,
        )
        mfw_comp_meas = max(
            0,
            20
            * math.sqrt(
                max(fw_dp, 0)
                * 1000
                / max(p['fw_dp'] * rho_fw, 1e-12)
            )
            + fw_noise,
        )
    else:
        msteam_comp = max(
            0, 20 * math.sqrt(max(steam_dp, 0) / max(p['steam_dp'], 1e-12))
            + steam_noise
        )
        mfw_comp_meas = max(
            0, 20 * math.sqrt(max(fw_dp, 0) / max(p['fw_dp'], 1e-12))
            + fw_noise
        )
    reg = IF97_region_pT(P, max(p['tsteam_sp'], Tsat + 5) + 273.15)
    return dict(o2=dry_O2, eta=eta, qboiler=qboiler, qsteam=qsteam_need, adequacy=adequacy, tstack=tstack, Tsat=Tsat, hf=hf, hg=hg, rho_steam=rho_steam, rho_fw=rho_fw, tmid=tmid, tsteam=tout, steam_capacity=steam_capacity, msteam_actual=msteam_actual, mfw_actual=mfw_actual, msteam_comp=msteam_comp, mfw_comp_meas=mfw_comp_meas, region=reg, stoair=nu_O2_st * 4.76 * nf, actair=O2in + N2in, dry_O2=dry_O2, dry_CO2=dry_CO2, dry_CO=dry_CO, co_ppm=co_ppm, uhc_ppmc=uhc_ppmc, lambda_=lambda_, phi=phi, ce=ce, flue_total=flue_total, water_mole_fraction=water_mole_fraction, dew_point=dew_point, flame_temp=flame_temp, thermal_nox=thermal_nox * nox_dilution, fuel_nox=fuel_nox * nox_dilution, prompt_nox=prompt_nox * nox_dilution, nox_ppm=nox_ppm, nox_corrected_3pct=nox_corrected_3pct, co_carbon_frac=co_carbon_frac, effective_capture=effective_capture, flue_air_leak=leak_air)

def select_mode(sel, model, p):
    if sel == 1:
        return 1, 'Single-element'
    if sel == 2:
        return 2, 'Two-element'
    if sel == 3:
        return 3, 'Three-element'
    if p['demand'] < 0.55:
        return 1, 'Auto->Single'
    if abs(p['steam_ft_bias']) > 7 or p['steam_ft_noise'] > 4:
        return 1, 'Auto fallback->Single'
    if abs(p['fw_ft_bias']) > 7 or p['fw_ft_noise'] > 4:
        return 2, 'Auto fallback->Two'
    if model['msteam_comp'] < 8:
        return 2, 'Auto->Two'
    return 3, 'Auto->Three'


def finite_vals(seq):
    return [v for v in seq if v is not None and not math.isnan(v)]


def padded_limits(values, fallback, min_span=1.0, pad_frac=0.08):
    vals = finite_vals(values)
    if not vals:
        return fallback
    lo = min(vals)
    hi = max(vals)
    if abs(hi - lo) < 1e-12:
        c = lo
        half = max(min_span / 2.0, abs(c) * pad_frac, 0.5)
        return (c - half, c + half)
    span = max(hi - lo, min_span)
    pad = span * pad_frac
    return (lo - pad, hi + pad)


def alarms_and_trip(s, p):
    ac = 0
    tc = 0
    alarm_txt = 'Normal'
    trip_txt = 'No trip'
    if s['drum'] <= p['lvl_ll']:
        ac = 1
        alarm_txt = 'Drum level LOW'
    if s['drum'] >= p['lvl_hh']:
        ac = 2
        alarm_txt = 'Drum level HIGH'
    if s['tstack'] >= p['stack_hh']:
        ac = 3
        alarm_txt = 'Stack temp HIGH'
    if s.get('dew_margin', math.inf) <= p.get('dew_margin_alarm', 15.0):
        ac = 4
        alarm_txt = 'Dew-point margin LOW'
    if s.get('fg_nox_ppm', 0.0) >= p.get('nox_alarm', 300.0):
        ac = 5
        alarm_txt = 'NOx emissions HIGH'
    if s.get('fg_uhc_ppmc', 0.0) >= p.get('uhc_alarm', 500.0):
        ac = 6
        alarm_txt = 'Unburned hydrocarbons HIGH'
    if s['tsteam'] >= p['ttrip'] or s['drum'] <= max(5, p['lvl_ll'] - 10) or s['drum'] >= min(95, p['lvl_hh'] + 10):
        tc = 1
        trip_txt = 'MASTER FUEL TRIP'
    return alarm_txt, trip_txt, ac, tc


class CollapsibleBox(QWidget):
    def __init__(self, title):
        super().__init__()
        self.button = QToolButton(text=title, checkable=True, checked=True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.DownArrow)
        self.button.clicked.connect(self.on_toggled)
        self.content = QWidget()
        self.content.setLayout(QVBoxLayout())
        self.content.layout().setContentsMargins(8, 4, 8, 8)
        self.content.layout().setSpacing(4)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.button)
        outer.addWidget(self.content)
        self.setStyleSheet("QToolButton { font-weight: bold; text-align: left; padding: 6px; background: #efefef; border: 1px solid #c7c7c7; }")

    def on_toggled(self):
        expanded = self.button.isChecked()
        self.button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)

    def layout(self):
        return self.content.layout()


class SliderRow(QWidget):
    def __init__(self, label, vmin, vmax, v0, step):
        super().__init__()
        self.vmin = float(vmin)
        self.vmax = float(vmax)
        self.step = float(step)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(QLabel(label))
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(int(round((self.vmax - self.vmin) / self.step)))
        self.slider.setValue(self.to_slider(v0))
        self.edit = QLineEdit(fmt(v0))
        self.edit.setFixedWidth(70)
        row.addWidget(self.slider)
        row.addWidget(self.edit)
        layout.addLayout(row)
        self.slider.valueChanged.connect(self.on_slider)
        self.edit.editingFinished.connect(self.on_edit)

    def to_slider(self, v):
        return int(round((float(v) - self.vmin) / self.step))

    def from_slider(self, i):
        return self.vmin + i * self.step

    def value(self):
        return self.from_slider(self.slider.value())

    def set_value(self, v):
        v = clamp(float(v), self.vmin, self.vmax)
        self.slider.blockSignals(True)
        self.slider.setValue(self.to_slider(v))
        self.slider.blockSignals(False)
        self.edit.setText(fmt(v))

    def on_slider(self):
        self.edit.setText(fmt(self.value()))

    def on_edit(self):
        try:
            v = float(self.edit.text())
        except Exception:
            v = self.value()
        self.set_value(v)


class BoilerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Live Boiler/Furnace Transient Simulator v56c5 - PyQt Demo Mode')
        self.resize(1780, 980)
        self.dt = 0.25
        self.tick = 0
        self.running = False
        self.log_enabled = False
        self.log_file = 'boiler_transient_log.csv'
        self.demo_active = False
        self.demo_stage = None
        self.demo_start_sim_time = 0.0
        self.demo_message = 'Demo mode off.'
        self.fault_baseline = None
        self.active_fault_name = None
        self.hist_n = 360
        # Rolling simulated-time window: oldest sample is negative and the
        # newest/current sample is at 0 s.
        self.hist_t = [
            (i - (self.hist_n - 1)) * self.dt for i in range(self.hist_n)
        ]
        self.fuel_db = fuel_catalog()
        self.fuels = [f['name'] for f in self.fuel_db]
        self.mix = default_mixture()
        self.mixl = default_liquid_blend()
        self.mem = dict(
            int_o2=0, int_ot=0, int_it=0, int_lvl=0, int_fic=0,
            lvltrim=0, mid_sp=440, phase=0,
        )
        self.state = dict(o2=3, eta=80, qboiler=0, qsteam=0, adequacy=100, tstack=180, dew_point=55, dew_margin=125, flame_temp=1900, nox_corrected_3pct=120, steam_capacity=0.30, fuel_balance_pct=100, fuel_warning=False, fuel_warn_time=0, firing_factor=1.0, actual_fuel_user_flow=100, tmid=450, tsteam=440, instab=0, drum=50, drum_inventory=50, swell=0, previous_steamflow=0.30, steamflow=0.30, fwflow=0.30, spray=0, trip=0, alarm=0, fwvalve=0.30, sim_time=0, realtime=0, fuel_user_flow=100, fuel_nmolps=1, fuel_unit='Nm3/hr', fg_o2=3, fg_co2=9, fg_co_ppm=300, fg_nox_ppm=120, fg_uhc_ppmc=30, fg_stack=180)
        self.hist = {k: [math.nan] * self.hist_n for k in ['eta', 'ad', 'drum', 'steam', 'fw', 'tsteam', 'tstack', 'air', 'spray', 'inst', 'fwsp', 'mode', 'fg_o2', 'fg_co2', 'fg_co_ppm', 'fg_nox_ppm', 'fg_uhc_ppmc']}
        self.rows = {}
        self.out = {}
        self.conv = {}
        self.diag = {}
        self.fg = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.run_loop)
        self.build_ui()
        self.reset_cb()

    def build_ui(self):
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(8, 8, 8, 8)
        central_layout.setSpacing(8)
        self.setCentralWidget(central)

        header = QFrame()
        header.setStyleSheet(
            'QFrame { background:#0e1013; border-bottom:3px solid #7d1238; }'
            'QLabel { background:transparent; color:#f3f5f7; }'
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)

        logo_group = QHBoxLayout()
        logo_group.setSpacing(10)

        self.fkm_logo = QLabel()
        self.fkm_logo.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        dashboard_fkm_logo = logo_pixmap(FKM_LOGO_PATH, 560, 70)
        if dashboard_fkm_logo.isNull():
            self.fkm_logo.setText('UTM Faculty of Mechanical Engineering')
            self.fkm_logo.setStyleSheet(
                'background:#7d1238; color:white; padding:8px 20px;'
                'font-size:16px; font-weight:bold;'
            )
        else:
            self.fkm_logo.setPixmap(dashboard_fkm_logo)
        logo_group.addWidget(self.fkm_logo)

        self.hiref_logo = QLabel()
        self.hiref_logo.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        dashboard_hiref_logo = logo_pixmap(HIREF_LOGO_PATH, 110, 70)
        if dashboard_hiref_logo.isNull():
            self.hiref_logo.setText('HiREF')
            self.hiref_logo.setStyleSheet(
                'color:#f3f5f7; font-size:16px; font-weight:bold;'
            )
        else:
            self.hiref_logo.setPixmap(dashboard_hiref_logo)
        logo_group.addWidget(self.hiref_logo)
        header_layout.addLayout(logo_group, 0)

        branding = QVBoxLayout()
        title = QLabel(PROJECT_NAME)
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title.setStyleSheet('font-size:18px; font-weight:bold;')
        author = QLabel(AUTHOR_LINE)
        author.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        author.setStyleSheet('color:#c7d1db; font-size:11px;')
        branding.addWidget(title)
        branding.addWidget(author)
        header_layout.addLayout(branding, 1)
        central_layout.addWidget(header, 0)

        splitter = QSplitter(Qt.Horizontal)
        central_layout.addWidget(splitter, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_host = QWidget()
        left_scroll.setWidget(left_host)
        left = QVBoxLayout(left_host)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_host = QWidget()
        right_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_scroll.setWidget(right_host)
        right = QVBoxLayout(right_host)
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(8)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right_scroll)
        splitter.setSizes([1150, 620])

        self.combustion_box = CollapsibleBox('Combustion inputs')
        self.steam_box = CollapsibleBox('Steam-side + IF97 state inputs')
        self.control_box = CollapsibleBox('Control, compensation, alarms')
        left.addWidget(self.combustion_box)
        left.addWidget(self.steam_box)
        left.addWidget(self.control_box)

        self.build_combustion()
        self.build_steam()
        self.build_control()

        left.addWidget(self.build_measurements())
        self.status = QLabel('Live transient simulator ready.')
        self.status.setStyleSheet('background:#dbeaf7; padding:8px;')
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        left.addStretch(1)

        self.runtime_panel = self.build_runtime()
        self.fault_panel = self.build_fault_injection()
        self.notebook_panel = self.build_notebook()
        right.addWidget(self.runtime_panel, 0)
        right.addWidget(self.fault_panel, 0)
        right.addWidget(self.notebook_panel, 1)
        right.setStretch(0, 0)
        right.setStretch(1, 1)

    def make_group(self, title):
        g = QGroupBox(title)
        g.setLayout(QVBoxLayout())
        g.layout().setSpacing(4)
        return g

    def add_row(self, group, label, key, vmin, vmax, v0, step):
        row = SliderRow(label, vmin, vmax, v0, step)
        group.layout().addWidget(row)
        self.rows[key] = row

    def build_combustion(self):
        self.fuel_popup = QComboBox()
        self.fuel_popup.addItems(self.fuels)
        self.fuel_popup.currentIndexChanged.connect(self.fuel_cb)
        self.lock_comp = QCheckBox('Lock to preset fuel')
        self.lock_comp.setChecked(True)
        self.lock_comp.stateChanged.connect(self.fuel_cb)
        gas_btn = QPushButton('Edit gas mixture')
        gas_btn.clicked.connect(self.mixture_cb)
        liq_btn = QPushButton('Edit liquid blend')
        liq_btn.clicked.connect(self.liquid_blend_cb)
        self.fuel_info = QLabel('Fuel info: --')
        self.fuel_info.setStyleSheet('background:#e5f2fa; padding:6px;')
        self.fuel_info.setWordWrap(True)
        for w in [self.fuel_popup, self.lock_comp, gas_btn, liq_btn, self.fuel_info]:
            self.combustion_box.layout().addWidget(w)
        for spec in [('Fuel flow','fuel_flow_user',1,50000,100,0.01),('Excess air base (%)','ea',0,150,15,0.01),('Air temp (C)','tair',0,350,25,0.01),('Fuel temp (C)','tfuel',0,200,25,0.01),('Combustion completeness','eta_comb',0.80,1.0,0.99,0.005),('Wall loss (%)','loss',0,15,3,0.01),('Heat capture factor','capture',0.40,0.95,0.82,0.01),('Mixture LHV','lhv',50,50000,802,0.01),('C atoms/mol fuel','C',0,20,1,0.01),('H atoms/mol fuel','H',0,40,4,0.01),('O atoms/mol fuel','O',0,12,0,0.01),('S atoms/mol fuel','S',0,2,0,0.01),('Fuel MW (kg/kmol)','mwfuel',2,250,16.043,0.01),('Fuel moisture frac','fuelmoist',0,0.40,0,0.01),('Fuel nitrogen (wt%)','fuel_nitrogen',0,3,0.05,0.01),('Fuel ash frac','fuelash',0,0.50,0,0.01)]:
            self.add_row(self.combustion_box, *spec)

    def build_steam(self):
        for spec in [('Drum pressure (bar)','pbar',5,180,45,0.01),('Feedwater inlet T (C)','tfw',20,250,105,0.01),('Feedwater valve / cmd','fwcmd',0,120,0.30,0.01),('Steam outlet T setpoint (C)','tsteam_sp',180,620,440,0.01),('Steam demand factor','demand',0.40,1.35,1.0,0.01),('Spray water T (C)','tspray',20,220,105,0.01),('Manual spray (%)','spray_manual',0,35,0,0.01),('Drum level SP (%)','lvl_sp',30,70,50,0.01),('Initial drum level (%)','lvl_init',20,80,50,0.01),('Steam FT bias (%)','steam_ft_bias',-10,10,0,0.01),('FW FT bias (%)','fw_ft_bias',-10,10,0,0.01),('Steam FT noise (%)','steam_ft_noise',0,5,0.5,0.01),('FW FT noise (%)','fw_ft_noise',0,5,0.5,0.01),('Steam DP signal','steam_dp',0.1,5.0,1.0,0.01),('FW DP signal','fw_dp',0.1,5.0,1.0,0.01)]:
            self.add_row(self.steam_box, *spec)

    def build_control(self):
        for spec in [('O2 setpoint (%)','o2_sp',1,8,3,0.01),('Air PI Kp','air_kp',0,8,1.6,0.01),('Air PI Ki','air_ki',0,1.0,0.12,0.01),('Outer steam PI Kp','out_kp',0,8,1.0,0.01),('Outer steam PI Ki','out_ki',0,1.0,0.06,0.01),('Inner spray PI Kp','in_kp',0,8,1.5,0.01),('Inner spray PI Ki','in_ki',0,1.0,0.12,0.01),('Level PI Kp','lvl_kp',0,5,0.8,0.01),('Level PI Ki','lvl_ki',0,0.5,0.05,0.01),('Flow PI Kp','fw_kp',0,5,0.35,0.01),('Flow PI Ki','fw_ki',0,0.5,0.08,0.01),('Mid-temp bias (C)','mid_bias',5,80,30,0.01),('LL drum alarm (%)','lvl_ll',5,45,25,0.01),('HH drum alarm (%)','lvl_hh',55,95,75,0.01),('Steam T HH trip (C)','ttrip',350,650,540,0.01),('Stack T HH alarm (C)','stack_hh',150,450,280,0.01),('Minimum dew-point margin (C)','dew_margin_alarm',0,50,15,0.5),('NOx high alarm (ppm)','nox_alarm',50,1500,300,1),('UHC high alarm (ppmC)','uhc_alarm',50,10000,500,10),('Fuel/FW warning margin (%)','fuel_warn_margin',0,50,10,1),('Fuel/FW warning delay (s)','fuel_warn_delay',1,60,10,1),('Burner mixing quality (%)','burner_mixing',30,100,95,0.01),('Post-furnace air leak (%)','flue_air_leak',0,80,0,0.01),('Tube fouling / soot (%)','tube_fouling',0,100,0,0.01),('Analyzer lag (s)','analyzer_lag',0.5,30,8,0.01),('Analyzer noise level','analyzer_noise',0,5,0.5,0.01)]:
            self.add_row(self.control_box, *spec)

    def make_value_label(self):
        lab = QLabel('--')
        lab.setStyleSheet('background:white; padding:3px;')
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lab

    def build_measurements(self):
        g = QGroupBox('Measurements / indications')
        grid = QGridLayout(g)
        left_items = [('Region guess','region'),('Sat T (C)','tsat'),('h_f (kJ/kg)','hf'),('h_g (kJ/kg)','hg'),('rho_steam (kg/m3)','rhos'),('rho_fw (kg/m3)','rhof'),('Steam flow actual (kg/s)','msteam'),('Steam flow comp (kg/s)','msteamc'),('FW flow actual (kg/s)','mfw'),('FW flow comp (kg/s)','mfwc'),('Drum level (%)','drum'),('Drum mode active','mode'),('Dry O2 (%)','o2')]
        right_items = [('Efficiency (%)','eta'),('Boiler heat (kW)','qboiler'),('Steam duty need (kW)','qsteam'),('Adequacy (%)','ad'),('Fuel-supported steam cap. (kg/s)','steamcap'),('Fuel/FW adequacy (%)','fuelbalance'),('Mid steam T (C)','tmid'),('Final steam T (C)','tsteam'),('Stack T (C)','tstack'),('Spray cmd (%)','spray'),('FW demand SP','fwsp'),('FW valve cmd','fwvalve'),('Alarm state','alarm'),('Trip state','trip'),('Fuel basis rate','fuelrate')]
        for i, (lab, key) in enumerate(left_items):
            grid.addWidget(QLabel(lab), i, 0)
            self.out[key] = self.make_value_label()
            grid.addWidget(self.out[key], i, 1)
        for i, (lab, key) in enumerate(right_items):
            grid.addWidget(QLabel(lab), i, 2)
            self.out[key] = self.make_value_label()
            grid.addWidget(self.out[key], i, 3)
        return g

    def build_runtime(self):
        g = QGroupBox('Live run, mode, logging')
        grid = QGridLayout(g)
        self.mode_popup = QComboBox()
        self.mode_popup.addItems(['Single-element', 'Two-element', 'Three-element', 'Auto-select'])
        self.mode_popup.setCurrentIndex(3)
        self.auto_air = QCheckBox('Auto O2 trim')
        self.auto_air.setChecked(True)
        self.auto_steam = QCheckBox('Auto cascade steam-T')
        self.auto_steam.setChecked(True)
        self.dens_comp = QCheckBox('Density compensation ON')
        self.dens_comp.setChecked(True)
        self.bumpless = QCheckBox('Bumpless mode switching')
        self.bumpless.setChecked(True)
        self.coordinated_firing = QCheckBox('Coordinated firing follows steam demand')
        self.coordinated_firing.setChecked(True)
        self.speed_popup = QComboBox()
        self.speed_popup.addItems(['0.5x', '1x', '2x', '5x'])
        self.speed_popup.setCurrentIndex(1)
        self.log_check = QCheckBox('Enable CSV logging')
        self.log_check.stateChanged.connect(self.toggle_log_cb)
        self.log_name = QLineEdit(self.log_file)
        grid.addWidget(self.mode_popup, 0, 0, 1, 2)
        grid.addWidget(self.auto_air, 1, 0)
        grid.addWidget(self.auto_steam, 1, 1)
        grid.addWidget(self.dens_comp, 2, 0)
        grid.addWidget(self.bumpless, 2, 1)
        grid.addWidget(self.coordinated_firing, 2, 2, 1, 2)
        grid.addWidget(QLabel('Speed'), 3, 0)
        grid.addWidget(self.speed_popup, 3, 1)
        grid.addWidget(self.log_check, 3, 2)
        grid.addWidget(self.log_name, 3, 3)
        btns = [
            ('Start', self.start_cb), ('Pause', self.pause_cb), ('Resume', self.resume_cb),
            ('Step', self.step_cb), ('Reset', self.reset_cb), ('Load Case', self.case_cb),
            ('Start Demo', self.start_demo_cb),
            ('Stop Demo', self.stop_demo_cb), ('Clear Trends', self.clear_cb),
            ('Export Log', self.export_log_cb), ('Reset Trip', self.trip_reset_cb),
            ('Demand +10%', self.disturb_demand_up_cb), ('Demand -10%', self.disturb_demand_dn_cb),
            ('Fuel quality -5%', self.disturb_lhv_cb)
        ]
        for i, (txt, cb) in enumerate(btns):
            b = QPushButton(txt)
            b.clicked.connect(cb)
            grid.addWidget(b, 4 + i // 7, i % 7)
        self.time_box = QLabel('Sim t = 0.0 s | Wall t = 0.0 s | Paused')
        self.time_box.setStyleSheet('background:#e0ebf7; padding:6px;')
        grid.addWidget(self.time_box, 7, 0, 1, 7)
        self.demo_box = QLabel('Demo mode: off. Click Start Demo for a guided tour of boiler response, flue-gas diagnosis, and fault interpretation.')
        self.demo_box.setWordWrap(True)
        self.demo_box.setStyleSheet('background:#f0f7ff; padding:8px; border:1px solid #bdd7ee;')
        grid.addWidget(self.demo_box, 8, 0, 1, 7)
        return g

    def fault_case_definitions(self):
        """Faults that map directly to the simulator's available physics."""
        return [
            {
                'name': 'Air-starved firing / damper stuck closed',
                'description': 'Cuts excess air and degrades mixing. Expect low O2, sharp CO breakthrough, reduced combustion efficiency, and possible instability.',
                'values': {'ea': 0, 'burner_mixing': 80},
                'auto_air': False,
            },
            {
                'name': 'Excess air / damper stuck open',
                'description': 'Forces excessive combustion air. Expect high O2, diluted CO2, higher stack loss, and lower boiler efficiency.',
                'values': {'ea': 45, 'burner_mixing': 96},
                'auto_air': False,
            },
            {
                'name': 'Poor burner mixing / register maldistribution',
                'description': 'Reduces burner mixing quality while retaining reasonable excess air. Expect elevated CO despite an apparently acceptable O2 reading.',
                'values': {'ea': 15, 'burner_mixing': 50},
                'auto_air': False,
            },
            {
                'name': 'Flame quench / incomplete hydrocarbon burnout',
                'description': 'Reduces combustion completeness and mixing. Expect UHC and CO to rise, indicating incomplete burnout rather than a soot calculation.',
                'values': {'eta_comb': 0.90, 'burner_mixing': 60},
            },
            {
                'name': 'Post-furnace duct or casing air leak',
                'description': 'Adds air downstream of combustion. Expect analyzer O2 to rise while CO2 and CO are diluted; the extra air does not improve the flame.',
                'values': {'ea': 15, 'flue_air_leak': 35},
                'auto_air': False,
            },
            {
                'name': 'Tube fouling / soot deposition',
                'description': 'Reduces effective heat capture. Expect rising stack temperature, falling efficiency, and a maintenance-oriented diagnosis.',
                'values': {'tube_fouling': 65},
            },
            {
                'name': 'O2/CO analyzer sluggish and noisy',
                'description': 'Applies severe analyzer lag and noise. True combustion is unchanged, but displayed flue readings respond slowly and fluctuate.',
                'values': {'analyzer_lag': 25, 'analyzer_noise': 4.5},
            },
            {
                'name': 'Steam-flow transmitter negative drift',
                'description': 'Biases the steam-flow signal low and adds noise. Auto-select should fall back from three-element control when the signal becomes unreliable.',
                'values': {'steam_ft_bias': -10, 'steam_ft_noise': 4.5},
                'mode_index': 3,
            },
            {
                'name': 'Feedwater-flow transmitter positive drift',
                'description': 'Biases the feedwater-flow signal high and adds noise. Expect incorrect valve action or automatic fallback to a simpler drum-level strategy.',
                'values': {'fw_ft_bias': 10, 'fw_ft_noise': 4.0},
                'mode_index': 3,
            },
            {
                'name': 'Fuel heating-value loss',
                'description': 'Reduces the current fuel LHV by 15%. Expect lower released heat, reduced steam capability, and falling adequacy at unchanged fuel flow.',
                'values': {},
                'lhv_scale': 0.85,
            },
            {
                'name': 'Excess firing at low steam demand',
                'description': 'Drops steam demand to 45% while leaving firing uncoordinated at its full setting. Expect rising steam temperature and spray demand, followed by a high-temperature trip if uncorrected.',
                'values': {'demand': 0.45},
                'coordinated_firing': False,
            },
            {
                'name': 'High fuel-nitrogen / NOx excursion',
                'description': 'Raises fuel nitrogen to 1.5 wt%. Expect the fuel-NOx component, total analyzer NOx, and corrected NOx output to rise toward or above the alarm.',
                'values': {'fuel_nitrogen': 1.50},
            },
            {
                'name': 'Wet fuel / elevated flue-water loading',
                'description': 'Raises fuel moisture to 30%. Expect a higher water dew point and a smaller stack-to-dew-point safety margin.',
                'values': {'fuelmoist': 0.30},
            },
        ]

    def build_fault_injection(self):
        g = QGroupBox('Fault injection')
        layout = QVBoxLayout(g)
        self.fault_cases = self.fault_case_definitions()
        self.fault_popup = QComboBox()
        self.fault_popup.addItems([case['name'] for case in self.fault_cases])
        self.fault_popup.currentIndexChanged.connect(self.update_fault_description)
        layout.addWidget(self.fault_popup)

        self.fault_info = QLabel()
        self.fault_info.setWordWrap(True)
        self.fault_info.setStyleSheet(
            'background:#fff7df; padding:8px; border:1px solid #dfc77d;'
        )
        layout.addWidget(self.fault_info)

        buttons = QHBoxLayout()
        inject = QPushButton('Inject selected fault')
        inject.clicked.connect(self.inject_fault_cb)
        clear = QPushButton('Clear injected fault')
        clear.clicked.connect(self.clear_fault_cb)
        buttons.addWidget(inject)
        buttons.addWidget(clear)
        layout.addLayout(buttons)
        self.update_fault_description()
        return g

    def update_fault_description(self):
        if not hasattr(self, 'fault_cases'):
            return
        case = self.fault_cases[self.fault_popup.currentIndex()]
        prefix = (
            f"ACTIVE: {self.active_fault_name}\n\n"
            if self.active_fault_name else ''
        )
        self.fault_info.setText(prefix + case['description'])

    def build_notebook(self):
        g = QGroupBox('Notebook view')
        g.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(g)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Give the notebook a useful initial height, but allow it to grow with
        # the main window. Individual tabs keep their own scroll bars.
        self.tabs.setMinimumHeight(620)
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self.build_trends_tab(), 'Trends')
        self.tabs.addTab(self.build_diag_tab(), 'Diagnostics')
        self.tabs.addTab(self.build_flue_tab(), 'Flue Gas')
        self.tabs.addTab(self.build_alarm_tab(), 'Alarms')
        return g

    def build_trends_tab(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        self.fig = Figure(figsize=(7.6, 10.5), dpi=100, constrained_layout=True)
        gs = self.fig.add_gridspec(3, 1, hspace=0.30)
        self.ax1 = self.fig.add_subplot(gs[0, 0])
        self.ax2 = self.fig.add_subplot(gs[1, 0])
        self.ax3 = self.fig.add_subplot(gs[2, 0])

        self.ax1.set_title('Efficiency / adequacy / drum', pad=10)
        self.ax1.grid(True)
        self.ax1.set_xlim(self.hist_t[0], self.hist_t[-1])
        self.ax1.set_xlabel('Time before present (simulated s)')
        self.ax1.set_ylim(0, 120)
        self.l1, = self.ax1.plot(self.hist_t, self.hist['eta'], 'b-', linewidth=2, label='Efficiency')
        self.l2, = self.ax1.plot(self.hist_t, self.hist['ad'], 'g-', linewidth=2, label='Adequacy')
        self.l3, = self.ax1.plot(self.hist_t, self.hist['drum'], 'k--', linewidth=2, label='Drum')
        self.ax1.legend(loc='upper right', fontsize=8)

        self.ax2.set_title('Steam T / stack T', pad=10)
        self.ax2.grid(True)
        self.ax2.set_xlim(self.hist_t[0], self.hist_t[-1])
        self.ax2.set_xlabel('Time before present (simulated s)')
        self.ax2.set_ylim(0, 650)
        self.l4, = self.ax2.plot(self.hist_t, self.hist['tsteam'], 'r-', linewidth=2, label='Steam T')
        self.l5, = self.ax2.plot(self.hist_t, self.hist['tstack'], 'm-', linewidth=2, label='Stack T')
        self.ax2.legend(loc='upper right', fontsize=8)

        self.ax3.set_title('Steam flow, FW flow, spray x3, mode x30', pad=10)
        self.ax3.grid(True)
        self.ax3.set_xlim(self.hist_t[0], self.hist_t[-1])
        self.ax3.set_xlabel('Time before present (simulated s)')
        self.ax3.set_ylim(0, 140)
        self.l6, = self.ax3.plot(self.hist_t, self.hist['steam'], 'c--', linewidth=1.8, label='Steam')
        self.l7, = self.ax3.plot(self.hist_t, self.hist['fw'], 'g--', linewidth=1.8, label='FW')
        self.l8, = self.ax3.plot(self.hist_t, self.hist['spray'], 'k:', linewidth=1.8, label='Spray x3')
        self.l9, = self.ax3.plot(self.hist_t, self.hist['mode'], 'y:', linewidth=1.8, label='Mode x30')
        self.ax3.legend(loc='upper right', fontsize=8)

        for ax in (self.ax1, self.ax2, self.ax3):
            ax.tick_params(axis='x', pad=2)
            ax.tick_params(axis='y', pad=2)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumHeight(980)   # taller than the viewport: scroll to lower plots
        lay.addWidget(self.canvas, 1)

        outer.setWidget(w)
        return outer

    def build_diag_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        items = [('User fuel flow','usr'),('Fuel unit','unit'),('Fuel molar flow (mol/s)','nmol'),('Fuel mass flow (kg/s)','mkg'),('Stoich air (mol/s)','stoair'),('Actual air (mol/s)','actair'),('Dry O2 (%)','o2dry'),('Dry CO2 (%)','co2dry'),('Dry CO (%)','codry'),('Lambda','lambda'),('Phi','phi'),('Completeness','ce'),('Flue total (mol/s)','flue'),('Combustion mode','mode')]
        for i, (lab, key) in enumerate(items):
            grid.addWidget(QLabel(lab), i, 0)
            v = self.make_value_label()
            grid.addWidget(v, i, 1)
            if i < 9:
                self.conv[key] = v
            else:
                self.diag[key] = v
        return w

    def build_flue_tab(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        g = QGroupBox('Virtual flue gas analyzer readings')
        grid = QGridLayout(g)
        items = [
            ('Analyzer dry O2 (%)', 'o2'),
            ('Analyzer dry CO2 (%)', 'co2'),
            ('Analyzer dry CO (ppm)', 'co'),
            ('Analyzer NOx (ppm, dry)', 'nox'),
            ('NOx corrected to 3% O2 (ppm)', 'nox3'),
            ('Analyzer UHC (ppmC, dry)', 'uhc'),
            ('Flame-temperature proxy (C)', 'flamet'),
            ('Thermal / fuel / prompt NOx (ppm)', 'noxparts'),
            ('Analyzer stack T (C)', 'stack'),
            ('Water dew point (C)', 'dewpoint'),
            ('Stack-to-dew-point margin (C)', 'dewmargin'),
            ('True lambda', 'lambda'),
            ('True phi', 'phi'),
            ('Carbon to CO (%)', 'cofrac'),
            ('Effective heat capture', 'capture'),
            ('Diagnosis', 'diagnosis'),
            ('Operator action', 'action'),
            ('Efficiency note', 'effnote'),
        ]
        self.fg = {}
        for i, (lab, key) in enumerate(items):
            grid.addWidget(QLabel(lab), i, 0)
            v = self.make_value_label()
            v.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) if key in ('diagnosis', 'action', 'effnote') else None
            v.setWordWrap(True)
            grid.addWidget(v, i, 1)
            self.fg[key] = v
        lay.addWidget(g)

        self.fg_msg = QLabel('Flue gas interpretation will appear here while the simulator is running.')
        self.fg_msg.setStyleSheet('background:#e5f0fa; padding:10px;')
        self.fg_msg.setWordWrap(True)
        lay.addWidget(self.fg_msg)

        self.fg_fig = Figure(figsize=(7.6, 11.0), dpi=100, constrained_layout=True)
        self.fg_ax = self.fg_fig.add_subplot(311)
        self.fg_ax.set_title('Combustion map: dry O2 vs CO')
        self.fg_ax.set_xlabel('Dry O2 analyzer reading (%)')
        self.fg_ax.set_ylabel('Dry CO analyzer reading (ppm)')
        self.fg_ax.set_xlim(0, 12)
        self.fg_ax.set_ylim(0, 5000)
        self.fg_ax.grid(True)
        self.fg_ax.axhline(500, linestyle='--', linewidth=1, label='CO caution')
        self.fg_ax.axhline(2000, linestyle=':', linewidth=1, label='CO high')
        self.fg_ax.axvspan(0, 2, alpha=0.08, label='Low O2')
        self.fg_ax.axvspan(7, 12, alpha=0.06, label='High excess air')
        self.fg_trace, = self.fg_ax.plot([], [], 'k-', linewidth=1.4, label='Recent path')
        self.fg_point, = self.fg_ax.plot([], [], 'ro', markersize=6, label='Current')
        self.fg_ax.legend(loc='upper right', fontsize=8)
        self.nox_ax = self.fg_fig.add_subplot(312)
        self.nox_ax.set_title('Estimated NOx trend (teaching model)')
        self.nox_ax.set_xlabel('Time before present (simulated s)')
        self.nox_ax.set_ylabel('Dry NOx (ppm)')
        self.nox_ax.set_xlim(self.hist_t[0], self.hist_t[-1])
        self.nox_ax.set_ylim(0, 500)
        self.nox_ax.grid(True)
        self.nox_line, = self.nox_ax.plot(
            self.hist_t, self.hist['fg_nox_ppm'], color='#7d1238',
            linewidth=1.8, label='Analyzer NOx',
        )
        self.nox_alarm_line = self.nox_ax.axhline(
            self.getval('nox_alarm'), color='red', linestyle='--',
            linewidth=1, label='High alarm',
        )
        self.nox_ax.legend(loc='upper right', fontsize=8)
        self.uhc_ax = self.fg_fig.add_subplot(313)
        self.uhc_ax.set_title('Estimated unburned hydrocarbons (teaching model)')
        self.uhc_ax.set_xlabel('Time before present (simulated s)')
        self.uhc_ax.set_ylabel('Dry UHC (ppmC)')
        self.uhc_ax.set_xlim(self.hist_t[0], self.hist_t[-1])
        self.uhc_ax.set_ylim(0, 750)
        self.uhc_ax.grid(True)
        self.uhc_line, = self.uhc_ax.plot(
            self.hist_t, self.hist['fg_uhc_ppmc'], color='#8b5a2b',
            linewidth=1.8, label='Analyzer UHC',
        )
        self.uhc_alarm_line = self.uhc_ax.axhline(
            self.getval('uhc_alarm'), color='red', linestyle='--',
            linewidth=1, label='High alarm',
        )
        self.uhc_ax.legend(loc='upper right', fontsize=8)
        self.fg_canvas = FigureCanvas(self.fg_fig)
        self.fg_canvas.setMinimumHeight(1040)
        self.fg_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.fg_canvas, 1)

        help_text = QLabel(
            'Use “Control, compensation, alarms” for burner mixing, air leakage, fouling, analyzer dynamics, and the NOx alarm. '
            'Fuel nitrogen is set in “Combustion inputs”. NOx and UHC values are simplified teaching estimates, not regulatory or design predictions. '
            'Use the dedicated Fault injection box for individual exercises or Start Demo for the guided tour.'
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet('background:#f6f6f6; padding:8px;')
        lay.addWidget(help_text)
        outer.setWidget(w)
        return outer

    def build_alarm_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        self.tile_mode = QLabel('MODE\n--')
        self.tile_alarm = QLabel('ALARM\nNORMAL')
        self.tile_trip = QLabel('TRIP\nNO TRIP')
        self.tile_o2 = QLabel('DRY O2\n-- %')
        self.tile_dew = QLabel('DEW-POINT MARGIN\n-- C')
        self.tile_nox = QLabel('NOx\n-- ppm')
        self.tile_uhc = QLabel('UNBURNED HYDROCARBONS\n-- ppmC')
        self.tile_fuel_balance = QLabel('FUEL / FEEDWATER BALANCE\nNORMAL')
        for lab, color in [(self.tile_mode, '#dbeaf7'), (self.tile_alarm, '#d7edd7'), (self.tile_trip, '#dbeaf7'), (self.tile_o2, '#f5f5d9'), (self.tile_dew, '#d7edd7'), (self.tile_nox, '#d7edd7'), (self.tile_uhc, '#d7edd7'), (self.tile_fuel_balance, '#d7edd7')]:
            lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet(f'background:{color}; padding:20px; font-weight:bold; font-size:16px;')
        grid.addWidget(self.tile_mode, 0, 0)
        grid.addWidget(self.tile_alarm, 0, 1)
        grid.addWidget(self.tile_trip, 1, 0)
        grid.addWidget(self.tile_o2, 1, 1)
        grid.addWidget(self.tile_dew, 2, 0)
        grid.addWidget(self.tile_nox, 2, 1)
        grid.addWidget(self.tile_uhc, 3, 0, 1, 2)
        grid.addWidget(self.tile_fuel_balance, 4, 0, 1, 2)
        self.alarm_msg = QLabel('Alarm interpretation panel')
        self.alarm_msg.setStyleSheet('background:#e5f0fa; padding:10px;')
        self.alarm_msg.setWordWrap(True)
        grid.addWidget(self.alarm_msg, 5, 0, 1, 2)
        return w

    def get_fuel(self):
        fuel = dict(self.fuel_db[self.fuel_popup.currentIndex()])
        if fuel['phase'] == 'mixgas':
            fuel = mixture_to_fuel(self.mix)
        elif fuel['phase'] == 'mixliquid':
            fuel = liquid_blend_to_fuel(self.mixl)
        return fuel

    def fuel_cb(self):
        fuel = self.get_fuel()
        if self.lock_comp.isChecked() or fuel['phase'] in ('custom', 'mixgas', 'mixliquid'):
            for k, src in [('C', 'C'), ('H', 'H'), ('O', 'O'), ('S', 'S'), ('lhv', 'LHV'), ('mwfuel', 'MW')]:
                self.setpair(k, fuel[src])
        self.fuel_info.setText(f"Fuel info: {fuel['note']} | Unit: {fuel['flow_unit']}")

    def mixture_cb(self):
        keys = ['CH4', 'C2H6', 'C3H8', 'H2', 'CO', 'CO2', 'N2', 'H2S']
        vals = []
        for k in keys:
            v, ok = QInputDialog.getDouble(self, 'Edit gas mixture', f'{k} %', self.mix[k], 0, 1000, 3)
            if not ok:
                return
            vals.append(v)
        s = sum(vals)
        if s <= 0:
            return
        vals = [100 * v / s for v in vals]
        for k, v in zip(keys, vals):
            self.mix[k] = v
        self.fuel_popup.setCurrentIndex(self.fuels.index('User-defined gas mixture'))
        self.fuel_cb()

    def liquid_blend_cb(self):
        keys = ['FuelOil', 'Diesel', 'Gasoline', 'Kerosene']
        vals = []
        for k in keys:
            v, ok = QInputDialog.getDouble(self, 'Edit liquid blend', f'{k} %', self.mixl[k], 0, 1000, 3)
            if not ok:
                return
            vals.append(v)
        s = sum(vals)
        if s <= 0:
            return
        vals = [100 * v / s for v in vals]
        for k, v in zip(keys, vals):
            self.mixl[k] = v
        self.fuel_popup.setCurrentIndex(self.fuels.index('User-defined liquid blend'))
        self.fuel_cb()

    def setpair(self, key, val):
        self.rows[key].set_value(val)

    def getval(self, key):
        return self.rows[key].value()

    def init_log_file(self, fname):
        with open(fname, 'w', newline='') as f:
            csv.writer(f).writerow(['time_s', 'mode', 'fuel_flow_mol_s', 'actual_fuel_user_flow', 'firing_factor', 'coordinated_firing', 'excess_air_pct', 'drum_level_pct', 'o2_pct', 'co_ppm', 'nox_ppm_dry', 'nox_ppm_at_3pct_o2', 'uhc_ppmC_dry', 'flame_temp_proxy_C', 'efficiency_pct', 'boiler_heat_kw', 'steam_need_kw', 'adequacy_pct', 'fuel_supported_steam_capacity_kg_s', 'fuel_feedwater_adequacy_pct', 'fuel_feedwater_warning', 'steam_temp_C', 'stack_temp_C', 'water_dew_point_C', 'dew_point_margin_C', 'steam_flow_kg_s', 'fw_flow_kg_s', 'fw_sp', 'spray_pct', 'alarm', 'trip'])

    def append_log_row(self, fname, tsim, mode_name, p, s, fw_sp, alarm_txt, trip_txt):
        with open(fname, 'a', newline='') as f:
            csv.writer(f).writerow([f'{tsim:.4f}', clean_csv(mode_name), f"{p['nf']:.6f}", f"{s['actual_fuel_user_flow']:.6f}", f"{s['firing_factor']:.6f}", int(bool(p.get('coordinated_firing', False))), f"{p['ea']:.6f}", f"{s['drum']:.6f}", f"{s['o2']:.6f}", f"{s['fg_co_ppm']:.6f}", f"{s['fg_nox_ppm']:.6f}", f"{s['nox_corrected_3pct']:.6f}", f"{s['fg_uhc_ppmc']:.6f}", f"{s['flame_temp']:.6f}", f"{s['eta']:.6f}", f"{s['qboiler']:.6f}", f"{s['qsteam']:.6f}", f"{s['adequacy']:.6f}", f"{s['steam_capacity']:.6f}", f"{s['fuel_balance_pct']:.6f}", int(bool(s['fuel_warning'])), f"{s['tsteam']:.6f}", f"{s['tstack']:.6f}", f"{s['dew_point']:.6f}", f"{s['dew_margin']:.6f}", f"{s['steamflow']:.6f}", f"{s['fwflow']:.6f}", f'{fw_sp:.6f}', f"{s['spray']:.6f}", clean_csv(alarm_txt), clean_csv(trip_txt)])

    def toggle_log_cb(self):
        self.log_enabled = self.log_check.isChecked()
        self.log_file = self.log_name.text().strip() or 'boiler_transient_log.csv'
        self.log_name.setText(self.log_file)
        if self.log_enabled:
            self.init_log_file(self.log_file)

    def rd(self):
        names = ['fuel_flow_user', 'ea', 'tair', 'tfuel', 'eta_comb', 'loss', 'capture', 'lhv', 'C', 'H', 'O', 'S', 'mwfuel', 'fuelmoist', 'fuel_nitrogen', 'fuelash', 'pbar', 'tfw', 'fwcmd', 'tsteam_sp', 'demand', 'tspray', 'spray_manual', 'lvl_sp', 'lvl_init', 'steam_ft_bias', 'fw_ft_bias', 'steam_ft_noise', 'fw_ft_noise', 'steam_dp', 'fw_dp', 'o2_sp', 'air_kp', 'air_ki', 'out_kp', 'out_ki', 'in_kp', 'in_ki', 'lvl_kp', 'lvl_ki', 'fw_kp', 'fw_ki', 'mid_bias', 'lvl_ll', 'lvl_hh', 'ttrip', 'stack_hh', 'dew_margin_alarm', 'nox_alarm', 'uhc_alarm', 'fuel_warn_margin', 'fuel_warn_delay', 'burner_mixing', 'flue_air_leak', 'tube_fouling', 'analyzer_lag', 'analyzer_noise']
        p = {n: self.getval(n) for n in names}
        fuel = self.get_fuel()
        p['coordinated_firing'] = (
            self.coordinated_firing.isChecked()
            if hasattr(self, 'coordinated_firing') else False
        )
        p['fuel_unit'] = fuel['flow_unit']
        p['fuel_phase'] = fuel['phase']
        if fuel['flow_unit'] == 'Nm3/hr':
            p['nf'] = p['fuel_flow_user'] * fuel['Nm3_to_kmol'] * 1000 / 3600
            p['fuel_mass_kgps'] = p['nf'] * p['mwfuel'] / 1000
        else:
            p['fuel_mass_kgps'] = p['fuel_flow_user'] / 3600
            p['nf'] = p['fuel_mass_kgps'] / (p['mwfuel'] / 1000)
        return p

    def mode_sel_value(self):
        return self.mode_popup.currentIndex() + 1

    def speed_scale(self):
        return [2.0, 1.0, 0.5, 0.2][self.speed_popup.currentIndex()]

    def start_cb(self):
        self.running = True
        if self.log_enabled:
            self.init_log_file(self.log_file)
        self.timer.start(int(self.dt * self.speed_scale() * 1000))

    def pause_cb(self):
        self.running = False
        self.timer.stop()
        self.update_time_box('Paused')

    def resume_cb(self):
        self.running = True
        self.timer.start(int(self.dt * self.speed_scale() * 1000))

    def step_cb(self):
        self.running = False
        self.timer.stop()
        self.simulate_one_step()

    def reset_cb(self):
        self.demo_active = False
        self.demo_stage = None
        self.demo_message = 'Demo mode off.'
        self.fault_baseline = None
        self.active_fault_name = None
        if hasattr(self, 'fault_info'):
            self.update_fault_description()
        if hasattr(self, 'demo_box'):
            self.demo_box.setStyleSheet('background:#f0f7ff; padding:8px; border:1px solid #bdd7ee;')
            self.demo_box.setText('Demo mode: off. Click Start Demo for a guided tour of boiler response, flue-gas diagnosis, and fault interpretation.')
        self.pause_cb()
        self.fuel_popup.setCurrentIndex(0)
        self.lock_comp.setChecked(True)
        self.fuel_cb()
        d = fuel_defaults(1)
        for k, v in [('C', d['C']), ('H', d['H']), ('O', d['O']), ('S', d['S']), ('lhv', d['LHV']), ('mwfuel', d['MW']), ('fuelmoist', d['moist']), ('fuel_nitrogen', 0.05), ('fuelash', d['ash'])]:
            self.setpair(k, v)
        vals = {'fuel_flow_user':100, 'ea':15, 'tair':25, 'tfuel':25, 'eta_comb':0.99, 'loss':3, 'capture':0.82, 'pbar':45, 'tfw':105, 'fwcmd':0.30, 'tsteam_sp':440, 'demand':1.0, 'tspray':105, 'spray_manual':0, 'lvl_sp':50, 'lvl_init':50, 'steam_ft_bias':0, 'fw_ft_bias':0, 'steam_ft_noise':0.5, 'fw_ft_noise':0.5, 'steam_dp':1.0, 'fw_dp':1.0, 'o2_sp':3, 'air_kp':1.6, 'air_ki':0.12, 'out_kp':1.0, 'out_ki':0.06, 'in_kp':1.5, 'in_ki':0.12, 'lvl_kp':0.8, 'lvl_ki':0.05, 'fw_kp':0.35, 'fw_ki':0.08, 'mid_bias':30, 'lvl_ll':25, 'lvl_hh':75, 'ttrip':540, 'stack_hh':280, 'dew_margin_alarm':15, 'nox_alarm':300, 'uhc_alarm':500, 'fuel_warn_margin':10, 'fuel_warn_delay':10, 'burner_mixing':95, 'flue_air_leak':0, 'tube_fouling':0, 'analyzer_lag':8, 'analyzer_noise':0.5}
        for k, v in vals.items():
            self.setpair(k, v)
        self.mode_popup.setCurrentIndex(3)
        self.auto_air.setChecked(True)
        self.auto_steam.setChecked(True)
        self.dens_comp.setChecked(True)
        self.bumpless.setChecked(True)
        self.coordinated_firing.setChecked(True)
        self.speed_popup.setCurrentIndex(1)
        for k in self.hist:
            self.hist[k] = [math.nan] * self.hist_n
        self.tick = 0
        initial_level = self.getval('lvl_init')
        self.state = dict(o2=3, eta=80, qboiler=0, qsteam=0, adequacy=100, tstack=180, dew_point=55, dew_margin=125, flame_temp=1900, nox_corrected_3pct=120, steam_capacity=0.30, fuel_balance_pct=100, fuel_warning=False, fuel_warn_time=0, firing_factor=1.0, actual_fuel_user_flow=100, tmid=450, tsteam=440, instab=0, drum=initial_level, drum_inventory=initial_level, swell=0, previous_steamflow=0.30, steamflow=0.30, fwflow=0.30, spray=0, trip=0, alarm=0, fwvalve=0.30, sim_time=0, realtime=0, fuel_user_flow=100, fuel_nmolps=1, fuel_unit='Nm3/hr', fg_o2=3, fg_co2=9, fg_co_ppm=300, fg_nox_ppm=120, fg_uhc_ppmc=30, fg_stack=180)
        self.mem = dict(
            int_o2=0, int_ot=0, int_it=0, int_lvl=0, int_fic=0,
            lvltrim=0, mid_sp=self.getval('tsteam_sp'), phase=0,
        )
        initial_model = plant_calc_if97(
            self.rd(), self.state, self.mem['phase'],
            1 if self.dens_comp.isChecked() else 0,
        )
        balanced_flow = initial_model['msteam_actual']
        self.setpair('fwcmd', balanced_flow)
        self.state.update(
            steam_capacity=initial_model['steam_capacity'],
            steamflow=balanced_flow,
            previous_steamflow=balanced_flow,
            fwflow=balanced_flow,
            fwvalve=balanced_flow,
        )
        self.simulate_one_step()

    def start_demo_cb(self):
        """Run an automatic guided tour for demonstration and outreach."""
        # Reset first so the demo always starts from a clean, predictable point.
        self.reset_cb()
        self.demo_active = True
        self.demo_stage = None
        self.demo_start_sim_time = self.state['sim_time']
        self.demo_message = 'Starting guided demo tour.'
        self.mode_popup.setCurrentIndex(3)
        self.auto_air.setChecked(True)
        self.auto_steam.setChecked(True)
        self.dens_comp.setChecked(True)
        self.bumpless.setChecked(True)
        self.speed_popup.setCurrentIndex(3)  # 5x for a lively exhibition demo
        self.tabs.setCurrentIndex(2)        # Show the Flue Gas tab first
        for k in self.hist:
            self.hist[k] = [math.nan] * self.hist_n
        self.running = True
        self.timer.start(int(self.dt * self.speed_scale() * 1000))
        if hasattr(self, 'demo_box'):
            self.demo_box.setStyleSheet('background:#e5f7ff; padding:8px; border:1px solid #69a9d6; font-weight:bold;')
            self.demo_box.setText('Demo mode running: guided tour begins with a stable boiler, then introduces demand and flue-gas fault scenarios.')
        self.status.setText('Demo mode started. The simulator will automatically step through attention-grabbing training scenarios.')

    def stop_demo_cb(self):
        self.demo_active = False
        self.demo_stage = None
        self.demo_message = 'Demo mode stopped.'
        if hasattr(self, 'demo_box'):
            self.demo_box.setStyleSheet('background:#f0f7ff; padding:8px; border:1px solid #bdd7ee;')
            self.demo_box.setText('Demo mode: stopped. Controls are now manual/normal again; click Start Demo to replay the guided tour.')
        self.status.setText('Demo mode stopped. Current plant state is left as-is for discussion or manual operation.')

    def apply_demo_stage(self, stage):
        """Apply one-time control changes for each demo scene."""
        self.demo_stage = stage
        # Default: make sure trips do not mask the outreach demo.
        self.state['trip'] = 0
        if stage == 0:
            self.setpair('demand', 1.0)
            self.setpair('ea', 15)
            self.setpair('o2_sp', 3.0)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.setpair('analyzer_lag', 6)
            self.setpair('analyzer_noise', 0.4)
            self.auto_air.setChecked(True)
            self.auto_steam.setChecked(True)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '1/8 Stable automatic operation: O2 trim and steam-temperature cascade hold the boiler near a clean, efficient point.'
        elif stage == 1:
            self.setpair('demand', 1.22)
            self.auto_air.setChecked(True)
            self.auto_steam.setChecked(True)
            self.tabs.setCurrentIndex(0)
            self.demo_message = '2/8 Demand step: steam demand is increased so visitors can see the transient response in boiler heat, drum level, and steam temperature.'
        elif stage == 2:
            self.auto_air.setChecked(False)
            self.setpair('ea', 45)
            self.setpair('burner_mixing', 96)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '3/8 Excess-air case: O2 rises, CO stays low, CO2 is diluted, and efficiency is penalized by stack loss.'
        elif stage == 3:
            self.auto_air.setChecked(True)
            self.setpair('o2_sp', 3.0)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '4/8 Automatic recovery: O2 trim brings excess air back toward the target while the flue-gas map traces the operating path.'
        elif stage == 4:
            self.auto_air.setChecked(False)
            self.setpair('ea', 0)
            self.setpair('burner_mixing', 82)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '5/8 Air-starved firing: O2 collapses and CO breaks through sharply, showing why O2 margin and CO monitoring matter.'
        elif stage == 5:
            self.auto_air.setChecked(False)
            self.setpair('ea', 16)
            self.setpair('burner_mixing', 55)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '6/8 Poor burner mixing: CO remains high even though O2 is not extremely low, illustrating why O2 alone is not enough.'
        elif stage == 6:
            self.auto_air.setChecked(False)
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 35)
            self.setpair('tube_fouling', 0)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '7/8 Post-furnace air leakage: measured O2 rises and CO2 is diluted, but the extra air did not help the flame.'
        elif stage == 7:
            self.auto_air.setChecked(False)
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 60)
            self.tabs.setCurrentIndex(2)
            self.demo_message = '8/8 Fouling/soot case: stack temperature rises and effective heat capture falls, highlighting heat-transfer maintenance.'
        elif stage == 8:
            self.auto_air.setChecked(True)
            self.auto_steam.setChecked(True)
            self.setpair('demand', 1.0)
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.tabs.setCurrentIndex(2)
            self.demo_message = 'Final recovery: all demo faults are cleared and automatic operation resumes. Click Start Demo again to replay.'

    def update_demo_mode(self):
        if not self.demo_active:
            return
        t = max(0.0, self.state['sim_time'] - self.demo_start_sim_time)
        # Stage timeline in simulated seconds. At 5x speed this is a short, punchy demo.
        if t < 12:
            stage = 0
        elif t < 30:
            stage = 1
        elif t < 50:
            stage = 2
        elif t < 70:
            stage = 3
        elif t < 90:
            stage = 4
        elif t < 112:
            stage = 5
        elif t < 134:
            stage = 6
        elif t < 156:
            stage = 7
        elif t < 176:
            stage = 8
        else:
            self.apply_demo_stage(8)
            self.demo_active = False
            self.demo_stage = None
            self.demo_message = 'Demo complete. The plant has returned to normal automatic operation.'
            if hasattr(self, 'demo_box'):
                self.demo_box.setStyleSheet('background:#e8f6e8; padding:8px; border:1px solid #9ac79a; font-weight:bold;')
                self.demo_box.setText('Demo complete: normal automatic operation restored. Click Start Demo to replay the guided tour.')
            return
        if stage != self.demo_stage:
            self.apply_demo_stage(stage)
        if hasattr(self, 'demo_box'):
            self.demo_box.setStyleSheet('background:#e5f7ff; padding:8px; border:1px solid #69a9d6; font-weight:bold;')
            self.demo_box.setText(f'Demo mode running | t = {t:.1f} s / 176 s | {self.demo_message}')

    def case_cb(self):
        sel, ok = QInputDialog.getInt(self, 'Load case', '1 Stable 3-element auto\n2 Startup low-load single-element\n3 Medium-load two-element\n4 High-demand shrink/swell\n5 Faulty steam FT -> fallback', 1, 1, 5, 1)
        if not ok:
            return
        self.reset_cb()
        if sel == 1:
            self.mode_popup.setCurrentIndex(2)
        elif sel == 2:
            self.setpair('demand', 0.45)
            self.setpair('fwcmd', 10)
            self.mode_popup.setCurrentIndex(0)
        elif sel == 3:
            self.setpair('demand', 0.75)
            self.mode_popup.setCurrentIndex(1)
        elif sel == 4:
            self.setpair('demand', 1.22)
            self.setpair('tsteam_sp', 500)
            self.mode_popup.setCurrentIndex(3)
        elif sel == 5:
            self.setpair('steam_ft_bias', -8)
            self.setpair('steam_ft_noise', 5)
            self.mode_popup.setCurrentIndex(3)
        self.simulate_one_step()

    def capture_fault_baseline(self):
        keys = [
            'ea', 'eta_comb', 'demand', 'burner_mixing', 'flue_air_leak', 'tube_fouling',
            'analyzer_lag', 'analyzer_noise', 'steam_ft_bias',
            'steam_ft_noise', 'fw_ft_bias', 'fw_ft_noise', 'lhv',
            'fuelmoist', 'fuel_nitrogen',
        ]
        return {
            'values': {key: self.getval(key) for key in keys},
            'auto_air': self.auto_air.isChecked(),
            'auto_steam': self.auto_steam.isChecked(),
            'coordinated_firing': self.coordinated_firing.isChecked(),
            'mode_index': self.mode_popup.currentIndex(),
        }

    def restore_fault_baseline(self):
        if self.fault_baseline is None:
            return
        for key, value in self.fault_baseline['values'].items():
            self.setpair(key, value)
        self.auto_air.setChecked(self.fault_baseline['auto_air'])
        self.auto_steam.setChecked(self.fault_baseline['auto_steam'])
        self.coordinated_firing.setChecked(
            self.fault_baseline['coordinated_firing']
        )
        self.mode_popup.setCurrentIndex(self.fault_baseline['mode_index'])

    def inject_fault_cb(self):
        if self.fault_baseline is None:
            self.fault_baseline = self.capture_fault_baseline()
        else:
            # Make cases mutually exclusive and repeatable.
            self.restore_fault_baseline()

        case = self.fault_cases[self.fault_popup.currentIndex()]
        for key, value in case.get('values', {}).items():
            self.setpair(key, value)
        if 'lhv_scale' in case:
            baseline_lhv = self.fault_baseline['values']['lhv']
            self.setpair('lhv', baseline_lhv * case['lhv_scale'])
        if 'auto_air' in case:
            self.auto_air.setChecked(case['auto_air'])
        if 'auto_steam' in case:
            self.auto_steam.setChecked(case['auto_steam'])
        if 'coordinated_firing' in case:
            self.coordinated_firing.setChecked(case['coordinated_firing'])
        if 'mode_index' in case:
            self.mode_popup.setCurrentIndex(case['mode_index'])

        self.demo_active = False
        self.active_fault_name = case['name']
        self.update_fault_description()
        self.fault_info.setStyleSheet(
            'background:#ffe0cc; padding:8px; border:2px solid #cc6f35;'
        )
        self.simulate_one_step()

    def clear_fault_cb(self):
        if self.fault_baseline is None:
            self.active_fault_name = None
            self.update_fault_description()
            return
        self.restore_fault_baseline()
        self.fault_baseline = None
        self.active_fault_name = None
        self.fault_info.setStyleSheet(
            'background:#e8f6e8; padding:8px; border:1px solid #9ac79a;'
        )
        self.update_fault_description()
        self.status.setText(
            'Injected fault cleared. Pre-fault inputs and controller selections restored.'
        )

    def flue_case_cb(self):
        cases = [
            'Reset flue faults',
            'Excess air / damper too open',
            'Air-starved firing / damper too closed',
            'Poor burner mixing',
            'Post-furnace air leakage',
            'Tube fouling / soot on heat-transfer surfaces',
        ]
        sel, ok = QInputDialog.getItem(self, 'Flue gas fault case', 'Select flue-gas exercise:', cases, 0, False)
        if not ok:
            return
        # Start from a clean flue-side condition but keep the rest of the boiler state.
        for k, v in [('burner_mixing', 95), ('flue_air_leak', 0), ('tube_fouling', 0), ('analyzer_lag', 8), ('analyzer_noise', 0.5)]:
            self.setpair(k, v)
        if sel == 'Reset flue faults':
            self.setpair('ea', 15)
            self.status.setText('Flue gas faults reset. Normal burner mixing, no post-furnace leakage, no fouling.')
        elif sel == 'Excess air / damper too open':
            self.setpair('ea', 42)
            self.setpair('burner_mixing', 96)
            self.status.setText('Flue case loaded: excess air. Expect high O2, lower CO2, higher stack loss, and usually low CO.')
        elif sel == 'Air-starved firing / damper too closed':
            self.setpair('ea', 0)
            self.setpair('burner_mixing', 84)
            self.status.setText('Flue case loaded: air-starved firing. Expect low O2 and rapid CO breakthrough.')
        elif sel == 'Poor burner mixing':
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 55)
            self.status.setText('Flue case loaded: poor burner mixing. Expect high CO even though O2 may look acceptable.')
        elif sel == 'Post-furnace air leakage':
            self.setpair('ea', 15)
            self.setpair('flue_air_leak', 35)
            self.status.setText('Flue case loaded: post-furnace leakage. Expect O2 reading to rise and CO2/CO to be diluted.')
        elif sel == 'Tube fouling / soot on heat-transfer surfaces':
            self.setpair('ea', 15)
            self.setpair('tube_fouling', 55)
            self.status.setText('Flue case loaded: fouling/soot. Expect higher stack temperature and lower effective heat capture.')
        self.simulate_one_step()

    def update_flue_analyzer(self, p, model):
        lag_s = max(p.get('analyzer_lag', 8.0), self.dt)
        noise = max(p.get('analyzer_noise', 0.0), 0.0)
        phase = self.mem.get('phase', 0.0)

        true_o2 = model['dry_O2']
        true_co2 = model['dry_CO2']
        true_co_ppm = model['co_ppm']
        true_nox_ppm = model['nox_ppm']
        true_uhc_ppmc = model['uhc_ppmc']
        true_stack = model['tstack']

        target_o2 = clamp(true_o2 + 0.035 * noise * math.sin(2.1 * phase), 0, 25)
        target_co2 = clamp(true_co2 + 0.030 * noise * math.cos(1.7 * phase), 0, 25)
        target_co = max(0, true_co_ppm + 30 * noise * math.sin(2.7 * phase))
        target_nox = max(0, true_nox_ppm + 8 * noise * math.cos(2.3 * phase))
        target_uhc = max(0, true_uhc_ppmc + 12 * noise * math.sin(1.9 * phase))
        target_stack = max(0, true_stack + 0.8 * noise * math.cos(1.3 * phase))

        self.state['fg_o2'] = lag(self.state.get('fg_o2', target_o2), target_o2, lag_s / self.dt)
        self.state['fg_co2'] = lag(self.state.get('fg_co2', target_co2), target_co2, lag_s / self.dt)
        self.state['fg_co_ppm'] = lag(self.state.get('fg_co_ppm', target_co), target_co, lag_s / self.dt)
        self.state['fg_nox_ppm'] = lag(self.state.get('fg_nox_ppm', target_nox), target_nox, lag_s / self.dt)
        self.state['fg_uhc_ppmc'] = lag(self.state.get('fg_uhc_ppmc', target_uhc), target_uhc, lag_s / self.dt)
        self.state['fg_stack'] = lag(self.state.get('fg_stack', target_stack), target_stack, lag_s / self.dt)

    def flue_diagnosis(self, p, model):
        o2 = self.state.get('fg_o2', model['dry_O2'])
        co2 = self.state.get('fg_co2', model['dry_CO2'])
        co = self.state.get('fg_co_ppm', model['co_ppm'])
        nox = self.state.get('fg_nox_ppm', model['nox_ppm'])
        uhc = self.state.get('fg_uhc_ppmc', model['uhc_ppmc'])
        stack = self.state.get('fg_stack', model['tstack'])
        leak = p.get('flue_air_leak', 0.0)
        mixing = p.get('burner_mixing', 95.0)
        fouling = p.get('tube_fouling', 0.0)

        condition = 'Good combustion / acceptable trim'
        reason = 'O2, CO, and CO2 are in a reasonable relationship for this simplified burner model.'
        action = 'Continue trending. Fine-tune excess air slowly while watching CO.'
        effnote = 'Efficiency is near the current operating optimum for this fuel and load.'
        color = '#d7edd7'

        if co > 3000 and o2 < 2.0:
            condition = 'Air-starved combustion / CO breakthrough'
            reason = 'Analyzer O2 is low while CO is very high. The burner is operating too close to rich conditions.'
            action = 'Increase combustion air and verify damper/fan response. Do not reduce air further.'
            effnote = 'Incomplete combustion wastes fuel and can quickly become unsafe.'
            color = '#facccc'
        elif co > 1200 and o2 >= 2.0:
            condition = 'Poor mixing or unstable burner'
            reason = 'CO is high even though measured O2 is not especially low. This suggests maldistribution, dirty burner tips, poor atomization, or flame instability.'
            action = 'Check burner register, fuel/air distribution, atomization, and flame shape. Add air only as a temporary stabilizing action.'
            effnote = 'O2 trim alone cannot solve poor mixing; excess air may hide the problem while reducing efficiency.'
            color = '#fadbc2'
        elif o2 > 8.0 and co < 500:
            condition = 'Excess air too high'
            reason = 'High O2 and low CO indicate the furnace has more air than needed for clean combustion.'
            action = 'Reduce air gradually until O2 approaches setpoint, while ensuring CO remains low.'
            effnote = 'Too much air heats extra nitrogen and oxygen, increasing stack loss and lowering efficiency.'
            color = '#fff2c2'
        elif leak > 15 and o2 > 5.5 and co2 < 8.0:
            condition = 'Post-furnace air leakage / dilution'
            reason = 'O2 is elevated and CO2 is diluted. The extra oxygen may be entering after combustion, so it does not prove that the flame has enough air.'
            action = 'Inspect casing, access doors, ducting, economizer outlet, and sampling line for air ingress.'
            effnote = 'A leaking sample path can mislead O2 trim and cause the controller to remove too much combustion air.'
            color = '#fadbc2'
        elif nox >= p.get('nox_alarm', 300):
            condition = 'High estimated NOx emissions'
            reason = 'The simplified thermal, fuel, and prompt NOx contributions exceed the configured analyzer alarm.'
            action = 'Check excess air, air preheat, firing intensity, burner staging/mixing, and fuel-nitrogen input.'
            effnote = 'NOx reduction can trade against CO and efficiency; adjust combustion conditions while trending all three.'
            color = '#fadbc2'
        elif uhc >= p.get('uhc_alarm', 500):
            condition = 'High estimated unburned hydrocarbons'
            reason = 'The simplified UHC estimate indicates incomplete hydrocarbon burnout from richness, quenching, or poor mixing.'
            action = 'Check flame stability, fuel preparation/atomization, burner mixing, excess air, and furnace temperature.'
            effnote = 'Unburned fuel represents lost chemical energy and should be interpreted together with CO.'
            color = '#fadbc2'
        elif fouling > 25 or (stack > 0.9 * p.get('stack_hh', 280) and 2.0 <= o2 <= 7.0):
            condition = 'Heat-transfer fouling / soot suspected'
            reason = 'Stack temperature is high without a matching excess-air explanation.'
            action = 'Inspect heat-transfer surfaces and consider soot-blowing/cleaning in the exercise scenario.'
            effnote = 'Fouling sends more heat to the stack, lowering boiler efficiency.'
            color = '#fff2c2'
        elif o2 < 1.5 and co > 500:
            condition = 'Low-O2 operation approaching CO breakthrough'
            reason = 'O2 margin is very small and CO is starting to rise.'
            action = 'Increase O2 setpoint or air flow slightly and monitor the CO trend.'
            effnote = 'Operating too near stoichiometric air can give good efficiency briefly but has poor safety margin.'
            color = '#fadbc2'
        elif mixing < 75 and co > 500:
            condition = 'Developing burner mixing problem'
            reason = 'Burner mixing quality is reduced and CO is above the normal clean-combustion range.'
            action = 'Compare O2 and CO together; do not rely on O2 alone.'
            effnote = 'Better mechanical mixing often improves both CO and efficiency more than simply adding air.'
            color = '#fff2c2'

        return condition, reason, action, effnote, color

    def clear_cb(self):
        for k in self.hist:
            self.hist[k] = [math.nan] * self.hist_n
        self.updplots()

    def export_log_cb(self):
        self.status.setText(f'Log file path: {self.log_file}')

    def trip_reset_cb(self):
        self.state['trip'] = 0

    def disturb_demand_up_cb(self):
        self.setpair('demand', min(self.getval('demand') * 1.10, self.rows['demand'].vmax))

    def disturb_demand_dn_cb(self):
        self.setpair('demand', max(self.getval('demand') * 0.90, self.rows['demand'].vmin))

    def disturb_lhv_cb(self):
        self.setpair('lhv', max(self.getval('lhv') * 0.95, self.rows['lhv'].vmin))

    def run_loop(self):
        if not self.running:
            return
        self.simulate_one_step()
        self.timer.start(int(self.dt * self.speed_scale() * 1000))

    def simulate_one_step(self):
        if self.demo_active:
            self.update_demo_mode()
        p = self.rd()
        self.tick += 1
        self.state['fuel_user_flow'] = p['fuel_flow_user']
        self.state['fuel_nmolps'] = p['nf']
        self.state['fuel_unit'] = p['fuel_unit']
        self.state['sim_time'] += self.dt
        self.state['realtime'] = self.tick * self.dt
        if p.get('coordinated_firing', False) and self.state['trip'] == 0:
            self.state['firing_factor'] = lag(
                self.state.get('firing_factor', 1.0),
                p['demand'],
                8.0 / self.dt,
            )
        elif self.state['trip'] == 0:
            self.state['firing_factor'] = lag(
                self.state.get('firing_factor', 1.0),
                1.0,
                4.0 / self.dt,
            )
        self.state['actual_fuel_user_flow'] = (
            p['fuel_flow_user'] * self.state['firing_factor']
        )
        p['nf'] *= self.state['firing_factor']
        p['fuel_mass_kgps'] *= self.state['firing_factor']
        if self.state['trip'] == 1:
            p['nf'] = 0
            p['fuel_mass_kgps'] = 0
            self.state['actual_fuel_user_flow'] = 0
            p['fwcmd'] = 0
            p['spray_manual'] = 20
        if self.auto_air.isChecked() and self.state['trip'] == 0:
            ea_cmd, self.mem['int_o2'] = pi_ctrl(self.getval('ea'), self.state['o2'], p['o2_sp'], p['air_kp'], p['air_ki'], self.mem['int_o2'], self.dt, 0, 150)
            self.setpair('ea', ea_cmd)
            p['ea'] = ea_cmd
        mid_sp = p['tsteam_sp'] + p['mid_bias']
        if self.auto_steam.isChecked() and self.state['trip'] == 0:
            mid_sp, self.mem['int_ot'] = pi_ctrl(self.mem.get('mid_sp', mid_sp), self.state['tsteam'], p['tsteam_sp'], p['out_kp'], p['out_ki'], self.mem['int_ot'], self.dt, p['tsteam_sp'], p['tsteam_sp'] + p['mid_bias'])
            self.mem['mid_sp'] = mid_sp
            spray_cmd, self.mem['int_it'] = pi_ctrl(self.getval('spray_manual'), self.state['tmid'], mid_sp, p['in_kp'], p['in_ki'], self.mem['int_it'], self.dt, 0, 35)
            self.setpair('spray_manual', spray_cmd)
            p['spray_manual'] = spray_cmd
        self.mem['phase'] += 2 * math.pi * self.dt / 12
        model = plant_calc_if97(p, self.state, self.mem['phase'], 1 if self.dens_comp.isChecked() else 0)
        mode_id, mode_name = select_mode(self.mode_sel_value(), model, p)
        if self.state['trip'] == 0:
            if mode_id == 1:
                fwcmd, self.mem['int_lvl'] = pi_ctrl(self.getval('fwcmd'), self.state['drum'], p['lvl_sp'], p['lvl_kp'], p['lvl_ki'], self.mem['int_lvl'], self.dt, 0, 120)
                fw_sp = fwcmd
            else:
                lvltrim, self.mem['int_lvl'] = pi_ctrl(self.mem.get('lvltrim', 0), self.state['drum'], p['lvl_sp'], p['lvl_kp'], p['lvl_ki'], self.mem['int_lvl'], self.dt, -30, 30)
                self.mem['lvltrim'] = lvltrim
                fw_sp = max(0, model['msteam_comp'] + lvltrim)
                fwcmd, self.mem['int_fic'] = pi_ctrl(self.getval('fwcmd'), model['mfw_comp_meas'], fw_sp, p['fw_kp'], p['fw_ki'], self.mem['int_fic'], self.dt, 0, 120)
        else:
            fw_sp = 0
            fwcmd = 0
        if self.bumpless.isChecked():
            self.setpair('fwcmd', fwcmd)
        p['fwcmd'] = fwcmd
        model = plant_calc_if97(p, self.state, self.mem['phase'], 1 if self.dens_comp.isChecked() else 0)
        self.state['o2'] = lag(self.state['o2'], model['o2'], 4 / self.dt)
        self.state['eta'] = lag(self.state['eta'], model['eta'], 4 / self.dt)
        self.state['qboiler'] = lag(self.state['qboiler'], model['qboiler'], 8 / self.dt)
        self.state['qsteam'] = lag(self.state['qsteam'], model['qsteam'], 8 / self.dt)
        self.state['adequacy'] = lag(self.state['adequacy'], model['adequacy'], 8 / self.dt)
        self.state['tstack'] = lag(self.state['tstack'], model['tstack'], 8 / self.dt)
        self.state['dew_point'] = model['dew_point']
        self.state['dew_margin'] = self.state['tstack'] - self.state['dew_point']
        self.state['flame_temp'] = model['flame_temp']
        self.state['tmid'] = lag(self.state['tmid'], model['tmid'], 10 / self.dt)
        self.state['tsteam'] = lag(self.state['tsteam'], model['tsteam'], 12 / self.dt)
        self.state['spray'] = lag(self.state['spray'], p['spray_manual'], 2 / self.dt)
        self.state['steamflow'] = lag(self.state['steamflow'], model['msteam_actual'], 3 / self.dt)
        self.state['fwflow'] = lag(self.state['fwflow'], model['mfw_actual'], 3 / self.dt)
        self.state['fwvalve'] = lag(self.state['fwvalve'], p['fwcmd'], 2 / self.dt)
        self.state['steam_capacity'] = model['steam_capacity']
        self.state['fuel_balance_pct'] = (
            100 * self.state['steam_capacity'] / max(self.state['fwflow'], 0.05)
        )
        fuel_deficit = (
            self.state['fwflow'] > 0.1
            and self.state['fuel_balance_pct'] < 100 - p['fuel_warn_margin']
        )
        if fuel_deficit:
            self.state['fuel_warn_time'] = min(
                p['fuel_warn_delay'],
                self.state['fuel_warn_time'] + self.dt,
            )
        else:
            self.state['fuel_warn_time'] = max(
                0.0, self.state['fuel_warn_time'] - 2 * self.dt
            )
        self.state['fuel_warning'] = (
            self.state['fuel_warn_time'] >= p['fuel_warn_delay']
        )
        # True inventory changes only with the mass-flow imbalance.
        inventory_rate = 0.22 * (
            self.state['fwflow'] - self.state['steamflow']
        )
        self.state['drum_inventory'] = clamp(
            self.state['drum_inventory'] + self.dt * inventory_rate, 0, 100
        )

        # Shrink/swell is a temporary indicated-level effect driven by changes
        # in steam release, not a permanent addition to drum inventory.
        steam_rate = (
            self.state['steamflow'] - self.state['previous_steamflow']
        ) / max(self.dt, 1e-9)
        swell_target = clamp(2.0 * steam_rate, -8.0, 8.0)
        self.state['swell'] = lag(
            self.state['swell'], swell_target, 6.0 / self.dt
        )
        self.state['previous_steamflow'] = self.state['steamflow']
        self.state['drum'] = clamp(
            self.state['drum_inventory'] + self.state['swell'], 0, 100
        )
        self.update_flue_analyzer(p, model)
        self.state['nox_corrected_3pct'] = (
            self.state['fg_nox_ppm']
            * (20.9 - 3.0)
            / max(20.9 - self.state['fg_o2'], 1.0)
        )
        alarm_txt, trip_txt, alarm_code, trip_code = alarms_and_trip(self.state, p)
        self.state['alarm'] = alarm_code
        if trip_code == 1:
            self.state['trip'] = 1
        self.hist['eta'] = shift(self.hist['eta'], self.state['eta'])
        self.hist['ad'] = shift(self.hist['ad'], self.state['adequacy'])
        self.hist['drum'] = shift(self.hist['drum'], self.state['drum'])
        self.hist['steam'] = shift(self.hist['steam'], self.state['steamflow'])
        self.hist['fw'] = shift(self.hist['fw'], self.state['fwflow'])
        self.hist['tsteam'] = shift(self.hist['tsteam'], self.state['tsteam'])
        self.hist['tstack'] = shift(self.hist['tstack'], self.state['tstack'])
        self.hist['air'] = shift(self.hist['air'], p['ea'])
        self.hist['spray'] = shift(self.hist['spray'], self.state['spray'] * 3)
        self.hist['inst'] = shift(self.hist['inst'], 0)
        self.hist['fwsp'] = shift(self.hist['fwsp'], fw_sp)
        self.hist['mode'] = shift(self.hist['mode'], 30 * mode_id)
        self.hist['fg_o2'] = shift(self.hist['fg_o2'], self.state['fg_o2'])
        self.hist['fg_co2'] = shift(self.hist['fg_co2'], self.state['fg_co2'])
        self.hist['fg_co_ppm'] = shift(self.hist['fg_co_ppm'], self.state['fg_co_ppm'])
        self.hist['fg_nox_ppm'] = shift(self.hist['fg_nox_ppm'], self.state['fg_nox_ppm'])
        self.hist['fg_uhc_ppmc'] = shift(self.hist['fg_uhc_ppmc'], self.state['fg_uhc_ppmc'])
        vals = {'region': model['region'], 'tsat': f"{model['Tsat']:.2f}", 'hf': f"{model['hf']:.1f}", 'hg': f"{model['hg']:.1f}", 'rhos': f"{model['rho_steam']:.3f}", 'rhof': f"{model['rho_fw']:.1f}", 'msteam': f"{model['msteam_actual']:.2f}", 'msteamc': f"{model['msteam_comp']:.2f}", 'mfw': f"{model['mfw_actual']:.2f}", 'mfwc': f"{model['mfw_comp_meas']:.2f}", 'drum': f"{self.state['drum']:.1f}", 'mode': mode_name, 'o2': f"{self.state['o2']:.3f}", 'eta': f"{self.state['eta']:.2f}", 'qboiler': f"{self.state['qboiler']:.1f}", 'qsteam': f"{self.state['qsteam']:.1f}", 'ad': f"{self.state['adequacy']:.1f}", 'steamcap': f"{self.state['steam_capacity']:.2f}", 'fuelbalance': f"{self.state['fuel_balance_pct']:.1f}", 'tmid': f"{self.state['tmid']:.1f}", 'tsteam': f"{self.state['tsteam']:.1f}", 'tstack': f"{self.state['tstack']:.1f}", 'spray': f"{self.state['spray']:.1f}", 'fwsp': f"{fw_sp:.2f}", 'fwvalve': f"{self.state['fwvalve']:.2f}", 'alarm': alarm_txt, 'trip': trip_txt, 'fuelrate': f"{self.state['actual_fuel_user_flow']:.2f} {self.state['fuel_unit']} actual ({self.state['firing_factor']:.2f}x)"}
        for k, v in vals.items():
            self.out[k].setText(v)
        self.conv['usr'].setText(f"{self.state['fuel_user_flow']:.2f}")
        self.conv['unit'].setText(self.state['fuel_unit'])
        self.conv['nmol'].setText(f"{p['nf']:.3f}")
        self.conv['mkg'].setText(f"{p['fuel_mass_kgps']:.4f}")
        self.conv['stoair'].setText(f"{model['stoair']:.3f}")
        self.conv['actair'].setText(f"{model['actair']:.3f}")
        self.conv['o2dry'].setText(f"{model['dry_O2']:.3f}")
        self.conv['co2dry'].setText(f"{model['dry_CO2']:.3f}")
        self.conv['codry'].setText(f"{model['dry_CO']:.3f}")
        self.diag['lambda'].setText(f"{model['lambda_']:.3f}")
        self.diag['phi'].setText(f"{model['phi']:.3f}")
        self.diag['ce'].setText(f"{model['ce']:.3f}")
        self.diag['flue'].setText(f"{model['flue_total']:.3f}")
        self.diag['mode'].setText(mode_name)
        condition, reason, action, effnote, fg_color = self.flue_diagnosis(p, model)
        if self.fg:
            self.fg['o2'].setText(f"{self.state['fg_o2']:.2f}")
            self.fg['co2'].setText(f"{self.state['fg_co2']:.2f}")
            self.fg['co'].setText(f"{self.state['fg_co_ppm']:.0f}")
            self.fg['nox'].setText(f"{self.state['fg_nox_ppm']:.0f}")
            self.fg['nox3'].setText(f"{self.state['nox_corrected_3pct']:.0f}")
            self.fg['uhc'].setText(f"{self.state['fg_uhc_ppmc']:.0f}")
            self.fg['flamet'].setText(f"{model['flame_temp']:.0f}")
            self.fg['noxparts'].setText(
                f"{model['thermal_nox']:.0f} / {model['fuel_nox']:.0f} / "
                f"{model['prompt_nox']:.0f}"
            )
            self.fg['stack'].setText(f"{self.state['fg_stack']:.1f}")
            self.fg['dewpoint'].setText(f"{self.state['dew_point']:.1f}")
            self.fg['dewmargin'].setText(f"{self.state['dew_margin']:.1f}")
            self.fg['lambda'].setText(f"{model['lambda_']:.3f}")
            self.fg['phi'].setText(f"{model['phi']:.3f}")
            self.fg['cofrac'].setText(f"{100 * model['co_carbon_frac']:.2f}")
            self.fg['capture'].setText(f"{model['effective_capture']:.3f}")
            self.fg['diagnosis'].setText(condition)
            self.fg['action'].setText(action)
            self.fg['effnote'].setText(effnote)
            self.fg['diagnosis'].setStyleSheet(f"background:{fg_color}; padding:3px;")
            self.fg_msg.setText(f"{condition}\nReason: {reason}\nAction: {action}\nEfficiency note: {effnote}")
            self.fg_msg.setStyleSheet(f"background:{fg_color}; padding:10px;")
        self.tile_mode.setText(f"MODE\n{mode_name.upper()}")
        self.tile_alarm.setText(f"ALARM\n{alarm_txt.upper()}" if alarm_code > 0 else 'ALARM\nNORMAL')
        self.tile_alarm.setStyleSheet(f"background:{'#fadbc2' if alarm_code > 0 else '#d7edd7'}; padding:20px; font-weight:bold; font-size:16px;")
        self.tile_trip.setText(f"TRIP\n{trip_txt.upper()}" if self.state['trip'] == 1 else 'TRIP\nNO TRIP')
        self.tile_trip.setStyleSheet(f"background:{'#facccc' if self.state['trip'] == 1 else '#dbeaf7'}; padding:20px; font-weight:bold; font-size:16px;")
        self.tile_o2.setText(f"DRY O2\n{self.state['o2']:.2f} %")
        dew_alarm = self.state['dew_margin'] <= p['dew_margin_alarm']
        self.tile_dew.setText(f"DEW-POINT MARGIN\n{self.state['dew_margin']:.1f} C")
        self.tile_dew.setStyleSheet(f"background:{'#facccc' if dew_alarm else '#d7edd7'}; padding:20px; font-weight:bold; font-size:16px;")
        nox_alarm = self.state['fg_nox_ppm'] >= p['nox_alarm']
        self.tile_nox.setText(f"NOx\n{self.state['fg_nox_ppm']:.0f} ppm")
        self.tile_nox.setStyleSheet(f"background:{'#facccc' if nox_alarm else '#d7edd7'}; padding:20px; font-weight:bold; font-size:16px;")
        uhc_alarm = self.state['fg_uhc_ppmc'] >= p['uhc_alarm']
        self.tile_uhc.setText(f"UNBURNED HYDROCARBONS\n{self.state['fg_uhc_ppmc']:.0f} ppmC")
        self.tile_uhc.setStyleSheet(f"background:{'#facccc' if uhc_alarm else '#d7edd7'}; padding:20px; font-weight:bold; font-size:16px;")
        if self.state['fuel_warning']:
            fuel_warning_text = 'LOW FUEL FOR FEEDWATER - DRUM FILL EXPECTED'
            fuel_warning_color = '#ffd59e'
        else:
            fuel_warning_text = 'NORMAL'
            fuel_warning_color = '#d7edd7'
        self.tile_fuel_balance.setText(
            f"FUEL / FEEDWATER BALANCE\n{fuel_warning_text}\n"
            f"{self.state['fuel_balance_pct']:.0f}% adequate"
        )
        self.tile_fuel_balance.setStyleSheet(f"background:{fuel_warning_color}; padding:20px; font-weight:bold; font-size:16px;")
        self.alarm_msg.setText(f"Mode: {mode_name}\nAlarm: {alarm_txt}\nTrip: {trip_txt}\nFuel/feedwater warning: {fuel_warning_text}\nFuel-supported steam capacity: {self.state['steam_capacity']:.2f} kg/s\nFeedwater flow: {self.state['fwflow']:.2f} kg/s\nFuel/feedwater adequacy: {self.state['fuel_balance_pct']:.1f}%\nDry O2: {self.state['o2']:.2f} %\nNOx: {self.state['fg_nox_ppm']:.0f} ppm (alarm at >= {p['nox_alarm']:.0f} ppm)\nNOx corrected to 3% O2: {self.state['nox_corrected_3pct']:.0f} ppm\nUHC: {self.state['fg_uhc_ppmc']:.0f} ppmC (alarm at >= {p['uhc_alarm']:.0f} ppmC)\nDrum level: {self.state['drum']:.1f} %\nStack T: {self.state['tstack']:.1f} C\nWater dew point: {self.state['dew_point']:.1f} C\nDew-point margin: {self.state['dew_margin']:.1f} C (alarm at <= {p['dew_margin_alarm']:.1f} C)")
        if self.demo_active:
            self.status.setText(f"DEMO MODE | {self.demo_message} | Mode={mode_name} | Alarm={alarm_txt} | Trip={trip_txt} | Fuel/FW={fuel_warning_text} | Diagnosis={condition} | O2={self.state['fg_o2']:.2f}% | CO={self.state['fg_co_ppm']:.0f} ppm | NOx={self.state['fg_nox_ppm']:.0f} ppm | UHC={self.state['fg_uhc_ppmc']:.0f} ppmC.")
        else:
            self.status.setText(f"PyQt translation active. Current mode: {mode_name} | Alarm={alarm_txt} | Trip={trip_txt} | Fuel/FW={fuel_warning_text} | Flue diagnosis={condition} | O2={self.state['fg_o2']:.2f}% | CO={self.state['fg_co_ppm']:.0f} ppm | NOx={self.state['fg_nox_ppm']:.0f} ppm | UHC={self.state['fg_uhc_ppmc']:.0f} ppmC.")
        if self.log_enabled:
            self.append_log_row(self.log_file, self.state['sim_time'], mode_name, p, self.state, fw_sp, alarm_txt, trip_txt)
        self.updplots()
        self.update_time_box('Running' if self.running else 'Paused')

    def updplots(self):
        self.l1.set_ydata(self.hist['eta'])
        self.l2.set_ydata(self.hist['ad'])
        self.l3.set_ydata(self.hist['drum'])
        self.l4.set_ydata(self.hist['tsteam'])
        self.l5.set_ydata(self.hist['tstack'])
        self.l6.set_ydata(self.hist['steam'])
        self.l7.set_ydata(self.hist['fw'])
        self.l8.set_ydata(self.hist['spray'])
        self.l9.set_ydata(self.hist['mode'])

        y1 = finite_vals(self.hist['eta']) + finite_vals(self.hist['ad']) + finite_vals(self.hist['drum'])
        y2 = finite_vals(self.hist['tsteam']) + finite_vals(self.hist['tstack'])
        y3 = finite_vals(self.hist['steam']) + finite_vals(self.hist['fw']) + finite_vals(self.hist['spray']) + finite_vals(self.hist['mode'])

        lo1, hi1 = padded_limits(y1, (0, 120), min_span=20)
        lo2, hi2 = padded_limits(y2, (0, 650), min_span=50)
        lo3, hi3 = padded_limits(y3, (0, 140), min_span=20)

        self.ax1.set_ylim(lo1, hi1)
        self.ax2.set_ylim(lo2, hi2)
        self.ax3.set_ylim(lo3, hi3)
        self.canvas.draw_idle()
        self.upd_flue_plots()

    def upd_flue_plots(self):
        if not hasattr(self, 'fg_trace'):
            return
        pairs = []
        for x, y in zip(self.hist.get('fg_o2', []), self.hist.get('fg_co_ppm', [])):
            if x is None or y is None:
                continue
            try:
                if math.isnan(x) or math.isnan(y):
                    continue
            except Exception:
                continue
            pairs.append((x, y))
        if not pairs:
            return
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        self.fg_trace.set_data(xs, ys)
        self.fg_point.set_data([xs[-1]], [ys[-1]])
        self.fg_ax.set_xlim(0, max(12, min(25, max(xs) * 1.15 + 0.5)))
        self.fg_ax.set_ylim(0, max(5000, min(50000, max(ys) * 1.25 + 200)))
        nox_values = finite_vals(self.hist.get('fg_nox_ppm', []))
        self.nox_line.set_ydata(self.hist['fg_nox_ppm'])
        nox_alarm = self.getval('nox_alarm')
        self.nox_alarm_line.set_ydata([nox_alarm, nox_alarm])
        self.nox_ax.set_ylim(
            0, max(100, nox_alarm * 1.2, max(nox_values, default=0) * 1.2)
        )
        uhc_values = finite_vals(self.hist.get('fg_uhc_ppmc', []))
        self.uhc_line.set_ydata(self.hist['fg_uhc_ppmc'])
        uhc_alarm = self.getval('uhc_alarm')
        self.uhc_alarm_line.set_ydata([uhc_alarm, uhc_alarm])
        self.uhc_ax.set_ylim(
            0, max(100, uhc_alarm * 1.2, max(uhc_values, default=0) * 1.2)
        )
        self.fg_canvas.draw_idle()

    def update_time_box(self, state):
        self.time_box.setText(f"Sim t = {self.state['sim_time']:.2f} s | Wall t = {self.state['realtime']:.2f} s | {state}")


def main():
    app = QApplication(sys.argv)
    w = BoilerApp()
    splash = StartupSplash()
    screen = app.primaryScreen()
    if screen is not None:
        splash.move(screen.availableGeometry().center() - splash.rect().center())
    splash.show()

    def reveal_dashboard():
        splash.close()
        w.show()
        w.raise_()
        w.activateWindow()

    QTimer.singleShot(3000, reveal_dashboard)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
