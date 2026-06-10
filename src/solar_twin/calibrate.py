"""Per-location lux -> GHI calibration + behavior-match scoring.

GPU-independent. The model your app consumes is lux -> GHI (input lux, output
GHI), per location. Two framings (dossier 02 section 5):

  A) physical efficacy:  GHI = lux / K_site         (alpha = 1/K, beta ~ 0)
  B) empirical OLS:      GHI = a_site * lux + b_site (fitted freely)

Sprint-0 (Location_A) showed lux<->GHI is tightly linear (R^2~0.976) but the
roof-tilt-vs-horizontal geometry makes the efficacy ~33 (not the 105-120 of a
horizontal surface) — so the per-location fit IS the transfer factor we export.
The optional geometry-aware fit adds solar elevation + air_mass features, which
Sprint-0's per-season slope difference (26.5 vs 33.4) says are informative.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class LocationFit:
    location_id: str
    n_obs: int
    # app-direction model: GHI = a_lux2ghi * lux + b_lux2ghi
    a_lux2ghi: float
    b_lux2ghi: float
    r2: float
    rmse_wm2: float
    mbe_wm2: float
    efficacy_mean: float        # lux/GHI mean (lm per W/m^2)
    framing: str = "empirical_regression"

    def predict_ghi(self, lux):
        return self.a_lux2ghi * np.asarray(lux, float) + self.b_lux2ghi

    def to_dict(self):
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}


def _clean(lux, ghi):
    lux = np.asarray(lux, float)
    ghi = np.asarray(ghi, float)
    m = np.isfinite(lux) & np.isfinite(ghi)
    return lux[m], ghi[m]


def fit_location(lux, ghi, location_id: str = "?") -> LocationFit:
    """Fit GHI = a*lux + b (the app's lux->GHI direction). Reports R^2/RMSE/MBE."""
    lux, ghi = _clean(lux, ghi)
    if len(lux) < 3:
        raise ValueError("need >= 3 finite (lux, ghi) pairs")
    a, b = np.polyfit(lux, ghi, 1)
    pred = a * lux + b
    ss_res = float(np.sum((ghi - pred) ** 2))
    ss_tot = float(np.sum((ghi - ghi.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rmse = float(np.sqrt(np.mean((ghi - pred) ** 2)))
    mbe = float(np.mean(pred - ghi))
    with np.errstate(divide="ignore", invalid="ignore"):
        eff = lux / np.where(ghi != 0, ghi, np.nan)
    return LocationFit(location_id, len(lux), float(a), float(b), r2, rmse, mbe,
                       float(np.nanmean(eff)))


def behavior_match(lux, ghi) -> float:
    """Pearson r between lux and GHI — the >=0.90 'behavior match' gate metric.
    (R^2 is r**2.) Measures shape co-movement, not absolute accuracy.
    """
    lux, ghi = _clean(lux, ghi)
    if len(lux) < 3:
        return float("nan")
    return float(np.corrcoef(lux, ghi)[0, 1])


def passes_gate(lux, ghi, min_r: float = 0.90) -> bool:
    return behavior_match(lux, ghi) >= min_r


def fit_geometry_aware(lux, ghi, elevation_deg, air_mass):
    """Multiple linear fit GHI ~ lux + elevation + air_mass. Returns (coefs, r2).
    Tests whether geometry features tighten the fit beyond lux alone (Sprint-0
    hinted they would). coefs order: [intercept, lux, elevation, air_mass].
    """
    lux = np.asarray(lux, float); ghi = np.asarray(ghi, float)
    elev = np.asarray(elevation_deg, float); am = np.asarray(air_mass, float)
    m = np.isfinite(lux) & np.isfinite(ghi) & np.isfinite(elev) & np.isfinite(am)
    X = np.column_stack([np.ones(m.sum()), lux[m], elev[m], am[m]])
    coefs, *_ = np.linalg.lstsq(X, ghi[m], rcond=None)
    pred = X @ coefs
    ss_res = float(np.sum((ghi[m] - pred) ** 2))
    ss_tot = float(np.sum((ghi[m] - ghi[m].mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return coefs, r2


def cross_validate_seasons(df, lux_col="lux", ghi_col="ghi", month_col="month"):
    """Fit on one season, test on the other (does calibration transfer?).
    df needs lux, ghi, month columns. Returns dict of train->test RMSE.
    """
    import pandas as pd  # local; pandas is a runtime dep
    summer = df[df[month_col].isin([4, 5, 6, 7, 8, 9])]
    winter = df[~df[month_col].isin([4, 5, 6, 7, 8, 9])]
    out = {}
    for name, tr, te in [("summer->winter", summer, winter), ("winter->summer", winter, summer)]:
        if len(tr) < 3 or len(te) < 3:
            out[name] = None
            continue
        fit = fit_location(tr[lux_col], tr[ghi_col])
        pred = fit.predict_ghi(te[lux_col].to_numpy())
        rmse = float(np.sqrt(np.mean((te[ghi_col].to_numpy() - pred) ** 2)))
        out[name] = round(rmse, 2)
    return out
