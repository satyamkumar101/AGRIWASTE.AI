"""
AgriWaste AI - Buyer Marketplace & Requirement Matching (prototype)

This module deliberately uses DEMO buyer requirements. It does not represent
real buyers, live listings, live prices, or guaranteed transactions.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional


@dataclass
class BuyerListing:
    buyer_id: str
    buyer_name: str
    buyer_type: str
    crop: str
    residue: str
    accepted_forms: List[str]          # raw / dry / processed
    max_moisture_pct: Optional[float]
    min_quantity_kg: float
    processing_required: str
    packaging: str
    pickup_available: bool
    location: str
    notes: str = ""


DEMO_BUYERS = [
    BuyerListing(
        buyer_id="DEMO-RICE-BIOMASS-01",
        buyer_name="Demo Biomass Processor",
        buyer_type="Biomass products",
        crop="rice",
        residue="Rice Straw",
        accepted_forms=["dry", "processed"],
        max_moisture_pct=18.0,
        min_quantity_kg=500.0,
        processing_required="Dry; baled or chopped according to buyer specification",
        packaging="Bales or tied bundles",
        pickup_available=True,
        location="Demo listing — local area required",
        notes="Final moisture, bale size and price must be agreed before dispatch.",
    ),
    BuyerListing(
        buyer_id="DEMO-WHEAT-FEED-01",
        buyer_name="Demo Feed Processor",
        buyer_type="Livestock feed processor",
        crop="wheat",
        residue="Wheat Straw",
        accepted_forms=["dry", "processed"],
        max_moisture_pct=15.0,
        min_quantity_kg=300.0,
        processing_required="Clean and dry; chopping may be requested",
        packaging="Bales or clean sacks",
        pickup_available=False,
        location="Demo listing — delivery terms required",
        notes="Feed use requires buyer quality checks and appropriate feed-safety controls.",
    ),
    BuyerListing(
        buyer_id="DEMO-MAIZE-BIOMASS-01",
        buyer_name="Demo Biomass Aggregator",
        buyer_type="Biomass products",
        crop="maize",
        residue="Maize Stover",
        accepted_forms=["raw", "dry", "processed"],
        max_moisture_pct=20.0,
        min_quantity_kg=1000.0,
        processing_required="Raw accepted; dry/chopped preferred",
        packaging="Loose, bundles or bales",
        pickup_available=True,
        location="Demo listing — local area required",
        notes="Buyer may inspect the lot before confirming acceptance.",
    ),
    BuyerListing(
        buyer_id="DEMO-COTTON-MATERIAL-01",
        buyer_name="Demo Fiber / Material Processor",
        buyer_type="Material processing",
        crop="cotton",
        residue="Cotton Stalks & Crop Residues",
        accepted_forms=["dry", "processed"],
        max_moisture_pct=18.0,
        min_quantity_kg=500.0,
        processing_required="Dry; size reduction may be requested",
        packaging="Bundles or bales",
        pickup_available=True,
        location="Demo listing — local area required",
        notes="Confirm acceptable stalk size and contamination limits before transport.",
    ),
    BuyerListing(
        buyer_id="DEMO-COCONUT-BIOMASS-01",
        buyer_name="Demo Coconut Biomass Processor",
        buyer_type="Biomass / material processor",
        crop="coconut",
        residue="Coconut Husk & Shell",
        accepted_forms=["raw", "dry", "processed"],
        max_moisture_pct=20.0,
        min_quantity_kg=250.0,
        processing_required="Clean; dry preferred; shell/husk may need separation",
        packaging="Sacks, bundles or loose load",
        pickup_available=True,
        location="Demo listing — local area required",
        notes="Keep husk and shell separated when the buyer requests separate grades.",
    ),
]


def get_buyer_listings(crop: str) -> List[Dict]:
    """Return demo listings for the selected crop."""
    return [
        asdict(buyer)
        for buyer in DEMO_BUYERS
        if buyer.crop == crop
    ]


def _form_score(farmer_form: str, accepted_forms: List[str]) -> float:
    if farmer_form in accepted_forms:
        return 25.0
    # A raw lot can be prepared into dry/processed form, so keep it
    # actionable instead of treating it as an immediate hard failure.
    if farmer_form == "raw" and any(f in accepted_forms for f in ("dry", "processed")):
        return 10.0
    return 0.0


def _moisture_score(moisture: Optional[float], maximum: Optional[float]) -> float:
    if moisture is None or maximum is None:
        return 10.0
    if moisture <= maximum:
        return 15.0
    # Still useful: the result tells the farmer that drying is required.
    excess_ratio = min((moisture - maximum) / max(maximum, 1.0), 1.0)
    return max(0.0, 15.0 * (1.0 - excess_ratio))


def match_buyer(
    listing: Dict,
    farmer_form: str,
    quantity_kg: float,
    moisture_pct: Optional[float],
    cleaned: bool = True,
    processed: bool = False,
) -> Dict:
    """
    Produce a transparent prototype match score.

    The score is a decision-support aid, not a guarantee of buyer acceptance.
    """
    score = 0.0
    reasons = []
    actions = []

    # 30: crop/residue identity is already enforced by get_buyer_listings().
    score += 30.0
    reasons.append("Residue type matches the listing.")

    # 25: material form.
    form_points = _form_score(farmer_form, listing["accepted_forms"])
    score += form_points
    if form_points >= 25:
        reasons.append(f"{farmer_form.title()} form is accepted.")
    else:
        actions.append("Prepare the residue into an accepted form before offering it.")

    # 15: moisture.
    moisture_points = _moisture_score(moisture_pct, listing["max_moisture_pct"])
    score += moisture_points
    if moisture_pct is not None and listing["max_moisture_pct"] is not None:
        if moisture_pct <= listing["max_moisture_pct"]:
            reasons.append("Measured moisture is within the buyer's stated limit.")
        else:
            actions.append(
                f"Dry the residue to at or below the buyer's stated "
                f"{listing['max_moisture_pct']:.1f}% moisture limit."
            )
    else:
        actions.append("Measure moisture before finalizing the sale.")

    # 10: quantity.
    if quantity_kg >= listing["min_quantity_kg"]:
        score += 10.0
        reasons.append("Lot size meets the listed minimum quantity.")
    else:
        ratio = max(0.0, quantity_kg / max(listing["min_quantity_kg"], 1.0))
        score += 10.0 * ratio
        actions.append(
            f"Increase the lot to about {listing['min_quantity_kg']:,.0f} kg "
            "or combine with a nearby farmer/aggregator."
        )

    # 10: cleanliness.
    if cleaned:
        score += 10.0
        reasons.append("Lot is marked as cleaned.")
    else:
        actions.append("Remove soil, stones, plastic and other contamination.")

    # 10: processing readiness.
    if processed or listing["processing_required"].lower().startswith("raw accepted"):
        score += 10.0
        reasons.append("Processing state is compatible with the listing.")
    else:
        actions.append("Confirm the required drying, chopping, baling or other preparation.")

    return {
        "score": round(min(score, 100.0), 1),
        "reasons": reasons,
        "actions": actions,
        "status": "Ready to contact buyer" if score >= 80 else (
            "Prepare before contacting buyer" if score >= 55 else "Needs more preparation"
        ),
    }


def build_farmer_listing(
    crop: str,
    residue: str,
    quantity_kg: float,
    form: str,
    moisture_pct: Optional[float],
    processing: str,
    location: str,
    pickup: bool,
    notes: str = "",
) -> Dict:
    """Create a marketplace listing payload for a future backend/database."""
    return {
        "crop": crop,
        "residue": residue,
        "quantity_kg": float(quantity_kg),
        "form": form,
        "moisture_pct": moisture_pct,
        "processing": processing,
        "location": location.strip(),
        "pickup": bool(pickup),
        "notes": notes.strip(),
        "status": "Draft",
    }
