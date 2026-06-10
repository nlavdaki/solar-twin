r"""Physically-structured inverse model: twin plane-of-array illuminance -> GHI.

The forward solar-engineering chain is irradiance -> illuminance via LUMINOUS
EFFICACY (spectral, air-mass dependent) and TRANSPOSITION (horizontal -> tilted
plane, geometry dependent). A single constant-efficacy fit GHI = a*lux + b
ignores both, which is why it caps at R^2 ~ 0.88 at a tilted/occluded pixel and
why a diffuse-fraction filter is needed to rescue it. This module INVERTS the
forward chain so the twin's measured illuminance at a roof pixel maps back to
horizontal GHI while staying physically interpretable and extensible to all-sky
(the next paper just adds cloud/aerosol/water terms to the same structure).

Model (per row):   GHI = lux / D ,   D = sum_j  a_j * k_j

with DIMENSIONLESS geometric kernels k_j computed (NOT fitted) from solar
position, the pixel's surface geometry, and the diffuse fraction kd = DHI/GHI:

  k_beam = (1 - kd) * max(cosAOI, 0) * visible / cos(zenith)   # beam stream
  k_diff = kd * SVF                                            # isotropic diffuse
  k_grnd = albedo * (1 - SVF)                                  # ground-reflected

  cosAOI  = cos z cos b + sin z sin b cos(gamma_sun - gamma_surface)   (Duffie-Beckman)
  visible = 1 if the pixel sees the sun (cosAOI>0 AND sun above local horizon) else 0
  SVF     = sky-view factor in [0,1]  (1 = fully open horizontal; tilt+obstruction reduce it)

The fitted a_j are LUMINOUS EFFICACIES (lm per W/m^2). After geometric
correction a_beam should land near the literature ~95-115 lm/W and a_diff
~120-130 lm/W (Perez et al. 1990) -- the physical sanity check that separates
"physics" from "curve fitting".

A site with NO extracted geometry defaults to horizontal & sky-open (tilt=0,
SVF=1), for which k_beam=(1-kd), k_diff=kd, so the model degrades gracefully to
a proper kd-weighted (diffuse-aware) global efficacy -- still better than a
constant. Geometry (tilt / SVF / horizon) matters most for tilted (H) and
occluded (J) pixels.

References: Perez et al. 1990 (luminous efficacy + anisotropic transposition);
Liu & Jordan 1960 (isotropic sky / clearness index); Kasten & Young 1989 (air
mass); Erbs 1982 / Reindl 1990 (diffuse-fraction decomposition).
GPU-independent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

N_AZ_BINS = 36  # horizon-profile resolution: 36 bins of 10 deg each
_SINGLE = "_single_"  # site key when a frame has no location_id

# Below this tilt, treat the pixel as horizontal: the tilt projection is tiny
# (sin 15deg ~ 0.26) and an unreconciled surface-azimuth convention would do
# more harm than good (verified at Thissio: 11deg + wrong azimuth dropped R2
# 0.95 -> 0.73; treating it as flat keeps 0.95). SVF/horizon are still applied.
AUTO_FLAT_TILT_DEG = 15.0


@dataclass
class SiteGeometry:
    """Static per-pixel geometry, extracted once from the twin (Isaac raycast).

    azimuth/horizon use the pvlib convention: degrees clockwise from North
    (N=0, E=90, S=180, W=270).
    """
    tilt_deg: float = 0.0          # 0 = horizontal
    azimuth_deg: float = 180.0     # surface-facing azimuth (irrelevant when tilt=0)
    svf: float = 1.0               # sky-view factor [0,1]; 1 = fully open
    horizon_deg: np.ndarray = field(default_factory=lambda: np.zeros(N_AZ_BINS))
    albedo: float = 0.2            # ground albedo for the reflected term

    @staticmethod
    def horizontal_open() -> "SiteGeometry":
        return SiteGeometry()

    @classmethod
    def from_dict(cls, d: dict) -> "SiteGeometry":
        def _finite(v, default):  # None/NaN/inf/bad -> default (a failed extraction is safe)
            try:
                x = float(v)
            except (TypeError, ValueError):
                return default
            return x if np.isfinite(x) else default
        hor = np.asarray(d.get("horizon_deg", np.zeros(N_AZ_BINS)), float)
        if hor.size != N_AZ_BINS:
            hor = np.zeros(N_AZ_BINS)
        hor = np.nan_to_num(hor, nan=0.0, posinf=0.0, neginf=0.0)
        # NaN tilt/azimuth (e.g. a failed normal capture, normal_raw=[0,0,0]) -> horizontal-open
        return cls(_finite(d.get("tilt_deg"), 0.0), _finite(d.get("azimuth_deg"), 180.0),
                   _finite(d.get("svf"), 1.0), hor, _finite(d.get("albedo"), 0.2))


@dataclass
class PhysicalModel:
    tier: str
    params: np.ndarray
    param_names: list

    def efficacies(self) -> dict:
        """Human-readable fitted efficacies (lm/W) incl. derived air-mass coef c."""
        p = {n: float(v) for n, v in zip(self.param_names, self.params)}
        if "a_beam0" in p and "a_beam0*c" in p and p["a_beam0"]:
            p["c_airmass"] = p.pop("a_beam0*c") / p["a_beam0"]
        return p


# ----------------------------------------------------------------------------- geometry
def _cos_zenith(elev_deg):
    return np.clip(np.sin(np.radians(np.asarray(elev_deg, float))), 0.02, 1.0)


def _cos_aoi(elev_deg, sun_az_deg, tilt_deg, surf_az_deg):
    z = np.radians(90.0 - np.asarray(elev_deg, float))
    gs = np.radians(np.asarray(sun_az_deg, float))
    b = np.radians(float(tilt_deg))
    g = np.radians(float(surf_az_deg))
    return np.cos(z) * np.cos(b) + np.sin(z) * np.sin(b) * np.cos(gs - g)


def _beam_visible(elev_deg, sun_az_deg, horizon_deg, cos_aoi):
    elev = np.asarray(elev_deg, float)
    az = np.mod(np.asarray(sun_az_deg, float), 360.0)
    hor = np.asarray(horizon_deg, float)
    if hor.size == N_AZ_BINS:
        idx = np.minimum((az / (360.0 / N_AZ_BINS)).astype(int), N_AZ_BINS - 1)
        h = hor[idx]
    else:
        h = 0.0
    return ((cos_aoi > 0) & (elev > h)).astype(float)


# ----------------------------------------------------------------------------- diffuse fraction
def erbs_kd(ghi, elevation_deg, day_of_year):
    """Diffuse fraction kd = DHI/GHI from the Erbs et al. (1982) correlation.

    Needs only GHI + solar geometry, so it supplies kd for sites without a
    measured diffuse channel (the synthetic A-J rooftops). For Thissio prefer
    the MEASURED kd from the station's shaded pyranometer. Drives the model's
    beam/diffuse split; in clear sky kt is high so kd is small (~0.13-0.25).
    """
    ghi = np.asarray(ghi, float)
    elev = np.asarray(elevation_deg, float)
    doy = np.asarray(day_of_year, float)
    cz = np.clip(np.sin(np.radians(elev)), 1e-3, 1.0)
    e0 = 1.0 + 0.033 * np.cos(2.0 * np.pi * doy / 365.0)          # earth-sun eccentricity
    ghi_extra = 1367.0 * e0 * cz                                  # extraterrestrial horizontal
    with np.errstate(divide="ignore", invalid="ignore"):
        kt = np.clip(ghi / np.where(ghi_extra > 1.0, ghi_extra, np.nan), 0.0, 1.0)
    kd = np.where(kt <= 0.22, 1.0 - 0.09 * kt,
         np.where(kt <= 0.80,
                  0.9511 - 0.1604 * kt + 4.388 * kt ** 2 - 16.638 * kt ** 3 + 12.336 * kt ** 4,
                  0.165))
    return np.clip(np.nan_to_num(kd, nan=0.2), 0.05, 1.0)


# ----------------------------------------------------------------------------- kernels
def _kernels_for_site(g, geom: SiteGeometry, tier: str):
    """Dimensionless per-row kernels k_j (n_rows x n_params) for one site group."""
    am = g["air_mass"].to_numpy(float)
    amf = am - 1.0
    if tier == "am":  # diffuse-unaware: a single efficacy that varies with air mass
        return np.column_stack([np.ones_like(am), amf]), ["a0", "a0*c_am"]

    elev = g["solar_elevation_deg"].to_numpy(float)
    saz = g["solar_azimuth_deg"].to_numpy(float)
    kd = g["kd"].to_numpy(float)
    cz = _cos_zenith(elev)
    eff_tilt = geom.tilt_deg if geom.tilt_deg >= AUTO_FLAT_TILT_DEG else 0.0
    caoi = _cos_aoi(elev, saz, eff_tilt, geom.azimuth_deg)
    vis = _beam_visible(elev, saz, geom.horizon_deg, caoi)
    kbeam = (1.0 - kd) * np.clip(caoi, 0.0, None) * vis / cz
    kdiff = kd * geom.svf
    kgrnd = geom.albedo * (1.0 - geom.svf) * np.ones_like(kd)

    if tier == "split":
        return np.column_stack([kbeam, kdiff]), ["a_beam", "a_diff"]
    if tier == "split_am":
        return np.column_stack([kbeam, kbeam * amf, kdiff]), ["a_beam0", "a_beam0*c", "a_diff"]
    if tier == "full":
        return np.column_stack([kbeam, kbeam * amf, kdiff, kgrnd]), \
            ["a_beam0", "a_beam0*c", "a_diff", "a_grnd"]
    raise ValueError(f"unknown tier: {tier}")


def _sites(df):
    if "location_id" in df.columns:
        return df["location_id"].to_numpy()
    return np.full(len(df), _SINGLE)


def _design(df, geom_by_site: dict, tier: str):
    """Per-row dimensionless kernels for the whole frame, applying each row's
    site geometry. Returns (K [n x p], param_names)."""
    sites = _sites(df)
    K = None
    names = None
    for s in np.unique(sites):
        m = sites == s
        geom = geom_by_site.get(s, SiteGeometry.horizontal_open())
        Kg, names = _kernels_for_site(df[m], geom, tier)
        if K is None:
            K = np.full((len(df), Kg.shape[1]), np.nan)
        K[m] = Kg
    return K, names


# ----------------------------------------------------------------------------- fit / predict
def fit_physical(df, geom_by_site: dict | None = None, tier: str = "split_am") -> PhysicalModel:
    """Fit luminous efficacies by linear least squares on lux = GHI * (K . a).

    df needs: lux, ghi, air_mass (+ solar_elevation_deg, solar_azimuth_deg, kd
    for the split tiers). Optional location_id for multi-site.
    """
    geom_by_site = geom_by_site or {}
    K, names = _design(df, geom_by_site, tier)
    ghi = df["ghi"].to_numpy(float)
    lux = df["lux"].to_numpy(float)
    X = K * ghi[:, None]                     # forward design: column_j = GHI * k_j
    mask = np.isfinite(X).all(axis=1) & np.isfinite(lux)
    if mask.sum() < len(names) + 1:
        raise ValueError(f"too few valid rows ({mask.sum()}) for tier {tier}")
    params, *_ = np.linalg.lstsq(X[mask], lux[mask], rcond=None)
    return PhysicalModel(tier, params, names)


def predict_physical(model: PhysicalModel, df, geom_by_site: dict | None = None):
    geom_by_site = geom_by_site or {}
    K, _ = _design(df, geom_by_site, model.tier)
    D = K @ model.params
    D = np.where(np.abs(D) < 1e-9, np.nan, D)
    ghi = df["lux"].to_numpy(float) / D
    return np.clip(ghi, 0.0, None)


# ----------------------------------------------------------------------------- metrics / CV
def metrics(meas, pred) -> dict:
    meas = np.asarray(meas, float); pred = np.asarray(pred, float)
    k = np.isfinite(meas) & np.isfinite(pred)
    meas, pred = meas[k], pred[k]
    if len(meas) < 3:
        return {}
    e = pred - meas
    rmse = float(np.sqrt(np.mean(e ** 2)))
    ss = float(np.sum(e ** 2)); tot = float(np.sum((meas - meas.mean()) ** 2))
    return dict(n=int(len(meas)), rmse=rmse, mbe=float(e.mean()),
                r2=1 - ss / tot if tot > 0 else float("nan"),
                nrmse=rmse / meas.mean() * 100 if meas.mean() else float("nan"))


def leave_location_out(df, geom_by_site: dict | None = None, tier: str = "split_am"):
    """Leave-LOCATION-out CV. Returns (aggregate_metrics, per_site_metrics, oof_pred)."""
    geom_by_site = geom_by_site or {}
    sites = _sites(df)
    uniq = np.unique(sites)
    oof = np.full(len(df), np.nan)
    for s in uniq:
        te = sites == s
        tr = ~te
        if tr.sum() < len(_design(df[tr] if tr.any() else df, geom_by_site, tier)[1]) + 1:
            continue
        if te.sum() < 1:
            continue
        m = fit_physical(df[tr], geom_by_site, tier)
        oof[te] = predict_physical(m, df[te], geom_by_site)
    ghi = df["ghi"].to_numpy(float)
    agg = metrics(ghi, oof)
    per = {str(s): metrics(ghi[sites == s], oof[sites == s]) for s in uniq}
    return agg, per, oof


def _loo_linear(df):
    """Leave-location-out for the BASELINE GHI = a*lux + b (the current model)."""
    from .calibrate import fit_location
    sites = _sites(df)
    oof = np.full(len(df), np.nan)
    lux = df["lux"].to_numpy(float); ghi = df["ghi"].to_numpy(float)
    for s in np.unique(sites):
        te = sites == s; tr = ~te
        if tr.sum() < 3 or te.sum() < 1:
            continue
        fit = fit_location(lux[tr], ghi[tr])
        oof[te] = fit.predict_ghi(lux[te])
    return metrics(ghi, oof)


def ablation(df, geom_by_site: dict | None = None):
    """Incremental-feature ablation under leave-location-out CV. Returns list of
    (label, metrics) from the constant-efficacy baseline up to the full model."""
    rows = [("M0_linear(a*lux+b)", _loo_linear(df))]
    for tier, label in [("am", "M1_+air_mass_efficacy"),
                        ("split", "M2_+beam/diffuse_split"),
                        ("split_am", "M3_+air_mass_on_beam"),
                        ("full", "M4_+ground_reflection")]:
        try:
            agg, _, _ = leave_location_out(df, geom_by_site, tier)
        except ValueError:
            agg = {}
        rows.append((label, agg))
    return rows


# ----------------------------------------------------------------------------- deployable model
def _parse_where(where):
    if isinstance(where, dict):
        return float(where["lat"]), float(where["lon"]), float(where.get("alt", 0.0))
    w = list(where)
    return float(w[0]), float(w[1]), (float(w[2]) if len(w) > 2 else 0.0)


def _clearsky_kd(times, lat, lon, alt, elev):
    """Clear-sky diffuse fraction kd from location + time ONLY (no GHI needed, so
    it is non-circular at prediction time). pvlib Ineichen clear sky -> kd=DHI/GHI;
    falls back to Haurwitz GHI + Erbs if the Linke-turbidity lookup is unavailable.
    """
    import numpy as np
    import pandas as pd
    import pvlib
    try:
        cs = pvlib.location.Location(lat, lon, altitude=alt).get_clearsky(times)
        ghi = cs["ghi"].to_numpy(); dhi = cs["dhi"].to_numpy()
        kd = np.where(ghi > 1.0, dhi / ghi, np.nan)
        if not np.isfinite(kd).any():
            raise ValueError("empty clearsky")
    except Exception:  # noqa: BLE001
        z = np.clip(90.0 - np.asarray(elev, float), 0.0, 90.0)
        ghi = pvlib.clearsky.haurwitz(pd.Series(z, index=times)).to_numpy()
        kd = erbs_kd(ghi, elev, np.asarray(times.dayofyear, float))
    return np.clip(np.nan_to_num(kd, nan=0.2), 0.05, 1.0)


@dataclass
class PhysicalGhiModel:
    """Deployable lux -> GHI predictor (structured physical model).

    ONE instance generalizes to ANY rooftop (leave-location-out R^2 ~ 0.95): give
    it the rendered photopic illuminance plus the render's UTC timestamp and
    location (and, optionally, the pixel's surface geometry) and it computes solar
    position, air mass, and the clear-sky diffuse fraction internally. Unlike the
    per-location linear export, no per-roof coefficients are needed.

    Coefficients are luminous efficacies (lm/W) that bake in this twin's absolute
    sky-luminance scale (~3.8x dim) -> the model is valid only for the same
    Isaac/MDL sky configuration it was fitted on; recalibrate if that changes.
    """
    tier: str
    params: list
    param_names: list
    twin_luminance_scale: float = 3.8
    meta: dict = field(default_factory=dict)

    def _pm(self):
        return PhysicalModel(self.tier, np.asarray(self.params, float), list(self.param_names))

    def predict(self, lux, when, where, geometry=None):
        """lux: float or array (photopic lux at the pixel). when: UTC timestamp(s).
        where: (lat, lon[, alt]) or {'lat','lon','alt'}. geometry: SiteGeometry or
        None (horizontal-open). Returns GHI in W/m^2 (float if lux is scalar)."""
        import numpy as np
        import pandas as pd
        import pvlib
        lat, lon, alt = _parse_where(where)
        scalar = np.isscalar(lux)
        lux = np.atleast_1d(np.asarray(lux, float))
        times = pd.DatetimeIndex(pd.to_datetime(np.atleast_1d(when), utc=True))
        if len(times) == 1 and len(lux) > 1:
            times = times.repeat(len(lux))
        sp = pvlib.solarposition.spa_python(times, lat, lon, altitude=alt)
        elev = sp["apparent_elevation"].to_numpy()
        az = sp["azimuth"].to_numpy()
        am = np.nan_to_num(pvlib.atmosphere.get_relative_airmass(
            90.0 - elev, model="kastenyoung1989"), nan=40.0)
        kd = _clearsky_kd(times, lat, lon, alt, elev)
        df = pd.DataFrame(dict(location_id="_pred_", lux=lux,
                               solar_elevation_deg=elev, solar_azimuth_deg=az,
                               air_mass=am, kd=kd))
        geom = {"_pred_": geometry} if geometry is not None else {}
        out = predict_physical(self._pm(), df, geom)
        return float(out[0]) if scalar else out

    def to_export(self):
        return {"schema_version": "phys-1.0.0",
                "model_family": "global_physical_structured_lux_to_ghi",
                "tier": self.tier, "param_names": list(self.param_names),
                "params": [float(x) for x in self.params],
                "twin_luminance_scale": float(self.twin_luminance_scale),
                "units": {"input": "lux", "output": "W/m^2",
                          "also_needs": ["timestamp_utc", "latitude", "longitude"]},
                **self.meta}

    @classmethod
    def from_export(cls, path):
        import json
        d = json.load(open(path, encoding="utf-8")) if isinstance(path, str) else dict(path)
        known = {"schema_version", "model_family", "tier", "param_names", "params",
                 "twin_luminance_scale", "units"}
        meta = {k: v for k, v in d.items() if k not in known}
        return cls(d["tier"], d["params"], d["param_names"],
                   d.get("twin_luminance_scale", 3.8), meta)


def fit_ghi_model(df, geom_by_site=None, tier="split", twin_scale=3.8, meta=None):
    """Fit the structured model and wrap it as a deployable PhysicalGhiModel."""
    m = fit_physical(df, geom_by_site, tier)
    return PhysicalGhiModel(m.tier, [float(x) for x in m.params],
                            list(m.param_names), twin_scale, meta or {})
