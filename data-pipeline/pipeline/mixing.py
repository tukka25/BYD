from __future__ import annotations

import random
from typing import Dict, List, Tuple


def select_mix(real_rows: List[Dict], rephrase_rows: List[Dict], aug_rows: List[Dict], cfg: Dict) -> Tuple[List[Dict], Dict]:
    synth_per_seed = float(cfg["generation"]["target_synth_per_seed"])
    rephrase_ratio = float(cfg["generation"]["rephrase_ratio"])

    n_real = len(real_rows)
    target_synth = round(n_real * synth_per_seed)
    target_rephrase = round(target_synth * rephrase_ratio)
    target_aug = target_synth - target_rephrase

    picked_rephrase = rephrase_rows[: min(len(rephrase_rows), target_rephrase)]
    picked_aug = aug_rows[: min(len(aug_rows), target_aug)]

    shortfall = target_synth - (len(picked_rephrase) + len(picked_aug))
    if shortfall > 0:
        rem_rephrase = rephrase_rows[len(picked_rephrase):]
        rem_aug = aug_rows[len(picked_aug):]
        extras = (rem_rephrase + rem_aug)[:shortfall]
        if extras:
            if rem_rephrase:
                picked_rephrase.extend(extras[: min(shortfall, len(rem_rephrase))])
                extras = extras[min(shortfall, len(rem_rephrase)):]
            if extras:
                picked_aug.extend(extras)

    final_rows = list(real_rows) + picked_rephrase + picked_aug
    random.Random(cfg["split"]["random_seed"]).shuffle(final_rows)

    stats = {
        "n_real": len(real_rows),
        "n_rephrase": len(picked_rephrase),
        "n_answer_aug": len(picked_aug),
        "n_total": len(final_rows),
        "target_synth": target_synth,
        "target_rephrase": target_rephrase,
        "target_answer_aug": target_aug,
    }
    return final_rows, stats
