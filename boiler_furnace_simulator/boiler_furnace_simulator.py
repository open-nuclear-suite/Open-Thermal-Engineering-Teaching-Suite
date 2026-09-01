import sys
import csv
import math
from pathlib import Path

try:
    from CoolProp.CoolProp import PropsSI
except ImportError as exc:
    raise RuntimeError(
        'CoolProp is required for accurate IF97 water/steam properties. '
        'Install the project requirements and restart the simulator.'
    ) from exc
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QCheckBox, QComboBox,
    QLineEdit, QSlider, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox, QTabWidget,
    QMessageBox, QInputDialog, QSizePolicy, QScrollArea, QToolButton, QFrame, QSplitter,
    QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem, QDoubleSpinBox,
    QHeaderView
)
from pyqtgraph_handler import BoilerPlotHandler, EnergyBalancePlot, SankeyDiagram


PROJECT_NAME = 'Live Boiler/Furnace Transient Simulator'
AUTHOR_LINE = 'maxisnote20 - 2026'
ABOUT_HTML = '''
<h2>Let Us Know Where This Software Is Used</h2>
<p>We would be delighted to hear from educators, students, researchers, and
other users of this software.</p>
<p>Please consider sending us a postcard or a short thank-you email describing:</p>
<ul>
<li>where you are using the software;</li>
<li>how it is being used, such as for teaching, laboratory exercises,
demonstrations, or self-study; and</li>
<li>any comments or experiences you would like to share.</li>
</ul>
<p><b>Email:</b> <a href="mailto:maxisnote20@gmail.com">maxisnote20@gmail.com</a></p>
<p>Your message will help us understand the educational reach of the software
and encourage its continued development. Thank you for using our software!</p>
'''
ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
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
    """Borderless startup panel displayed before the dashboard."""

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
    return PropsSI('T', 'P', pMPa * 1e6, 'Q', 0, 'IF97::Water')


def IF97_hL_p(pMPa):
    return PropsSI('H', 'P', pMPa * 1e6, 'Q', 0, 'IF97::Water') / 1000


def IF97_hV_p(pMPa):
    return PropsSI('H', 'P', pMPa * 1e6, 'Q', 1, 'IF97::Water') / 1000


def IF97_h_pT(pMPa, TK):
    # Avoid asking IF97 for the exactly saturated, ambiguous P-T state.
    ts = IF97_Tsat_p(pMPa)
    safe_t = TK - 0.01 if abs(TK - ts) < 0.01 else TK
    return PropsSI('H', 'P', pMPa * 1e6, 'T', safe_t, 'IF97::Water') / 1000


def IF97_v_pT(pMPa, TK):
    ts = IF97_Tsat_p(pMPa)
    safe_t = TK - 0.01 if abs(TK - ts) < 0.01 else TK
    return 1 / PropsSI('D', 'P', pMPa * 1e6, 'T', safe_t, 'IF97::Water')


def IF97_T_ph(pMPa, h):
    return PropsSI('T', 'P', pMPa * 1e6, 'H', h * 1000, 'IF97::Water')


