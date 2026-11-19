"""
AgriWaste AI - Farmer Preparation Guides (prototype)

Guides intentionally focus on general, low-risk preparation steps.
Buyer-specific specifications must override these general instructions.
Animal-feed and chemical-treatment decisions should be verified with
appropriate agricultural/livestock professionals and the buyer.
"""

from typing import Dict

PROCESSING_GUIDES = {
    "raw": {
        "title": "Raw residue",
        "summary": "Collected residue with only basic sorting and handling.",
        "steps": [
            "Collect the residue soon after harvest where practical.",
            "Separate obvious soil, stones, plastic, metal and other contamination.",
            "Keep different residue types or grades separate when a buyer asks for separation.",
            "Weigh the lot and record the quantity.",
            "Take clear photos of the lot from several sides.",
            "Store it off the ground and protect it from rain until pickup or further preparation.",
            "Tell the buyer that the material is raw and confirm whether they will collect it.",
        ],
    },
    "dry": {
        "title": "Dry residue",
        "summary": "Residue prepared for a buyer who specifies a moisture limit.",
        "steps": [
            "Sort and clean the residue before drying.",
            "Spread it in a clean, well-ventilated drying area or use an appropriate dryer.",
            "Turn or aerate the material so drying is reasonably uniform.",
            "Protect the material from rain and ground contact during drying.",
            "Measure moisture with a suitable moisture meter when the buyer has specified a limit.",
            "Stop drying when the buyer's required moisture specification is reached; do not assume one universal target.",
            "Weigh again after drying because water loss changes the saleable quantity.",
            "Bundle, bale or bag only if the buyer specifies that packaging.",
            "Store the dry material in a clean, dry, ventilated place until dispatch.",
        ],
    },
    "processed": {
        "title": "Processed residue",
        "summary": "Residue prepared to a buyer-defined form such as chopped, shredded, baled or otherwise processed.",
        "steps": [
            "Ask the buyer for the exact processing specification before spending money on processing.",
            "Confirm the required moisture, particle size, bale/bundle size, packaging and contamination limit.",
            "Sort and clean the residue first.",
            "Dry it if the buyer requires a moisture limit before processing.",
            "Use suitable equipment for the requested operation such as chopping, shredding, baling or size reduction.",
            "Check a small sample before processing the full lot to confirm the size and appearance meet the requirement.",
            "Measure and record final quantity and, where relevant, moisture.",
            "Pack and label the material with residue type, quantity, preparation date and any agreed quality information.",
            "Keep the processed lot protected from rain, soil and cross-contamination until pickup.",
        ],
    },
}


def get_processing_guide(form: str) -> Dict:
    return PROCESSING_GUIDES.get(form, PROCESSING_GUIDES["raw"])


def preparation_checklist(
    form: str,
    moisture_pct=None,
    buyer_max_moisture_pct=None,
    cleaned=False,
):
    """Return a farmer-friendly checklist for the current lot."""
    checks = [
        ("Residue sorted and free of visible contamination", cleaned),
        ("Quantity weighed", False),
        ("Photos taken", False),
    ]
    if form in {"dry", "processed"}:
        moisture_ok = (
            moisture_pct is not None
            and buyer_max_moisture_pct is not None
            and moisture_pct <= buyer_max_moisture_pct
        )
        checks.append(("Moisture measured against buyer requirement", moisture_ok))
    return checks
