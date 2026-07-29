#!/usr/bin/env python3
"""
osort_ref.py — faithful Python port of OSort's core ONLINE sorter.

Ported block-for-block from the OFFICIAL OSort v4.1 (Ueli Rutishauser, urut.ch):
  code/sortingNew/sortSpikesOnline.m   (thresholdMethod = 1, the default/raw path)
  code/sortingNew/calculateDistance.m  (weighted squared-Euclidean distance)
  code/sortingNew/defineSortingConstants.m  (NOISE cluster id = 99999999)

This exists because our from-a-flowchart C reimplementation is untrustworthy. This
is the REFERENCE we validate against — so it copies the real algorithm, warts and
all, and flags every place it deviates.

Algorithm (method 1):
  thres = std_estimate**2 * n_used_samples * 1.2      # 1.2 = burst correction
  dist(spike, center) = sum( weights * (center - spike)**2 )   # squared Euclidean
  per streaming spike:
    - if nearest center is farther than thres -> new cluster
    - else assign to nearest; update that center = mean of its spikes, but STOP
      updating once the cluster has >= 50 spikes ("converged")
    - after assigning, recursively MERGE any center now within thres of the
      updated one (weighted mean); clusters with < 2 spikes are not merged
    - every 1000 spikes, PRUNE clusters with < 2 spikes -> noise

Documented deviations from the MATLAB (be honest, then validate):
  1. Clean parallel lists (centers/counts/ids) instead of the MATLAB [ID,index]
     table with manual index-shifting. Semantically identical; avoids reindex bugs.
  2. MATLAB's init overwrites its seed cluster on the first new cluster (a quirk
     touching <=1 spike); here the seed is cluster id 1 and new clusters append.
  3. The `c1<2 or c2<2` merge-skip: MATLAB marks that pair unmergeable and tries the
     next-closest; we stop the merge loop when the closest pair is unmergeable.
     (Rare mid-merge since <2-count clusters get pruned; flagged for validation.)
  4. thresholdMethod 2 (whitened Chi2 path) is NOT ported yet.
"""
import numpy as np

NOISE = 99999999


def sort_spikes_online(spikes, std_estimate, run_avg=100):
    """spikes: (N, D) waveforms in streaming order. std_estimate: raw noise std.
    Returns (assigned, ids, counts, centers)."""
    spikes = np.asarray(spikes, dtype=float)
    n, d = spikes.shape

    weights = np.ones(d)
    if d == 256:                       # MATLAB zeroes the snippet edges only for 256-pt
        weights[:20] = 0.0
        weights[200:] = 0.0

    thres = (std_estimate ** 2) * int(weights.sum()) * 1.2   # incl. 1.2 burst factor
    thres_merge = thres

    centers = [spikes[0].copy()]       # cluster mean waveforms
    counts = [1]                       # spikes per cluster
    ids = [1]                          # unique id per cluster
    next_id = 1
    assigned = np.zeros(n, dtype=np.int64)   # id per spike (0 = seed spike, unset)

    peak_k = 1          # cost stat: max live clusters (memory driver)
    dist_evals = 0      # cost stat: per-center distance computations (compute driver)

    def dist_to_all(sp):
        C = np.asarray(centers)
        return ((C - sp) ** 2) @ weights

    for i in range(1, n):
        # --- periodic pruning of tiny (noise) clusters
        if (i + 1) % 1000 == 0:
            k = 0
            while k < len(centers):
                if counts[k] < 2:
                    assigned[assigned == ids[k]] = NOISE
                    del centers[k], counts[k], ids[k]
                else:
                    k += 1

        sp = spikes[i]
        dist_evals += len(centers)          # assign step: distance to every live center
        D = dist_to_all(sp)
        peak_k = max(peak_k, len(centers))

        if D.min() > thres:
            next_id += 1
            centers.append(sp.copy()); counts.append(1); ids.append(next_id)
            assigned[i] = next_id
            peak_k = max(peak_k, len(centers))
            continue

        # --- assign to nearest cluster
        ind = int(np.argmin(D))
        cid = ids[ind]
        assigned[i] = cid
        counts[ind] += 1

        # --- running-mean template update, frozen once the cluster reaches 50 spikes
        if counts[ind] < 50:
            members = np.where(assigned == cid)[0]
            if len(members) > run_avg:
                members = members[-run_avg - 1:]
            centers[ind] = spikes[members].mean(axis=0)

        # --- recursive merging of centers now within thres_merge
        while True:
            C = np.asarray(centers)
            DD = ((C - centers[ind]) ** 2) @ weights
            dist_evals += len(centers)      # merge step also scans every live center
            pos = DD > 0
            if not pos.any():
                break
            j = int(np.argmin(np.where(pos, DD, np.inf)))
            if DD[j] >= thres_merge:
                break
            c1, c2 = counts[ind], counts[j]
            if c1 < 2 or c2 < 2:        # deviation #3: stop rather than skip-and-continue
                break
            centers[ind] = (centers[ind] * c1 + centers[j] * c2) / (c1 + c2)
            counts[ind] = c1 + c2
            assigned[assigned == ids[j]] = cid
            del centers[j], counts[j], ids[j]
            if j < ind:
                ind -= 1

    return assigned, ids, counts, centers, {"peak_clusters": peak_k,
                                            "dist_per_spike": dist_evals / n}


if __name__ == "__main__":
    # COST profile of REAL OSort on the nRF54 (memory + compute). NOT a quality claim.
    import struct, sys
    fn = sys.argv[1] if len(sys.argv) > 1 else "snippets.bin"
    std = float(sys.argv[2]) if len(sys.argv) > 2 else 14.8   # ch56 MAD sigma from prep
    with open(fn, "rb") as f:
        n, k = struct.unpack("<ii", f.read(8))
        X = np.frombuffer(f.read(), dtype=np.float32).reshape(n, k).astype(float)
    assigned, ids, counts, centers, st = sort_spikes_online(X, std)

    peak, dps = st["peak_clusters"], st["dist_per_spike"]
    # nRF54 mapping (same model as opt_osort.c): each per-center distance ~3*k float ops;
    # M33 ~1 cycle/op @ 128 MHz. Memory = live cluster centers (k float32 each).
    ops_spike = dps * 3 * k
    us_spike = ops_spike / 128e6 * 1e6
    mem_ch = peak * k * 4
    print(f"REAL OSort on {n} spikes (std={std}) -- COST profile, not quality:\n")
    print(f"  peak live clusters : {peak}")
    print(f"  distances/spike    : {dps:.0f}  (vs opt-OSort's fixed 4)")
    print(f"  est ops/spike      : {ops_spike:.0f}  ->  {us_spike:.1f} us/spike @ 128 MHz")
    print(f"  cluster memory     : {mem_ch/1024:.0f} KB/ch  ->  {mem_ch*64/1024/1024:.1f} MB for 64 ch")
    print(f"  nRF54 RAM is 512 KB total  ->  {'FITS' if mem_ch*64 < 512*1024 else 'DOES NOT FIT'}")
    print(f"\n  (opt-OSort by contrast: 4 fixed clusters, ~8 us/spike, 88 KB for 64 ch)")