def IF97_region_pT(pMPa, TK):
    Ts = IF97_Tsat_p(pMPa)
    if abs(TK - Ts) < 0.1:
        return 'Saturation boundary'
    if TK < Ts:
        return 'Compressed liquid'
    if TK < 1073.15:
        return 'Superheated steam'
    return 'High-temperature steam'


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

    # Closed teaching heat balance. Species heat capacities are representative
    # mean values over the stack range (kJ/mol-K). Stack temperature is derived
    # from the dry/wet flue sensible loss rather than prescribed separately.
    fouling = clamp(p.get('tube_fouling', 0.0), 0.0, 100.0)
    effective_capture = clamp(p['capture'] * (1.0 - 0.0035 * fouling), 0.30, 0.95)
    qfuel = nf * p['lhv']
    q_incomplete = qfuel * (1.0 - ce)
    qwall = qfuel * p['loss'] / 100
    # Moisture entering with fuel must be heated and vaporised; LHV already
    # excludes recovery of the latent heat of combustion-generated water.
    moisture_kmol_s = fuel_moisture_water / 1000.0
    q_moisture = moisture_kmol_s * (40650 + 75 * 75.3)
    q_ash = p.get('fuel_mass_kgps', 0.0) * max(p.get('fuelash', 0.0), 0.0) * 0.84 * 125
    q_fixed = q_incomplete + qwall + q_moisture + q_ash
    q_remaining = max(qfuel - q_fixed, 0.0)
    # Map the familiar capture factor to a realistic residual stack-loss share.
    # Excess air, leakage and fouling increase that share transparently.
    stack_fraction = clamp(
        0.02 + 0.22 * (1.0 - effective_capture)
        + 0.00045 * max(p['ea'], 0.0)
        + 0.00035 * max(p.get('flue_air_leak', 0.0), 0.0),
        0.025, 0.45,
    )
    qstack = q_remaining * stack_fraction
    qboiler = max(qfuel - q_fixed - qstack, 0.0)
    q_balance_error = qfuel - (qboiler + qstack + qwall + q_incomplete + q_moisture + q_ash)
    cp_flue = (
        0.044 * CO2 + 0.030 * CO + 0.031 * O2_sample
        + 0.030 * N2_sample + 0.036 * H2O + 0.045 * SO2
    )
    tstack = 25.0 + qstack / max(cp_flue, 1e-9)
    eta = 100 * qboiler / max(qfuel, 1e-12)

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
    return dict(o2=dry_O2, eta=eta, qboiler=qboiler, qsteam=qsteam_need, adequacy=adequacy, tstack=tstack, Tsat=Tsat, hf=hf, hg=hg, rho_steam=rho_steam, rho_fw=rho_fw, tmid=tmid, tsteam=tout, steam_capacity=steam_capacity, msteam_actual=msteam_actual, mfw_actual=mfw_actual, msteam_comp=msteam_comp, mfw_comp_meas=mfw_comp_meas, region=reg, stoair=nu_O2_st * 4.76 * nf, actair=O2in + N2in, dry_O2=dry_O2, dry_CO2=dry_CO2, dry_CO=dry_CO, co_ppm=co_ppm, uhc_ppmc=uhc_ppmc, lambda_=lambda_, phi=phi, ce=ce, flue_total=flue_total, water_mole_fraction=water_mole_fraction, dew_point=dew_point, flame_temp=flame_temp, thermal_nox=thermal_nox * nox_dilution, fuel_nox=fuel_nox * nox_dilution, prompt_nox=prompt_nox * nox_dilution, nox_ppm=nox_ppm, nox_corrected_3pct=nox_corrected_3pct, co_carbon_frac=co_carbon_frac, effective_capture=effective_capture, flue_air_leak=leak_air, qfuel=qfuel, qstack=qstack, qwall=qwall, q_incomplete=q_incomplete, q_moisture=q_moisture, q_ash=q_ash, q_balance_error=q_balance_error)

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
        self.setStyleSheet(
            "QToolButton { font-weight:bold; text-align:left; padding:7px; "
            "background:#205b7d; color:white; border:1px solid #3c86ae; "
            "border-radius:3px; } QToolButton:hover { background:#2b7299; }"
        )

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


class SuiteSpinRow(QWidget):
    """Nuclear-suite style numeric row with a native double spin box."""

    def __init__(self, label, vmin, vmax, value, step):
        super().__init__()
        self.vmin = vmin
        self.vmax = vmax
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label), 1)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(vmin, vmax)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(4 if step < 0.01 else 2)
        self.spin.setValue(value)
        self.spin.setKeyboardTracking(False)
        layout.addWidget(self.spin)

    def value(self):
        return self.spin.value()

    def set_value(self, value):
        self.spin.setValue(clamp(value, self.vmin, self.vmax))


class BoilerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Live Boiler/Furnace Transient Simulator - PySide6/PyQtGraph')
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
        self.demo_sequence = []
        self.demo_duration = 0.0
        self.graphs = BoilerPlotHandler(dark=getattr(self, 'suite_style', False))
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
        about_button = QPushButton('About')
        about_button.setToolTip('About this software and how to contact us')
        about_button.setStyleSheet(
            'QPushButton { background:#7d1238; color:white; border:1px solid #a94b6d; '
            'border-radius:4px; padding:7px 16px; font-weight:bold; }'
            'QPushButton:hover { background:#98204b; }'
        )
        about_button.clicked.connect(self.show_about)
        header_layout.addWidget(about_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        central_layout.addWidget(header, 0)

        splitter = QSplitter(Qt.Horizontal)
        central_layout.addWidget(splitter, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_host = QWidget()
        left_host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([620, 1100])

        view_group = QGroupBox('Interface mode')
        view_layout = QHBoxLayout(view_group)
        view_layout.addWidget(QLabel('Choose the amount of input detail:'))
        self.interface_popup = QComboBox()
        self.interface_popup.addItems(['Student view', 'Advanced engineering view'])
        self.interface_popup.currentIndexChanged.connect(self.apply_interface_mode)
        view_layout.addWidget(self.interface_popup, 1)
        left.addWidget(view_group)

        self.combustion_box = CollapsibleBox('Combustion inputs')
        self.steam_box = CollapsibleBox('Steam-side + IF97 state inputs')
        self.control_box = CollapsibleBox('Control, compensation, alarms')
        left.addWidget(self.combustion_box)
        left.addWidget(self.steam_box)
        left.addWidget(self.control_box)

        self.build_combustion()
        self.build_steam()
        self.build_control()

        self.measurements_box = self.build_measurements()
        left.addWidget(self.measurements_box)
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
        self.apply_interface_mode()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('About')
        dialog.setModal(True)
        dialog.resize(650, 610)

        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QLabel(ABOUT_HTML)
        content.setWordWrap(True)
        content.setOpenExternalLinks(True)
        content.setTextInteractionFlags(
            Qt.TextBrowserInteraction | Qt.TextSelectableByMouse
        )
        content.setStyleSheet('padding:18px; font-size:11pt; background:white;')
        scroll.setWidget(content)
        layout.addWidget(scroll)

        close_button = QPushButton('Close')
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)
        dialog.exec()

    def make_group(self, title):
        g = QGroupBox(title)
        g.setLayout(QVBoxLayout())
        g.layout().setSpacing(4)
        return g

    def add_row(self, group, label, key, vmin, vmax, v0, step):
        row_type = SuiteSpinRow if getattr(self, 'suite_widgets', False) else SliderRow
        row = row_type(label, vmin, vmax, v0, step)
        if key == 'fwcmd':
            row.setToolTip(
                'Feedwater controller output. In automatic single-, two-, or '
                'three-element drum-level control this value is adjusted by '
                'feedback; pause the run to enter and inspect a fixed value.'
            )
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
        for spec in [('Drum pressure (bar)','pbar',5,180,45,0.01),('Feedwater inlet T (C)','tfw',20,250,105,0.01),('Feedwater mass-flow rate (kg/s)','fwcmd',0,120,0.30,0.01),('Steam outlet T setpoint (C)','tsteam_sp',180,620,440,0.01),('Steam demand factor','demand',0.40,1.35,1.0,0.01),('Spray water T (C)','tspray',20,220,105,0.01),('Manual spray (%)','spray_manual',0,35,0,0.01),('Drum level SP (%)','lvl_sp',30,70,50,0.01),('Initial drum level (%)','lvl_init',20,80,50,0.01),('Steam FT bias (%)','steam_ft_bias',-10,10,0,0.01),('FW FT bias (%)','fw_ft_bias',-10,10,0,0.01),('Steam FT noise (%)','steam_ft_noise',0,5,0,0.01),('FW FT noise (%)','fw_ft_noise',0,5,0,0.01),('Steam DP signal','steam_dp',0.1,5.0,1.0,0.01),('FW DP signal','fw_dp',0.1,5.0,1.0,0.01)]:
            self.add_row(self.steam_box, *spec)

    def build_control(self):
        for spec in [('O2 setpoint (%)','o2_sp',1,8,3,0.01),('Air PI Kp','air_kp',0,8,1.6,0.01),('Air PI Ki','air_ki',0,1.0,0.12,0.01),('Outer steam PI Kp','out_kp',0,8,1.0,0.01),('Outer steam PI Ki','out_ki',0,1.0,0.06,0.01),('Inner spray PI Kp','in_kp',0,8,1.5,0.01),('Inner spray PI Ki','in_ki',0,1.0,0.12),('Level PI Kp','lvl_kp',0,5,0.8,0.01),('Level PI Ki','lvl_ki',0,0.5,0.05,0.01),('Flow PI Kp','fw_kp',0,5,0.35,0.01),('Flow PI Ki','fw_ki',0,0.5,0.08,0.01),('Mid-temp bias (C)','mid_bias',5,80,30,0.01),('LL drum alarm (%)','lvl_ll',5,45,25,0.01),('HH drum alarm (%)','lvl_hh',55,95,75,0.01),('Steam T HH trip (C)','ttrip',350,650,540,0.01),('Stack T HH alarm (C)','stack_hh',150,450,280,0.01),('Minimum dew-point margin (C)','dew_margin_alarm',0,50,15,0.5),('NOx high alarm (ppm)','nox_alarm',50,1500,300,1),('UHC high alarm (ppmC)','uhc_alarm',50,10000,500,10),('Fuel/FW warning margin (%)','fuel_warn_margin',0,50,10,1),('Fuel/FW warning delay (s)','fuel_warn_delay',1,60,10,1),('Burner mixing quality (%)','burner_mixing',30,100,95,0.01),('Post-furnace air leak (%)','flue_air_leak',0,80,0,0.01),('Tube fouling / soot (%)','tube_fouling',0,100,0,0.01),('Analyzer lag (s)','analyzer_lag',0.5,30,8,0.01),('Analyzer noise level','analyzer_noise',0,5,0,0.01)]:
            self.add_row(self.control_box, *(spec if len(spec) == 6 else (*spec, 0.01)))

    def make_value_label(self):
        lab = QLabel('--')
        lab.setStyleSheet('background:white; padding:3px;')
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lab

    def build_measurements(self):
        g = QGroupBox('Measurements / indications')
        grid = QGridLayout(g)
        left_items = [('Region guess','region'),('Sat T (C)','tsat'),('h_f (kJ/kg)','hf'),('h_g (kJ/kg)','hg'),('rho_steam (kg/m3)','rhos'),('rho_fw (kg/m3)','rhof'),('Steam flow actual (kg/s)','msteam'),('Steam flow comp (kg/s)','msteamc'),('FW flow actual (kg/s)','mfw'),('FW flow comp (kg/s)','mfwc'),('Drum level (%)','drum'),('Drum mode active','mode'),('Dry O2 (%)','o2')]
        right_items = [('Efficiency (%)','eta'),('Boiler heat (kW)','qboiler'),('Steam duty need (kW)','qsteam'),('Adequacy (%)','ad'),('Fuel-supported steam cap. (kg/s)','steamcap'),('Fuel/FW adequacy (%)','fuelbalance'),('Mid steam T (C)','tmid'),('Final steam T (C)','tsteam'),('Stack T (C)','tstack'),('Stack / wall loss (kW)','heatloss'),('Incomplete / moisture loss (kW)','chemloss'),('Heat-balance residual (kW)','balance'),('Spray cmd (%)','spray'),('FW flow SP (kg/s)','fwsp'),('FW mass-flow cmd (kg/s)','fwvalve'),('Alarm state','alarm'),('Trip state','trip'),('Fuel basis rate','fuelrate')]
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
        g = QGroupBox('Live operation')
        outer = QVBoxLayout(g)

        run_group = QGroupBox('Run control')
        run_layout = QHBoxLayout(run_group)
        for txt, cb in (
            ('Start', self.start_cb), ('Pause', self.pause_cb),
            ('Resume', self.resume_cb), ('Step', self.step_cb),
            ('Reset', self.reset_cb), ('Reset Trip', self.trip_reset_cb),
        ):
            button = QPushButton(txt)
            button.clicked.connect(cb)
            run_layout.addWidget(button)
        outer.addWidget(run_group)

        mode_group = QGroupBox('Control mode')
        mode_layout = QGridLayout(mode_group)
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
        mode_layout.addWidget(QLabel('Drum-level strategy'), 0, 0)
        mode_layout.addWidget(self.mode_popup, 0, 1, 1, 2)
        mode_layout.addWidget(QLabel('Speed'), 0, 3)
        mode_layout.addWidget(self.speed_popup, 0, 4)
        mode_layout.addWidget(self.auto_air, 1, 0)
        mode_layout.addWidget(self.auto_steam, 1, 1)
        mode_layout.addWidget(self.dens_comp, 1, 2)
        mode_layout.addWidget(self.bumpless, 1, 3)
        mode_layout.addWidget(self.coordinated_firing, 1, 4)
        outer.addWidget(mode_group)

        demo_group = QGroupBox('Demonstrations and cases')
        demo_layout = QHBoxLayout(demo_group)
        self.demo_popup = QComboBox()
        self.demo_popup.addItems([
            'Guided boiler tour',
            'Load response and drum level',
            'Combustion and emissions',
            'Heat-transfer fouling',
        ])
        demo_layout.addWidget(QLabel('Demo'))
        demo_layout.addWidget(self.demo_popup, 1)
        for txt, cb in (
            ('Start Demo', self.start_demo_cb), ('Stop Demo', self.stop_demo_cb),
            ('Load Case', self.case_cb),
        ):
            button = QPushButton(txt)
            button.clicked.connect(cb)
            demo_layout.addWidget(button)
        outer.addWidget(demo_group)

        disturbance_group = QGroupBox('Disturbances and trend tools')
        disturbance_layout = QHBoxLayout(disturbance_group)
        for txt, cb in (
            ('Demand +10%', self.disturb_demand_up_cb),
            ('Demand -10%', self.disturb_demand_dn_cb),
            ('Fuel quality -5%', self.disturb_lhv_cb),
            ('Clear Trends', self.clear_cb),
        ):
            button = QPushButton(txt)
            button.clicked.connect(cb)
            disturbance_layout.addWidget(button)
        outer.addWidget(disturbance_group)

        log_group = QGroupBox('CSV logging')
        log_layout = QHBoxLayout(log_group)
        self.log_check = QCheckBox('Enable CSV logging')
        self.log_check.stateChanged.connect(self.toggle_log_cb)
        self.log_name = QLineEdit(self.log_file)
        export_button = QPushButton('Show Log Path')
        export_button.clicked.connect(self.export_log_cb)
        log_layout.addWidget(self.log_check)
        log_layout.addWidget(self.log_name, 1)
        log_layout.addWidget(export_button)
        outer.addWidget(log_group)

        self.time_box = QLabel('Sim t = 0.0 s | Wall t = 0.0 s | Paused')
        self.time_box.setStyleSheet('background:#e0ebf7; padding:6px;')
        outer.addWidget(self.time_box)
        self.demo_box = QLabel('Demo mode: off. Click Start Demo for a guided tour of boiler response, flue-gas diagnosis, and fault interpretation.')
        self.demo_box.setWordWrap(True)
        self.demo_box.setStyleSheet('background:#f0f7ff; padding:8px; border:1px solid #bdd7ee;')
        outer.addWidget(self.demo_box)
        return g

    def apply_interface_mode(self):
        """Progressively disclose tuning and model-detail controls."""
        if not hasattr(self, 'interface_popup'):
            return
        advanced = self.interface_popup.currentIndex() == 1
        self.control_box.setVisible(True)
        student_rows = {
            'fuel_flow_user', 'ea', 'tair', 'tfuel', 'lhv', 'mwfuel',
            'pbar', 'tfw', 'fwcmd', 'tsteam_sp', 'demand', 'lvl_sp', 'lvl_init',
            'o2_sp', 'lvl_ll', 'lvl_hh', 'stack_hh', 'dew_margin_alarm',
        }
        for key, row in self.rows.items():
            row.setVisible(advanced or key in student_rows)
        self.lock_comp.setVisible(advanced)
        if hasattr(self, 'status'):
            self.status.setText(
                'Student view: essential operating, setpoint and alarm inputs '
                'are shown; diagnostics and guided exercises remain available.'
                if not advanced else
                'Advanced engineering view: model assumptions, tuning and '
                'instrumentation controls are available.'
            )

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
        self.tabs.addTab(self.build_emissions_trends_tab(), 'Combustion & Emissions')
        self.tabs.addTab(self.build_diag_tab(), 'Diagnostics')
        self.tabs.addTab(self.build_sankey_tab(), 'Energy Balance')
        self.tabs.addTab(self.build_flue_tab(), 'Flue Gas')
        self.tabs.addTab(self.build_alarm_tab(), 'Alarms')
        return g

    def build_emissions_trends_tab(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        w = QWidget()
        lay = QVBoxLayout(w)
        note = QLabel(
            'Virtual analyzer and combustion-air trends. O2 and CO2 show air '
            'margin and dilution; CO and UHC indicate incomplete burnout. NOx '
            'is a simplified teaching estimate, not a regulatory prediction.'
        )
        note.setWordWrap(True)
        note.setStyleSheet('background:#e5f0fa; padding:8px;')
        lay.addWidget(note)
        plots = (
            ('em_air_plot', 'Combustion-air indicators', 'Dry gas / excess air (%)'),
            ('em_co_plot', 'Carbon monoxide', 'CO (ppm)'),
            ('em_nox_plot', 'Nitrogen oxides', 'NOx (ppm, dry)'),
            ('em_uhc_plot', 'Unburned hydrocarbons', 'UHC (ppmC, dry)'),
        )
        for attr, title, ylabel in plots:
            plot = self.graphs.line_plot(title, 'Time before present (simulated s)', ylabel)
            plot.setMinimumHeight(240)
            plot.setXRange(self.hist_t[0], self.hist_t[-1], padding=0)
            setattr(self, attr, plot)
            lay.addWidget(plot)
        self.em_o2_line = self.graphs.add_line(self.em_air_plot, 'Analyzer O2', '#2563a6')
        self.em_co2_line = self.graphs.add_line(self.em_air_plot, 'Analyzer CO2', '#16803c')
        self.em_air_line = self.graphs.add_line(self.em_air_plot, 'Excess air command', '#6b7280', Qt.DashLine)
        self.em_co_line = self.graphs.add_line(self.em_co_plot, 'Analyzer CO', '#b22222')
        self.em_nox_line = self.graphs.add_line(self.em_nox_plot, 'Analyzer NOx', '#7d1238')
        self.em_uhc_line = self.graphs.add_line(self.em_uhc_plot, 'Analyzer UHC', '#8b5a2b')
        self.em_co_caution = self.em_co_plot.addLine(y=500, pen={'color': '#d97706', 'style': Qt.DashLine})
        self.em_nox_alarm = self.em_nox_plot.addLine(y=self.getval('nox_alarm'), pen={'color': 'red', 'style': Qt.DashLine})
        self.em_uhc_alarm = self.em_uhc_plot.addLine(y=self.getval('uhc_alarm'), pen={'color': 'red', 'style': Qt.DashLine})
        outer.setWidget(w)
        return outer

    def build_sankey_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        note = QLabel(
            'Live fuel-energy balance. Arrow widths are proportional to heat '
            'flow; the numerical residual should remain approximately zero.'
        )
        note.setWordWrap(True)
        note.setStyleSheet('background:#e5f0fa; padding:8px;')
        lay.addWidget(note)
        views = QSplitter(Qt.Vertical)
        dark_plots = getattr(self, 'suite_style', False)
        self.energy_plot = EnergyBalancePlot(dark=dark_plots)
        self.sankey_diagram = SankeyDiagram(dark=dark_plots)
        views.addWidget(self.sankey_diagram)
        views.addWidget(self.energy_plot)
        views.setSizes([360, 320])
        lay.addWidget(views, 1)
        self.sankey_summary = QLabel('Run or step the simulation to populate the energy balance.')
        self.sankey_summary.setWordWrap(True)
        self.sankey_summary.setStyleSheet('background:#f6f6f6; padding:8px;')
        lay.addWidget(self.sankey_summary)
        return w

    def update_sankey(self, model):
        if not hasattr(self, 'energy_plot'):
            return
        qfuel = max(model.get('qfuel', 0.0), 1e-9)
        losses = [
            model.get('qboiler', 0.0),
            model.get('qstack', 0.0),
            model.get('qwall', 0.0),
            model.get('q_incomplete', 0.0),
            model.get('q_moisture', 0.0) + model.get('q_ash', 0.0),
        ]
        labels = ['Useful boiler heat', 'Stack loss', 'Wall loss',
                  'Incomplete combustion', 'Moisture + ash']
        self.sankey_diagram.set_balance(qfuel, labels, losses)
        self.energy_plot.set_balance(labels, losses)
        residual = model.get('q_balance_error', 0.0)
        self.sankey_summary.setText(
            f"Fuel input {qfuel:.1f} kW | Useful heat {losses[0]:.1f} kW "
            f"({100 * losses[0] / qfuel:.1f}%) | Total losses "
            f"{sum(losses[1:]):.1f} kW | Balance residual {residual:.6f} kW"
        )

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

        self.trend_plots = []
        for title, ylabel in (
            ('Efficiency / adequacy / drum', 'Percent'),
            ('Steam T / stack T', 'Temperature (C)'),
            ('Steam flow, FW flow, spray x3, mode x30', 'Scaled value'),
        ):
            plot = self.graphs.line_plot(title, 'Time before present (simulated s)', ylabel)
            plot.setMinimumHeight(290)
            plot.setXRange(self.hist_t[0], self.hist_t[-1], padding=0)
            self.trend_plots.append(plot)
            lay.addWidget(plot)
        self.l1 = self.graphs.add_line(self.trend_plots[0], 'Efficiency', '#2563eb')
        self.l2 = self.graphs.add_line(self.trend_plots[0], 'Adequacy', '#16a34a')
        self.l3 = self.graphs.add_line(self.trend_plots[0], 'Drum', '#f59e0b', Qt.DashLine)
        self.l4 = self.graphs.add_line(self.trend_plots[1], 'Steam T', '#dc2626')
        self.l5 = self.graphs.add_line(self.trend_plots[1], 'Stack T', '#a21caf')
        self.l6 = self.graphs.add_line(self.trend_plots[2], 'Steam', '#0891b2', Qt.DashLine)
        self.l7 = self.graphs.add_line(self.trend_plots[2], 'FW', '#16a34a', Qt.DashLine)
        self.l8 = self.graphs.add_line(self.trend_plots[2], 'Spray x3', '#f8fafc', Qt.DotLine)
        self.l9 = self.graphs.add_line(self.trend_plots[2], 'Mode x30', '#ca8a04', Qt.DotLine)

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

        self.fg_plot = self.graphs.line_plot(
            'Combustion map: dry O2 vs CO', 'Dry O2 analyzer reading (%)',
            'Dry CO analyzer reading (ppm)',
        )
        self.nox_plot = self.graphs.line_plot(
            'Estimated NOx trend (teaching model)',
            'Time before present (simulated s)', 'Dry NOx (ppm)',
        )
        self.uhc_plot = self.graphs.line_plot(
            'Estimated unburned hydrocarbons (teaching model)',
            'Time before present (simulated s)', 'Dry UHC (ppmC)',
        )
        for plot in (self.fg_plot, self.nox_plot, self.uhc_plot):
            plot.setMinimumHeight(300)
            lay.addWidget(plot)
        self.fg_trace = self.graphs.add_line(self.fg_plot, 'Recent path', '#111827')
        self.fg_point = self.fg_plot.plot([], [], pen=None, symbol='o', symbolBrush='#dc2626', symbolSize=8, name='Current')
        self.fg_plot.addLine(y=500, pen={'color': '#d97706', 'style': Qt.DashLine})
        self.fg_plot.addLine(y=2000, pen={'color': '#dc2626', 'style': Qt.DotLine})
        self.nox_line = self.graphs.add_line(self.nox_plot, 'Analyzer NOx', '#7d1238')
        self.nox_alarm_line = self.nox_plot.addLine(y=self.getval('nox_alarm'), pen={'color': 'red', 'style': Qt.DashLine})
        self.uhc_line = self.graphs.add_line(self.uhc_plot, 'Analyzer UHC', '#8b5a2b')
        self.uhc_alarm_line = self.uhc_plot.addLine(y=self.getval('uhc_alarm'), pen={'color': 'red', 'style': Qt.DashLine})

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
        components = ['CH4', 'C2H6', 'C3H8', 'H2', 'CO', 'CO2', 'N2', 'H2S']
        active = [(key, value) for key, value in self.mix.items() if value > 0]
        active = (active + [(key, 0.0) for key in components if key not in dict(active)])[:5]
        result = self.edit_fraction_table(
            'Edit gas mixture', components, active,
            'Choose up to five gas components. Entered fractions are normalized to 100%.',
            selectable_components=True,
        )
        if result is None:
            return
        self.mix = {key: result.get(key, 0.0) for key in components}
        self.fuel_popup.setCurrentIndex(self.fuels.index('User-defined gas mixture'))
        self.fuel_cb()

    def liquid_blend_cb(self):
        keys = ['FuelOil', 'Diesel', 'Gasoline', 'Kerosene']
        result = self.edit_fraction_table(
            'Edit liquid blend', keys, list(self.mixl.items()),
            'All liquid stocks supported by the current property model are shown; no smaller component-count limit is imposed.',
            selectable_components=False,
        )
        if result is None:
            return
        self.mixl = {key: result.get(key, 0.0) for key in keys}
        self.fuel_popup.setCurrentIndex(self.fuels.index('User-defined liquid blend'))
        self.fuel_cb()

    def edit_fraction_table(self, title, components, rows, note, selectable_components):
        """Edit mixture fractions in one table and return normalized values."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(540, 360)
        layout = QVBoxLayout(dialog)
        explanation = QLabel(note)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(['Component', 'Fraction (%)'])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        fraction_boxes = []
        component_boxes = []
        for row_index, (component, fraction) in enumerate(rows):
            if selectable_components:
                selector = QComboBox()
                selector.addItems(components)
                selector.setCurrentText(component)
                table.setCellWidget(row_index, 0, selector)
                component_boxes.append(selector)
            else:
                item = QTableWidgetItem(component)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_index, 0, item)
            fraction_box = QDoubleSpinBox()
            fraction_box.setRange(0.0, 1000.0)
            fraction_box.setDecimals(3)
            fraction_box.setValue(fraction)
            fraction_box.setSuffix(' %')
            table.setCellWidget(row_index, 1, fraction_box)
            fraction_boxes.append(fraction_box)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return None
        values = {}
        for row_index, fraction_box in enumerate(fraction_boxes):
            component = (
                component_boxes[row_index].currentText()
                if selectable_components else table.item(row_index, 0).text()
            )
            values[component] = values.get(component, 0.0) + fraction_box.value()
        total = sum(values.values())
        if total <= 0:
            QMessageBox.warning(self, title, 'At least one component must have a positive fraction.')
            return None
        return {component: 100.0 * value / total for component, value in values.items()}

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
        vals.update(steam_ft_noise=0, fw_ft_noise=0, analyzer_noise=0)
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
        """Run the selected demonstration without stealing the active tab."""
        # Reset first so the demo always starts from a clean, predictable point.
        self.reset_cb()
        self.demo_active = True
        self.demo_stage = None
        self.demo_start_sim_time = self.state['sim_time']
        self.demo_message = 'Starting guided demo tour.'
        sequences = {
            0: [(0, 12), (1, 18), (2, 20), (3, 20), (4, 20), (5, 22), (6, 22), (7, 22), (8, 20)],
            1: [(0, 12), (1, 35), (8, 20)],
            2: [(0, 10), (2, 18), (4, 20), (5, 20), (6, 20), (8, 18)],
            3: [(0, 12), (7, 35), (8, 20)],
        }
        self.demo_sequence = sequences[self.demo_popup.currentIndex()]
        self.demo_duration = sum(duration for _stage, duration in self.demo_sequence)
        self.mode_popup.setCurrentIndex(3)
        self.auto_air.setChecked(True)
        self.auto_steam.setChecked(True)
        self.dens_comp.setChecked(True)
        self.bumpless.setChecked(True)
        self.speed_popup.setCurrentIndex(3)  # 5x for a lively exhibition demo
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
        self.pause_cb()

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
            self.demo_message = '1/8 Stable automatic operation: O2 trim and steam-temperature cascade hold the boiler near a clean, efficient point.'
        elif stage == 1:
            self.setpair('demand', 1.22)
            self.auto_air.setChecked(True)
            self.auto_steam.setChecked(True)
            self.demo_message = '2/8 Demand step: steam demand is increased so visitors can see the transient response in boiler heat, drum level, and steam temperature.'
        elif stage == 2:
            self.auto_air.setChecked(False)
            self.setpair('ea', 45)
            self.setpair('burner_mixing', 96)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.demo_message = '3/8 Excess-air case: O2 rises, CO stays low, CO2 is diluted, and efficiency is penalized by stack loss.'
        elif stage == 3:
            self.auto_air.setChecked(True)
            self.setpair('o2_sp', 3.0)
            self.demo_message = '4/8 Automatic recovery: O2 trim brings excess air back toward the target while the flue-gas map traces the operating path.'
        elif stage == 4:
            self.auto_air.setChecked(False)
            self.setpair('ea', 0)
            self.setpair('burner_mixing', 82)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.demo_message = '5/8 Air-starved firing: O2 collapses and CO breaks through sharply, showing why O2 margin and CO monitoring matter.'
        elif stage == 5:
            self.auto_air.setChecked(False)
            self.setpair('ea', 16)
            self.setpair('burner_mixing', 55)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.demo_message = '6/8 Poor burner mixing: CO remains high even though O2 is not extremely low, illustrating why O2 alone is not enough.'
        elif stage == 6:
            self.auto_air.setChecked(False)
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 35)
            self.setpair('tube_fouling', 0)
            self.demo_message = '7/8 Post-furnace air leakage: measured O2 rises and CO2 is diluted, but the extra air did not help the flame.'
        elif stage == 7:
            self.auto_air.setChecked(False)
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 60)
            self.demo_message = '8/8 Fouling/soot case: stack temperature rises and effective heat capture falls, highlighting heat-transfer maintenance.'
        elif stage == 8:
            self.auto_air.setChecked(True)
            self.auto_steam.setChecked(True)
            self.setpair('demand', 1.0)
            self.setpair('ea', 15)
            self.setpair('burner_mixing', 95)
            self.setpair('flue_air_leak', 0)
            self.setpair('tube_fouling', 0)
            self.demo_message = 'Final recovery: all demo faults are cleared and automatic operation resumes. Click Start Demo again to replay.'

    def update_demo_mode(self):
        if not self.demo_active:
            return
        t = max(0.0, self.state['sim_time'] - self.demo_start_sim_time)
        elapsed = 0.0
        stage = None
        for candidate, duration in self.demo_sequence:
            elapsed += duration
            if t < elapsed:
                stage = candidate
                break
        if stage is None:
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
            self.demo_box.setText(
                f'Demo mode running | t = {t:.1f} s / {self.demo_duration:.0f} s | '
                f'{self.demo_message}'
            )

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
        self.setpair('analyzer_noise', 0)
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
        vals = {'region': model['region'], 'tsat': f"{model['Tsat']:.2f}", 'hf': f"{model['hf']:.1f}", 'hg': f"{model['hg']:.1f}", 'rhos': f"{model['rho_steam']:.3f}", 'rhof': f"{model['rho_fw']:.1f}", 'msteam': f"{model['msteam_actual']:.2f}", 'msteamc': f"{model['msteam_comp']:.2f}", 'mfw': f"{model['mfw_actual']:.2f}", 'mfwc': f"{model['mfw_comp_meas']:.2f}", 'drum': f"{self.state['drum']:.1f}", 'mode': mode_name, 'o2': f"{self.state['o2']:.3f}", 'eta': f"{self.state['eta']:.2f}", 'qboiler': f"{self.state['qboiler']:.1f}", 'qsteam': f"{self.state['qsteam']:.1f}", 'ad': f"{self.state['adequacy']:.1f}", 'steamcap': f"{self.state['steam_capacity']:.2f}", 'fuelbalance': f"{self.state['fuel_balance_pct']:.1f}", 'tmid': f"{self.state['tmid']:.1f}", 'tsteam': f"{self.state['tsteam']:.1f}", 'tstack': f"{self.state['tstack']:.1f}", 'heatloss': f"{model['qstack']:.1f} / {model['qwall']:.1f}", 'chemloss': f"{model['q_incomplete']:.1f} / {model['q_moisture'] + model['q_ash']:.1f}", 'balance': f"{model['q_balance_error']:.6f}", 'spray': f"{self.state['spray']:.1f}", 'fwsp': f"{fw_sp:.2f}", 'fwvalve': f"{self.state['fwvalve']:.2f}", 'alarm': alarm_txt, 'trip': trip_txt, 'fuelrate': f"{self.state['actual_fuel_user_flow']:.2f} {self.state['fuel_unit']} actual ({self.state['firing_factor']:.2f}x)"}
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
        # Keep physics at 4 Hz while limiting GUI rendering work to 2 Hz.
        # PyQtGraph updates are inexpensive, but the energy view still contains
        # text and bars that do not benefit from being rebuilt every model step.
        if self.tick % 2 == 0:
            self.update_sankey(model)
            self.updplots()
        self.update_time_box('Running' if self.running else 'Paused')

    def updplots(self):
        for item, key in (
            (self.l1, 'eta'), (self.l2, 'ad'), (self.l3, 'drum'),
            (self.l4, 'tsteam'), (self.l5, 'tstack'), (self.l6, 'steam'),
            (self.l7, 'fw'), (self.l8, 'spray'), (self.l9, 'mode'),
        ):
            self.graphs.update_line(item, self.hist_t, self.hist[key])
        self.upd_emissions_plots()
        self.upd_flue_plots()

    def upd_emissions_plots(self):
        if not hasattr(self, 'em_co_line'):
            return
        for item, key in (
            (self.em_o2_line, 'fg_o2'), (self.em_co2_line, 'fg_co2'),
            (self.em_air_line, 'air'), (self.em_co_line, 'fg_co_ppm'),
            (self.em_nox_line, 'fg_nox_ppm'), (self.em_uhc_line, 'fg_uhc_ppmc'),
        ):
            self.graphs.update_line(item, self.hist_t, self.hist[key])
        self.em_nox_alarm.setValue(self.getval('nox_alarm'))
        self.em_uhc_alarm.setValue(self.getval('uhc_alarm'))

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
        self.fg_trace.setData(xs, ys)
        self.fg_point.setData([xs[-1]], [ys[-1]])
        self.graphs.update_line(self.nox_line, self.hist_t, self.hist['fg_nox_ppm'])
        self.graphs.update_line(self.uhc_line, self.hist_t, self.hist['fg_uhc_ppmc'])
        self.nox_alarm_line.setValue(self.getval('nox_alarm'))
        self.uhc_alarm_line.setValue(self.getval('uhc_alarm'))

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
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
