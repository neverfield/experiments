"""Cluster bootstrap for means of per-case values, and Holm's step-down adjustment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Estimate:
    mean: float
    low: float
    high: float


def _draws(clusters: Sequence[str], n_boot: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Each case's cluster index, and ``n_boot`` draws of as many clusters as there are.

    The draws depend only on the number of distinct clusters, ``n_boot`` and ``seed``, so
    every set of values over the same cases is resampled identically."""
    _, cluster_index = np.unique(np.asarray(clusters), return_inverse=True)
    n_clusters = int(cluster_index.max()) + 1
    draws = np.random.default_rng(seed).integers(0, n_clusters, size=(n_boot, n_clusters))
    return cluster_index, draws


def cluster_replicates(
    values: Sequence[float], clusters: Sequence[str], n_boot: int = 2000, seed: int = 0
) -> np.ndarray:
    """Bootstrap replicates of the case-level mean, resampling whole clusters with
    replacement. Each replicate keeps all the cases of the clusters it draws, so
    ecosystems with more cases weigh more."""
    values_arr = np.asarray(values, dtype=float)
    if values_arr.size == 0:
        raise ValueError("no values to bootstrap")
    cluster_index, draws = _draws(clusters, n_boot, seed)
    sums = np.bincount(cluster_index, weights=values_arr)
    counts = np.bincount(cluster_index)
    return sums[draws].sum(axis=1) / counts[draws].sum(axis=1)


def group_replicates(
    values: Sequence[float],
    clusters: Sequence[str],
    groups: Sequence[str],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    """Replicates of each group's case-level mean on the resamples ``cluster_replicates``
    draws for the same cases. A replicate that draws no case of a group is NaN."""
    values_arr = np.asarray(values, dtype=float)
    if values_arr.size == 0:
        raise ValueError("no values to bootstrap")
    cluster_index, draws = _draws(clusters, n_boot, seed)
    n_clusters = draws.shape[1]
    groups_arr = np.asarray(groups)
    out = {}
    for group in sorted(set(groups_arr.tolist())):
        member = groups_arr == group
        sums = np.bincount(cluster_index, weights=values_arr * member, minlength=n_clusters)
        counts = np.bincount(cluster_index, weights=member.astype(float), minlength=n_clusters)
        drawn = counts[draws].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[group] = np.where(drawn > 0, sums[draws].sum(axis=1) / drawn, np.nan)
    return out


def percentile_interval(replicates: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    """The percentile interval of the finite replicates (numpy's default linear quantile)."""
    finite = replicates[np.isfinite(replicates)]
    if finite.size == 0:
        return float("nan"), float("nan")
    low, high = np.quantile(finite, [alpha / 2, 1 - alpha / 2])
    return float(low), float(high)


def cluster_bootstrap(
    values: Sequence[float],
    clusters: Sequence[str],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Estimate:
    """Mean with a percentile CI from resampling whole clusters with replacement."""
    replicates = cluster_replicates(values, clusters, n_boot, seed)
    low, high = np.quantile(replicates, [alpha / 2, 1 - alpha / 2])
    return Estimate(float(np.mean(np.asarray(values, dtype=float))), float(low), float(high))


def holm(pvalues: Mapping[str, float], alpha: float = 0.05) -> dict[str, tuple[float, bool]]:
    """Holm's step-down adjusted p-values, and whether each hypothesis is rejected at
    ``alpha``. Rejection stops at the first adjusted p above ``alpha``."""
    order = sorted(pvalues, key=lambda name: pvalues[name])
    out, running, rejecting = {}, 0.0, True
    m = len(order)
    for i, name in enumerate(order):
        adjusted = min(1.0, max(running, (m - i) * pvalues[name]))
        running = adjusted
        rejecting = rejecting and adjusted <= alpha
        out[name] = (adjusted, rejecting)
    return out
