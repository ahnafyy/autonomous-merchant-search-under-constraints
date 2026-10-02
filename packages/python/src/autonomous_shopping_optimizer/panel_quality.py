"""Quality diagnostics for longitudinal merchant-panel observations."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

ObservationKey = tuple[str, str]
Snapshot = tuple[str, dict[ObservationKey, dict[str, Any]]]


def transition_quality(
    prior: Snapshot,
    current: Snapshot,
    *,
    domain_fraction_threshold: float = 0.15,
    offer_fraction_threshold: float = 0.15,
) -> dict[str, Any]:
    """Measure comparable offer losses and flag broad common-mode changes."""
    prior_date, prior_rows = prior
    current_date, current_rows = current
    comparable = {
        key
        for key, row in prior_rows.items()
        if row.get("present") is True
        and key in current_rows
        and current_rows[key].get("merchant_fully_paginated") is True
    }
    lost = {key for key in comparable if current_rows[key].get("present") is False}
    comparable_domains = {domain for domain, _sku in comparable}
    affected_domains = {domain for domain, _sku in lost}
    offer_fraction = len(lost) / len(comparable) if comparable else 0.0
    domain_fraction = (
        len(affected_domains) / len(comparable_domains) if comparable_domains else 0.0
    )
    return {
        "prior_date": prior_date,
        "current_date": current_date,
        "comparable_present_offers": len(comparable),
        "lost_offers": len(lost),
        "offer_loss_fraction": round(offer_fraction, 6),
        "comparable_domains": len(comparable_domains),
        "affected_domains": len(affected_domains),
        "affected_domain_fraction": round(domain_fraction, 6),
        "common_mode_anomaly": (
            offer_fraction >= offer_fraction_threshold
            and domain_fraction >= domain_fraction_threshold
        ),
        "thresholds": {
            "offer_loss_fraction": offer_fraction_threshold,
            "affected_domain_fraction": domain_fraction_threshold,
        },
    }


def lifecycle_summary(snapshots: list[Snapshot]) -> dict[str, Any]:
    """Separate first loss, reappearance, and persistent absence at the horizon."""
    histories: dict[ObservationKey, list[tuple[str, bool]]] = defaultdict(list)
    for observation_date, rows in snapshots:
        for key, row in rows.items():
            if row.get("merchant_fully_paginated") is True:
                histories[key].append((observation_date, bool(row.get("present"))))

    first_disappearances = 0
    reappearances = 0
    transient_offers = 0
    persistent_offers = 0
    unresolved_offers = 0
    examples: list[dict[str, Any]] = []
    for (domain, sku), history in sorted(histories.items()):
        first_loss_date: str | None = None
        reappearance_dates: list[str] = []
        absent_observations_since_presence = 0
        previous_present: bool | None = None
        for observation_date, present in history:
            if previous_present is True and not present:
                if first_loss_date is None:
                    first_loss_date = observation_date
                    first_disappearances += 1
                absent_observations_since_presence = 1
            elif previous_present is False and present:
                reappearance_dates.append(observation_date)
                reappearances += 1
                absent_observations_since_presence = 0
            elif previous_present is False and not present:
                absent_observations_since_presence += 1
            previous_present = present

        if first_loss_date is None:
            continue
        if reappearance_dates:
            transient_offers += 1
        if history[-1][1] is False:
            if absent_observations_since_presence >= 2:
                persistent_offers += 1
            else:
                unresolved_offers += 1
        if len(examples) < 25:
            examples.append(
                {
                    "domain": domain,
                    "sku": sku,
                    "first_disappearance_date": first_loss_date,
                    "reappearance_dates": reappearance_dates,
                    "last_fully_observed_state": (
                        "present" if history[-1][1] else "absent"
                    ),
                    "consecutive_absent_observations_at_horizon": (
                        absent_observations_since_presence if not history[-1][1] else 0
                    ),
                }
            )

    return {
        "offers_with_first_disappearance": first_disappearances,
        "reappearance_events": reappearances,
        "offers_that_reappeared": transient_offers,
        "persistent_absence_at_horizon": persistent_offers,
        "unresolved_single_absence_at_horizon": unresolved_offers,
        "persistent_definition": (
            "absent in at least two consecutive fully observed records after the "
            "most recent presence, with no later reappearance"
        ),
        "examples": examples,
    }