r"""Assemble the Location-J inter-building occlusion figure (F9b).

Composes three Isaac Sim RTX PtIlluminance screenshots of Location J's monitored
roof pixel (red marker, pixel 618,346) at the three low-sun timestamps with the
largest leave-location-out scatter outliers. On these dates the pixel is shadowed
by neighbouring buildings, so the rendered illuminance drops and the calibrated GHI
falls below the clear-sky reference. The figure illustrates, qualitatively, that
the twin captures inter-object occlusion a horizontal-plane model (CAMS McClear)
does not represent.

The panels are the Isaac native false-colour renders (jet colour map, 0-35000 lux),
so the shared colour bar uses the same jet map and 0-35 klux range. The red pixel
marker is already present in the screenshots. Input filenames follow
Location_J_YYYYMMDD_HH_MM.png; a legend grab (e.g. legend_lux.png) is skipped.

Usage:
  uv run python scripts/make_j_occlusion_figure.py \
    --img-dir data/results/figures \
    --out     data/results/figures/F9b_J_occlusion.png \
    --vmax-klux 35
  # optional per-panel labels (timestamp order):
  #   --annot "GHI meas 410, pred 250" "..." "..."
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os


def _parse_ts(path):
    """Location_J_YYYYMMDD_HH_MM(.png) -> datetime."""
    base = os.path.splitext(os.path.basename(path))[0]
    ymd, hh, mm = base.split("_")[-3:]
    return dt.datetime.strptime(f"{ymd}{hh}{mm}", "%Y%m%d%H%M")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--img-dir", help="dir holding Location_J_YYYYMMDD_HH_MM.png")
    p.add_argument("--pattern", default="Location_J_*.png")
    p.add_argument("--images", nargs="*", help="explicit image paths (overrides --img-dir/--pattern)")
    p.add_argument("--out", required=True)
    p.add_argument("--cmap", default="jet", help="match the Isaac illuminance legend (jet)")
    p.add_argument("--vmax-klux", type=float, default=35.0, help="legend max (Isaac default 35000 lux)")
    p.add_argument("--annot", nargs="*", default=None,
                   help="optional per-panel annotation, one per image (timestamp order)")
    args = p.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    matplotlib.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm",
                                "savefig.dpi": 300, "savefig.bbox": "tight"})

    if args.images:
        imgs = list(args.images)
    else:
        if not args.img_dir:
            raise SystemExit("provide --images or --img-dir")
        imgs = glob.glob(os.path.join(args.img_dir, args.pattern))
    imgs = [f for f in imgs if "legend" not in os.path.basename(f).lower()]
    if not imgs:
        raise SystemExit(f"no images matched {args.pattern} in {args.img_dir}")
    imgs = sorted(imgs, key=_parse_ts)

    n = len(imgs)
    fig, axes = plt.subplots(1, n, figsize=(4.4 * n, 3.5))
    if n == 1:
        axes = [axes]
    for i, (ax, f) in enumerate(zip(axes, imgs)):
        ax.imshow(plt.imread(f))
        ax.set_xticks([]); ax.set_yticks([])
        title = _parse_ts(f).strftime("%d %b %Y, %H:%M")
        if args.annot and i < len(args.annot):
            title += "\n" + args.annot[i]
        ax.set_title(title, fontsize=11)

    fig.subplots_adjust(left=0.01, right=0.88, wspace=0.04, bottom=0.05, top=0.85)
    cax = fig.add_axes([0.905, 0.12, 0.014, 0.70])
    sm = ScalarMappable(norm=Normalize(0, args.vmax_klux), cmap=args.cmap)
    cb = fig.colorbar(sm, cax=cax)
    cb.set_label("illuminance (klux)", fontsize=11)

    fig.suptitle("Location J: monitored roof pixel (red marker) shadowed by neighbouring "
                 "buildings on the three low-sun outlier days", y=0.99, fontsize=12)

    base = os.path.splitext(args.out)[0]
    for ext in (".png", ".pdf"):
        fig.savefig(base + ext)
        print(f"[wrote] {base + ext}")
    plt.close(fig)


if __name__ == "__main__":
    main()
