# ============================================================
# AGRIWASTE AI
# Agricultural Waste Identification & Value Platform — v25 Hardened Prototype
# ============================================================

from pathlib import Path
import tempfile
import csv
import io
import re
from datetime import datetime

from PIL import Image, ImageEnhance

import streamlit as st
import plotly.express as px

#from predict import predict_image
from recommendations import (
    get_waste_information,
    get_recommendations,
)
from economic_value import estimate_value
from utilizers import get_utilizers
from marketplace import match_buyer, build_farmer_listing
from marketplace_db import (
    get_buyer_listings,
    create_listing,
    save_interest,
    get_recent_listings,
    get_recent_interests,
    get_farmer_dashboard,
    get_listing,
    get_audit_events,
    get_listing_quality,
    save_listing_quality,
    add_listing_evidence,
    get_listing_evidence,
    save_prediction_feedback,
    get_prediction_feedback,
    get_preparation,
    create_or_update_preparation,
    create_rfq,
    get_open_rfqs,
    get_buyer_rfqs,
    get_rfq,
    create_rfq_response,
    get_rfq_responses_for_farmer,
    get_rfq_responses_for_buyer,
    get_deal_for_response,
    create_or_get_deal,
    get_deal,
    get_deals_for_buyer,
    get_deals_for_farmer,
    get_deal_messages,
    send_deal_message,
    confirm_deal,
    schedule_pickup,
    submit_handover,
    confirm_handover,
    get_transaction_receipt,
    update_listing_status,
    update_interest_status,
    LISTING_TRANSITIONS,
    INTEREST_TRANSITIONS,
)
from processing_guides import get_processing_guide
from auth import authenticate, create_user, initialize_auth_db, get_user_contact


# ============================================================
# SMART BUYER–FARMER MATCHING
# ============================================================

def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _processing_terms_match(required: str, available: str) -> bool:
    terms = {
        token for token in re.findall(r"[a-z0-9]+", _normalize_text(required))
        if len(token) >= 3 and token not in {"and", "the", "for", "with"}
    }
    available_text = _normalize_text(available)
    return not terms or all(term in available_text for term in terms)


def build_farmer_response_draft(listing: dict, rfq: dict, match_result: dict) -> str:
    """Build a factual, editable RFQ response from stored listing/RFQ data only."""
    quantity = float(listing.get("quantity_kg") or 0)
    form = str(listing.get("form") or "").strip().title() or "Not recorded"
    moisture = listing.get("moisture_pct")
    moisture_text = (
        f"{float(moisture):.1f}%" if moisture is not None else "not recorded"
    )
    processing = str(listing.get("processing") or "").strip()
    location = str(listing.get("location") or "").strip()
    buyer_name = str(rfq.get("buyer_name") or "the buyer").strip()
    minimum = float(rfq.get("min_quantity_kg") or 0)
    offered_quantity = min(quantity, minimum) if minimum > 0 else quantity

    lines = [
        f"Hello {buyer_name},",
        "",
        f"I have a {form.lower()} lot of {quantity:,.0f} kg of {format_crop_name(listing.get('crop'))} {listing.get('residue', '')}.",
        f"Current recorded moisture is {moisture_text}.",
    ]

    if processing:
        lines.append(f"Recorded processing: {processing}.")
    if location:
        lines.append(f"Lot location: {location}.")

    lines.append(
        f"I can offer up to {offered_quantity:,.0f} kg from this lot, subject to final quantity verification."
    )

    if match_result.get("category") == "Ready to respond":
        lines.append("The listed lot currently aligns with the main requirements in your request.")
    elif match_result.get("category") == "Preparation needed":
        lines.append("I am reviewing the remaining preparation/confirmation requirements before finalizing the offer.")

    if rfq.get("processing_required"):
        lines.append(f"Your requested processing is: {rfq['processing_required']}.")
    if rfq.get("packaging"):
        lines.append(f"Your requested packaging is: {rfq['packaging']}.")
    if rfq.get("pickup_required"):
        lines.append("Please confirm the pickup arrangement, transport details, and final acceptance requirements.")

    lines.extend([
        "Please confirm if this lot is suitable for your requirement and share any final instructions.",
        "",
        "Thank you."
    ])
    return "\n".join(lines)


def match_listing_to_rfq(listing: dict, rfq: dict) -> dict:
    matched, preparation, blockers = [], [], []

    crop_match = _normalize_text(listing.get("crop")) == _normalize_text(rfq.get("crop"))
    residue_match = _normalize_text(listing.get("residue")) == _normalize_text(rfq.get("residue"))

    if crop_match: matched.append("Crop matches.")
    else: blockers.append("Crop does not match the buyer request.")
    if residue_match: matched.append("Residue type matches.")
    else: blockers.append("Residue type does not match the buyer request.")

    forms = {_normalize_text(x) for x in (rfq.get("accepted_forms") or []) if _normalize_text(x)}
    current_form = _normalize_text(listing.get("form"))
    if forms:
        if current_form in forms:
            matched.append(f"Form matches ({listing.get('form', '').title()}).")
        else:
            preparation.append(
                f"Buyer accepts {', '.join(sorted(x.title() for x in forms))}; "
                f"your lot is currently {listing.get('form', '').title()}."
            )

    qty=float(listing.get("quantity_kg") or 0)
    minimum=float(rfq.get("min_quantity_kg") or 0)
    if qty >= minimum:
        matched.append(f"Quantity meets the minimum ({qty:,.0f} kg available).")
    else:
        blockers.append(f"Lot has {qty:,.0f} kg; buyer requests at least {minimum:,.0f} kg.")

    moisture_limit=rfq.get("max_moisture_pct")
    moisture=listing.get("moisture_pct")
    if moisture_limit is not None:
        if moisture is None:
            preparation.append(
                f"Buyer requires moisture ≤ {float(moisture_limit):.1f}%; measure the actual lot."
            )
        elif float(moisture) <= float(moisture_limit):
            matched.append(
                f"Moisture meets the limit ({float(moisture):.1f}% ≤ {float(moisture_limit):.1f}%)."
            )
        else:
            preparation.append(
                f"Moisture is {float(moisture):.1f}%; buyer requires ≤ {float(moisture_limit):.1f}%. "
                "Dry further and re-measure."
            )

    required_processing=str(rfq.get("processing_required") or "").strip()
    recorded_processing=str(listing.get("processing") or "").strip()
    if required_processing:
        if _processing_terms_match(required_processing, recorded_processing):
            matched.append("Recorded processing is consistent with the buyer requirement.")
        else:
            preparation.append(
                f"Buyer requests: {required_processing}. "
                f"Your lot records: {recorded_processing or 'no processing recorded'}."
            )

    packaging=str(rfq.get("packaging") or "").strip()
    if packaging:
        preparation.append(
            f"Buyer packaging requirement: {packaging}. Confirm and prepare packaging accordingly."
        )

    if bool(rfq.get("pickup_required")):
        if bool(listing.get("pickup_available")):
            matched.append("Pickup is marked as available.")
        else:
            blockers.append("Buyer requires pickup, but this lot is not marked for pickup.")

    if _normalize_text(rfq.get("location")) and _normalize_text(listing.get("location")):
        matched.append(
            f"Locations are recorded (buyer: {rfq['location']}; farmer: {listing['location']}). "
            "Confirm transport distance and cost before agreeing."
        )

    category = "Not currently compatible" if blockers else (
        "Preparation needed" if preparation else "Ready to respond"
    )
    return {
        "category": category,
        "matched": matched,
        "preparation": preparation,
        "blockers": blockers,
    }


# ============================================================
# BUYER REQUIREMENT GAP ANALYSIS
# ============================================================

def build_requirement_gap(
    buyer: dict,
    farmer_form: str,
    quantity_kg: float,
    moisture_pct: float,
    cleaned: bool | None,
    processed: bool,
) -> dict:
    """
    Convert buyer requirements into a simple farmer-facing action plan.

    This is an advisory comparison layer:
    - hard requirements are separated from preparation suggestions;
    - buyer-stated limits are preserved as-is;
    - no universal moisture or processing target is invented;
    - the farmer is told to verify the buyer's specification before delivery.
    """
    gaps = []
    actions = []
    matched = []

    accepted_forms = [str(x).lower() for x in buyer.get("accepted_forms", [])]
    required_form = str(buyer.get("processing_required", "") or "").strip().lower()
    max_moisture = buyer.get("max_moisture_pct")
    minimum_qty = float(buyer.get("min_quantity_kg") or 0)

    # Form requirement
    if accepted_forms and farmer_form.lower() in accepted_forms:
        matched.append(f"Current form ({farmer_form.title()}) is accepted.")
    elif accepted_forms:
        accepted_text = ", ".join(x.title() for x in accepted_forms)
        gaps.append(f"Current form is {farmer_form.title()}, but the buyer accepts: {accepted_text}.")
        actions.append(
            f"Prepare the residue into one of the buyer's accepted forms: {accepted_text}. "
            "Confirm the required processing method with the buyer before starting."
        )

    # Quantity requirement
    if minimum_qty > 0:
        if quantity_kg >= minimum_qty:
            matched.append(
                f"Quantity meets the buyer minimum ({quantity_kg:,.0f} kg available vs {minimum_qty:,.0f} kg required)."
            )
        else:
            shortfall = minimum_qty - quantity_kg
            gaps.append(
                f"Quantity is {shortfall:,.0f} kg below the buyer minimum "
                f"({quantity_kg:,.0f} kg available vs {minimum_qty:,.0f} kg required)."
            )
            actions.append(
                f"Arrange about {shortfall:,.0f} kg more compatible residue, "
                "or ask the buyer whether a smaller lot or combined pickup is acceptable."
            )

    # Moisture requirement
    if max_moisture is None:
        matched.append("The buyer has not provided a maximum moisture limit.")
    elif moisture_pct <= float(max_moisture):
        matched.append(
            f"Measured moisture ({moisture_pct:.1f}%) is within the buyer's stated limit ({float(max_moisture):.1f}%)."
        )
    else:
        gaps.append(
            f"Measured moisture ({moisture_pct:.1f}%) is above the buyer's stated limit "
            f"({float(max_moisture):.1f}%)."
        )
        actions.append(
            f"Dry the residue until a measurement meets the buyer's stated limit of "
            f"{float(max_moisture):.1f}%. Re-measure the actual lot before pickup."
        )

    # Cleanliness
    # Older listing records do not persist a dedicated cleaned flag, so do not
    # falsely claim that the lot is contaminated or clean. The preparation
    # checklist records this step separately.
    if cleaned is True:
        matched.append("Farmer has marked the lot as visibly cleaned.")
    elif cleaned is False:
        gaps.append(
            "Visible soil, stones, plastic or other contamination has not been confirmed as removed."
        )
        actions.append(
            "Separate visible soil, stones, plastic and other contamination. "
            "Do not mix contaminated material into the buyer lot."
        )

    # Processing status
    if processed:
        matched.append("Farmer has marked the requested processing as completed.")
    elif required_form:
        # Only turn buyer-provided wording into an action; do not invent a recipe.
        actions.append(
            f"The buyer's processing requirement is: “{buyer.get('processing_required', 'Not specified')}”. "
            "Complete only the processing the buyer has requested and confirm the specification before delivery."
        )

    # Packaging
    packaging = str(buyer.get("packaging", "") or "").strip()
    if packaging and packaging.lower() not in {"not specified", "none", "n/a"}:
        actions.append(
            f"Prepare packaging according to the buyer's stated requirement: {packaging}. "
            "Confirm bale/package size or other packaging details before pickup."
        )

    # Pickup
    pickup_available = buyer.get("pickup_available")
    if pickup_available:
        matched.append("Buyer has listed pickup availability.")
    else:
        actions.append(
            "Pickup is not listed as available. Confirm who will arrange transport "
            "before accepting the buyer's terms."
        )

    # Readiness is deliberately conservative:
    # every identified hard gap means the lot is not ready.
    ready = not gaps

    return {
        "ready": ready,
        "gaps": gaps,
        "actions": actions,
        "matched": matched,
    }


def normalize_rfq_requirement(rfq: dict) -> dict:
    """
    Normalize a buyer RFQ into the requirement shape used by the preparation
    assistant. RFQ data is treated as the authoritative buyer specification.
    """
    return {
        "buyer_id": rfq["buyer_id"],
        "buyer_name": rfq["buyer_name"],
        "location": rfq.get("location", ""),
        "accepted_forms": list(rfq.get("accepted_forms") or []),
        "processing_required": rfq.get("processing_required", ""),
        "max_moisture_pct": rfq.get("max_moisture_pct"),
        "min_quantity_kg": float(rfq.get("min_quantity_kg") or 0),
        "packaging": rfq.get("packaging", ""),
        "pickup_available": bool(rfq.get("pickup_required")),
        "notes": rfq.get("notes", ""),
        "source": "RFQ",
        "rfq_id": rfq["rfq_id"],
    }


def render_requirement_gap(buyer: dict, gap: dict) -> None:
    """Render the gap analysis in a farmer-friendly, low-jargon format."""
    if gap["ready"]:
        st.success(
            "This lot currently meets the buyer requirements that were provided. "
            "Confirm the final specification with the buyer before pickup."
        )
    else:
        st.warning(
            f"{len(gap['gaps'])} requirement(s) still need attention before this lot is buyer-ready."
        )

    if gap["gaps"]:
        st.markdown("**What needs attention**")
        for item in gap["gaps"]:
            st.markdown(f"- {item}")

    if gap["matched"]:
        st.markdown("**Already meeting requirements**")
        for item in gap["matched"]:
            st.markdown(f"- {item}")

    if gap["actions"]:
        st.markdown("**Step-by-step preparation plan**")
        for index, action in enumerate(gap["actions"], start=1):
            st.markdown(f"**{index}.** {action}")

    st.caption(
        "This checklist compares the information entered by the farmer with the buyer's "
        "stated requirements. It does not replace the buyer's final quality inspection."
    )


# ============================================================
# TRANSACTION WORKSPACE HELPERS
# ============================================================

def _contact_card(user_id: str, title: str) -> None:
    """Show participant contact details only after mutual transaction confirmation."""
    contact = get_user_contact(user_id)
    if not contact:
        st.info("Contact details are not available for this account.")
        return

    phone = contact.get("phone") or "Phone number not provided"
    st.markdown(
        f"""
        <div class="context-card">
            <div class="context-label">{title}</div>
            <div class="context-value">{contact["full_name"]}</div>
            <div style="margin-top:.35rem;color:#4D5D53;">
                Email: {contact["email"]}<br>
                Phone: {phone}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_deal_status(status: str) -> None:
    st.markdown(
        f'<span class="status-pill">Status · {status}</span>',
        unsafe_allow_html=True,
    )


def _render_deal_messages(deal_id: int, actor_id: str) -> None:
    messages = get_deal_messages(deal_id, actor_id)
    if not messages:
        st.caption("No negotiation messages yet.")
        return

    st.markdown("**Negotiation history**")
    for item in messages:
        sender = "Buyer" if item["sender_role"] == "buyer" else "Farmer"
        details = []
        if item["proposed_quantity_kg"] is not None:
            details.append(f"{item['proposed_quantity_kg']:,.0f} kg")
        if item["proposed_price_per_kg"] is not None:
            details.append(f"₹{item['proposed_price_per_kg']:,.2f}/kg")
        if item["proposed_pickup_date"]:
            details.append(f"pickup {item['proposed_pickup_date']}")

        terms = f" · {' · '.join(details)}" if details else ""
        message = item["message"] or "Terms updated."
        st.markdown(
            f"""
            <div class="context-card" style="margin:.35rem 0;">
                <div style="font-weight:750;color:#285C3A;">{sender} · {item["message_type"]}</div>
                <div style="margin-top:.25rem;color:#24332A;">{message}</div>
                <div style="margin-top:.25rem;color:#6C756E;font-size:.82rem;">{item["created_at"]}{terms}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_deal_actions(deal: dict, actor_id: str, actor_role: str) -> None:
    deal_id = int(deal["deal_id"])
    status = deal["status"]

    st.markdown("**Current agreed terms**")
    t1, t2, t3 = st.columns(3)
    t1.metric("Quantity", f"{deal['agreed_quantity_kg']:,.0f} kg")
    t2.metric(
        "Price",
        "Not specified"
        if deal["agreed_price_per_kg"] is None
        else f"₹{deal['agreed_price_per_kg']:,.2f}/kg",
    )
    t3.metric(
        "Pickup",
        deal["pickup_date"] or "Not scheduled",
    )

    _render_deal_status(status)

    if status == "Buyer Confirmed" and actor_role == "buyer":
        st.info("You have confirmed these terms. Waiting for the farmer to confirm.")
    elif status == "Buyer Confirmed" and actor_role == "farmer":
        st.info("The buyer has confirmed these terms. Review them and confirm when you agree.")
    elif status == "Farmer Confirmed" and actor_role == "farmer":
        st.info("You have confirmed these terms. Waiting for the buyer to confirm.")
    elif status == "Farmer Confirmed" and actor_role == "buyer":
        st.info("The farmer has confirmed these terms. Review them and confirm when you agree.")
    elif status == "Confirmed":
        st.success("Both sides have confirmed. The residue lot is reserved for this transaction.")

    if status in {"Negotiation", "Buyer Confirmed", "Farmer Confirmed"}:
        st.markdown("**Negotiate / send a message**")
        n1, n2 = st.columns(2)
        with n1:
            proposed_qty = st.number_input(
                "Proposed quantity (kg)",
                min_value=1.0,
                value=float(deal["agreed_quantity_kg"]),
                step=10.0,
                key=f"deal_qty_{deal_id}_{actor_role}",
            )
        with n2:
            proposed_price = st.number_input(
                "Proposed price (₹/kg)",
                min_value=0.0,
                value=float(deal["agreed_price_per_kg"] or 0),
                step=0.50,
                key=f"deal_price_{deal_id}_{actor_role}",
            )
        proposed_pickup = st.text_input(
            "Proposed pickup date / time",
            value=deal["pickup_date"] or "",
            placeholder="Example: 28 Sep 2026, 10:00 AM",
            key=f"deal_pickup_{deal_id}_{actor_role}",
        )
        message = st.text_area(
            "Message / negotiation note",
            placeholder="Example: I can supply 1,200 kg at ₹4.50/kg and have the lot ready for pickup.",
            key=f"deal_message_{deal_id}_{actor_role}",
        )

        if st.button(
            "Send negotiation update",
            key=f"deal_send_{deal_id}_{actor_role}",
            use_container_width=True,
        ):
            try:
                send_deal_message(
                    deal_id=deal_id,
                    sender_id=actor_id,
                    sender_role=actor_role,
                    message=message,
                    proposed_quantity_kg=proposed_qty,
                    proposed_price_per_kg=proposed_price if proposed_price > 0 else None,
                    proposed_pickup_date=proposed_pickup.strip() or None,
                )
                st.success("Negotiation update sent.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

        st.divider()

        confirm_label = (
            "Confirm purchase"
            if actor_role == "buyer"
            else "Confirm agreement"
        )
        if st.button(
            confirm_label,
            type="primary",
            key=f"deal_confirm_{deal_id}_{actor_role}",
            use_container_width=True,
        ):
            try:
                new_status = confirm_deal(
                    deal_id=deal_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                )
                if new_status == "Confirmed":
                    st.success(
                        "Both sides have confirmed. The residue lot is now reserved."
                    )
                else:
                    st.success(
                        f"Your confirmation was recorded. Waiting for the other party. Status: {new_status}"
                    )
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    if status == "Confirmed":
        st.info(
            "Both parties have confirmed the current terms. Contact details are now available "
            "to coordinate the physical handover."
        )
        other_id = deal["farmer_id"] if actor_role == "buyer" else deal["buyer_id"]
        _contact_card(
            other_id,
            "Verified transaction contact",
        )

        pickup_date = st.text_input(
            "Pickup date / time",
            value=deal["pickup_date"] or "",
            placeholder="Example: 28 Sep 2026, 10:00 AM",
            key=f"schedule_date_{deal_id}_{actor_role}",
        )
        pickup_notes = st.text_area(
            "Pickup instructions",
            value=deal["pickup_notes"] or "",
            placeholder="Example: Call before arrival; lot is stored beside the farm shed.",
            key=f"schedule_notes_{deal_id}_{actor_role}",
        )
        if st.button(
            "Schedule pickup",
            key=f"schedule_{deal_id}_{actor_role}",
            use_container_width=True,
        ):
            try:
                schedule_pickup(
                    deal_id=deal_id,
                    actor_id=actor_id,
                    pickup_date=pickup_date,
                    pickup_notes=pickup_notes,
                )
                st.success("Pickup scheduled.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    if status == "Pickup Scheduled":
        other_id = deal["farmer_id"] if actor_role == "buyer" else deal["buyer_id"]
        _contact_card(other_id, "Verified transaction contact")

        st.info(
            f"Pickup is scheduled for {deal['pickup_date'] or 'the agreed time'}. "
            "After the residue is physically weighed/checked, the farmer records the actual handover. "
            "The buyer then verifies what was received."
        )

        if actor_role == "farmer":
            st.markdown("**Step 1 · Record the actual handover**")
            h1, h2 = st.columns(2)
            with h1:
                actual_qty = st.number_input(
                    "Actual quantity handed over (kg)",
                    min_value=0.1,
                    max_value=float(deal["agreed_quantity_kg"]) if deal.get("agreed_quantity_kg") else 1_000_000.0,
                    value=float(deal["agreed_quantity_kg"]),
                    step=1.0,
                    key=f"handover_qty_{deal_id}",
                    help="Use the quantity actually weighed at handover. It may be lower than the agreed quantity.",
                )
            with h2:
                actual_moisture = st.number_input(
                    "Measured moisture (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(deal["actual_moisture_pct"] or 0.0),
                    step=0.5,
                    key=f"handover_moisture_{deal_id}",
                    help="Enter the actual lot measurement if a moisture meter was used. Do not use an assumed value.",
                )

            handover_notes = st.text_area(
                "Handover / quality notes",
                value=deal["handover_notes"] or "",
                placeholder="Example: 1,180 kg weighed at pickup. Material was dry, clean and packed in 20 bales.",
                key=f"handover_notes_{deal_id}",
            )

            if st.button(
                "Submit handover for buyer review",
                type="primary",
                key=f"submit_handover_{deal_id}",
                use_container_width=True,
            ):
                try:
                    submit_handover(
                        deal_id=deal_id,
                        actor_id=actor_id,
                        actual_quantity_kg=actual_qty,
                        actual_moisture_pct=actual_moisture,
                        handover_notes=handover_notes,
                    )
                    st.success(
                        "Handover details submitted. The buyer can now review and confirm the received residue."
                    )
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

        else:
            st.markdown("**Step 1 · Wait for the farmer's handover record**")
            st.caption(
                "The farmer must record the actual weighed quantity and any measured quality details "
                "before you confirm receipt."
            )

    if status == "Handover Review":
        other_id = deal["farmer_id"] if actor_role == "buyer" else deal["buyer_id"]
        _contact_card(other_id, "Verified transaction contact")

        st.markdown("**Physical handover record**")
        r1, r2, r3 = st.columns(3)
        r1.metric(
            "Agreed quantity",
            f"{deal['agreed_quantity_kg']:,.0f} kg",
        )
        r2.metric(
            "Actual quantity",
            f"{float(deal['actual_quantity_kg']):,.0f} kg"
            if deal.get("actual_quantity_kg") is not None
            else "Not recorded",
        )
        r3.metric(
            "Measured moisture",
            f"{float(deal['actual_moisture_pct']):.1f}%"
            if deal.get("actual_moisture_pct") is not None
            else "Not recorded",
        )

        if deal.get("handover_notes"):
            st.markdown(
                f"""
                <div class="context-card">
                    <div class="context-label">Handover notes</div>
                    <div class="context-value">{deal["handover_notes"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if actor_role == "buyer":
            st.warning(
                "Check the actual quantity and quality against your agreed requirements before confirming receipt."
            )
            if st.button(
                "Confirm residue received",
                type="primary",
                key=f"confirm_handover_{deal_id}",
                use_container_width=True,
            ):
                try:
                    confirm_handover(
                        deal_id=deal_id,
                        actor_id=actor_id,
                        actor_role=actor_role,
                    )
                    st.success(
                        "Receipt confirmed. The transaction is complete and the delivered quantity has been removed from active inventory."
                    )
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        else:
            st.info(
                "Handover details have been submitted. The buyer must confirm receipt before the transaction is completed."
            )

    if status in {"Picked Up", "Completed"}:
        st.success(
            "This residue transaction is complete. The delivered quantity is no longer offered as an active lot."
        )
        other_id = deal["farmer_id"] if actor_role == "buyer" else deal["buyer_id"]
        _contact_card(other_id, "Transaction contact")

        receipt = get_transaction_receipt(deal_id)
        if receipt:
            receipt_text = (
                f"AgriWaste AI Transaction Receipt\n"
                f"Deal: Deal-{deal_id:05d}\n"
                f"Listing: AW-{receipt['listing_id']:05d}\n"
                f"Crop: {receipt['crop']}\n"
                f"Residue: {receipt['residue']}\n"
                f"Agreed quantity: {receipt['agreed_quantity_kg']:,.0f} kg\n"
                f"Actual delivered quantity: {float(receipt['actual_quantity_kg'] or 0):,.0f} kg\n"
                f"Agreed price: "
                f"{'Not specified' if receipt['agreed_price_per_kg'] is None else f'₹{receipt['agreed_price_per_kg']:,.2f}/kg'}\n"
                f"Measured moisture: "
                f"{'Not recorded' if receipt['actual_moisture_pct'] is None else f'{float(receipt['actual_moisture_pct']):.1f}%'}\n"
                f"Pickup: {receipt['pickup_date'] or 'Not recorded'}\n"
                f"Status: {receipt['status']}\n"
                f"Completed: {receipt['completed_at'] or 'Not recorded'}\n"
                f"Handover notes: {receipt['handover_notes'] or 'None'}\n"
            )
            st.download_button(
                "Download transaction receipt",
                data=receipt_text,
                file_name=f"AgriWaste_Deal_{deal_id:05d}_receipt.txt",
                mime="text/plain",
                use_container_width=True,
            )



# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AgriWaste AI",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>
    /* =========================================================
       AGRIWASTE AI — WARM AGRICULTURAL VISUAL SYSTEM
       Warm cream + forest green + sage + muted gold
       ========================================================= */

    :root {
        --cream: #F6F2E8;
        --cream-deep: #EEE8D9;
        --surface: #FFFCF6;
        --surface-soft: #F3EFE4;
        --forest: #285C3A;
        --forest-dark: #1F4930;
        --forest-deep: #183B28;
        --sage: #DDE8D5;
        --sage-strong: #C8D9BF;
        --gold: #C9A84E;
        --gold-soft: #F1E5BE;
        --ink: #24332A;
        --muted: #6C756E;
        --line: #D9D7CC;
        --shadow: rgba(38, 55, 44, 0.07);
    }

    /* ---------- Global canvas ---------- */
    .stApp {
        background: var(--cream) !important;
        color: var(--ink) !important;
    }

    [data-testid="stAppViewContainer"] {
        background: var(--cream) !important;
    }

    [data-testid="stHeader"] {
        background: rgba(246, 242, 232, 0.94) !important;
    }

    [data-testid="stMain"] {
        background: var(--cream) !important;
    }

    .main {
        padding-top: 1rem;
    }

    /* ---------- Typography ---------- */
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,600;9..144,700;9..144,800&display=swap');

    html, body, [class*="css"] {
        font-family: "DM Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
    }

    h1, h2, h3,
    .hero-main-title,
    .analysis-title,
    .page-title,
    .section-heading {
        font-family: "Fraunces", Georgia, serif !important;
        color: var(--ink) !important;
        letter-spacing: -0.025em;
    }

    h1, h2, h3, h4, h5, h6,
    p, label, span, div {
        color: inherit;
    }

    .page-title {
        font-size: clamp(2.2rem, 4vw, 3.55rem);
        line-height: 1.04;
        font-weight: 700;
        margin: 0 0 .55rem 0;
    }

    .hero-main-title {
        font-size: clamp(3.1rem, 5vw, 5rem) !important;
        line-height: 1.02 !important;
        font-weight: 700 !important;
        overflow-wrap: normal !important;
        word-break: normal !important;
        hyphens: none !important;
    }

    .analysis-title {
        font-size: clamp(2.4rem, 4.5vw, 4rem) !important;
        line-height: 1.03 !important;
        font-weight: 700 !important;
    }


    /* ---------- Sidebar collapse / expand control ---------- */
    [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stSidebarCollapsedControl"] button {
        background: #E3E8D8 !important;
        border: 1px solid #CDD8C3 !important;
        border-radius: 10px !important;
        color: #285C3A !important;
        box-shadow: none !important;
        transition: background .15s ease, border-color .15s ease, color .15s ease !important;
    }

    [data-testid="stSidebarCollapseButton"] button:hover,
    [data-testid="stSidebarCollapsedControl"] button:hover {
        background: #D6E1CC !important;
        border-color: #B9CDB1 !important;
        color: #1F4A2E !important;
    }

    [data-testid="stSidebarCollapseButton"] button svg,
    [data-testid="stSidebarCollapsedControl"] button svg {
        color: #285C3A !important;
        fill: #285C3A !important;
        stroke: #285C3A !important;
    }

    /* ---------- Sidebar ---------- */
    [data-testid="stSidebar"] {
        background: #F0ECE2 !important;
        color: #24352B !important;
        border-right: 1px solid #DDD8CB !important;
    }

    [data-testid="stSidebar"] > div:first-child {
        background: #F0ECE2 !important;
        padding-top: 1.25rem !important;
    }

    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] label {
        color: var(--ink) !important;
    }

    [data-testid="stSidebar"] hr {
        border-color: #D9D4C8 !important;
        margin: 1.15rem 0 !important;
    }

    [data-testid="stSidebar"] .stRadio > label {
        color: var(--muted) !important;
        font-size: .88rem !important;
        font-weight: 700 !important;
        letter-spacing: .04em !important;
        margin-bottom: .45rem !important;
    }

    /* Sidebar navigation: remove Streamlit's native radio dot.
       The navigation label itself is the clickable control, with
       compact icon/text spacing and a clear sage active state. */
    [data-testid="stSidebar"] div[data-testid="stRadio"] > div {
        gap: .16rem !important;
    }

    [data-testid="stSidebar"] div[data-testid="stRadio"] label {
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        box-sizing: border-box !important;
        border-radius: 11px !important;
        padding: .48rem .62rem !important;
        margin: .04rem 0 !important;
        color: var(--ink) !important;
        background: transparent !important;
        font-weight: 600 !important;
        line-height: 1.25 !important;
        transition: background .15s ease, color .15s ease !important;
    }

    /* Hide the actual radio circle so it cannot appear as a red/black dot. */
    [data-testid="stSidebar"] div[data-testid="stRadio"] label input[type="radio"] {
        position: absolute !important;
        opacity: 0 !important;
        width: 1px !important;
        height: 1px !important;
        pointer-events: none !important;
    }

    /* Force the navigation text/icon to remain dark and readable. */
    [data-testid="stSidebar"] div[data-testid="stRadio"] label,
    [data-testid="stSidebar"] div[data-testid="stRadio"] label span,
    [data-testid="stSidebar"] div[data-testid="stRadio"] label p,
    [data-testid="stSidebar"] div[data-testid="stRadio"] label div {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
    }

    [data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {
        background: rgba(40, 92, 58, .07) !important;
        color: var(--forest) !important;
    }

    [data-testid="stSidebar"] div[data-testid="stRadio"] label:hover span,
    [data-testid="stSidebar"] div[data-testid="stRadio"] label:hover p {
        color: var(--forest) !important;
        -webkit-text-fill-color: var(--forest) !important;
    }

    [data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) {
        background: var(--sage) !important;
        color: var(--forest) !important;
        font-weight: 700 !important;
        box-shadow: inset 3px 0 0 var(--forest) !important;
    }

    [data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) span,
    [data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) p,
    [data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) div {
        color: var(--forest) !important;
        -webkit-text-fill-color: var(--forest) !important;
    }

    /* ---------- Metrics / status visibility ----------
       Explicit colors prevent Streamlit theme inheritance from turning
       status labels white on the warm-cream application background. */
    [data-testid="stMetric"] {
        color: var(--ink) !important;
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] *,
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] *,
    [data-testid="stMetricDelta"],
    [data-testid="stMetricDelta"] * {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        opacity: 1 !important;
    }

    [data-testid="stMetricLabel"] {
        font-weight: 700 !important;
        color: #4B5C52 !important;
    }

    [data-testid="stMetricValue"] {
        font-weight: 700 !important;
    }

    .status-pill {
        display: inline-block;
        padding: .34rem .72rem;
        border-radius: 999px;
        background: #E3ECDD;
        border: 1px solid #C9D8C2;
        color: #285C3A !important;
        -webkit-text-fill-color: #285C3A !important;
        font-weight: 750;
        font-size: .84rem;
    }

    /* ---------- Links / active controls ---------- */
    a, a:visited {
        color: var(--forest) !important;
    }

    input[type="radio"],
    input[type="checkbox"] {
        accent-color: var(--forest) !important;
    }

    /* ---------- Primary action buttons ----------
       Forest green with guaranteed white text. */
    div.stButton > button[kind="primary"],
    button[data-testid="baseButton-primary"] {
        background: var(--forest) !important;
        border: 1px solid var(--forest) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border-radius: 12px !important;
        min-height: 2.85rem !important;
        box-shadow: 0 7px 18px rgba(40, 92, 58, .14) !important;
    }

    div.stButton > button[kind="primary"] *,
    button[data-testid="baseButton-primary"] * {
        color: #FFFFFF !important;
    }

    div.stButton > button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover {
        background: var(--forest-dark) !important;
        border-color: var(--forest-dark) !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
    }

    div.stButton > button[kind="secondary"],
    button[data-testid="baseButton-secondary"] {
        background: var(--surface) !important;
        border: 1px solid var(--line) !important;
        color: var(--forest) !important;
        border-radius: 12px !important;
    }

    div.stButton > button[kind="secondary"] * {
        color: var(--forest) !important;
    }

    /* Download buttons should look like intentional secondary actions. */
    [data-testid="stDownloadButton"] button {
        background: var(--surface) !important;
        border: 1px solid var(--forest) !important;
        color: var(--forest) !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
    }

    [data-testid="stDownloadButton"] button:hover {
        background: var(--sage) !important;
        color: var(--forest-dark) !important;
    }

    /* ---------- Select boxes / number inputs ----------
       High contrast instead of the previous near-black controls. */
    div[data-baseweb="select"] > div {
        background: var(--surface) !important;
        border: 1px solid #CFCFC4 !important;
        border-radius: 12px !important;
        min-height: 3rem !important;
        box-shadow: none !important;
    }

    div[data-baseweb="select"] *,
    div[data-baseweb="select"] input {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
    }

    div[data-baseweb="select"] svg {
        fill: var(--forest) !important;
        color: var(--forest) !important;
    }

    [role="listbox"],
    [role="option"] {
        background: var(--surface) !important;
        color: var(--ink) !important;
    }

    [role="option"]:hover,
    [role="option"][aria-selected="true"] {
        background: var(--sage) !important;
        color: var(--forest) !important;
    }

    [data-testid="stNumberInput"] input {
        background: var(--surface) !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        border-color: #CFCFC4 !important;
    }

    [data-testid="stNumberInput"] button {
        background: var(--surface) !important;
        color: var(--forest) !important;
        border-color: #CFCFC4 !important;
    }

    [data-testid="stNumberInput"] button:hover {
        background: var(--sage) !important;
        color: var(--forest-dark) !important;
    }

    /* ---------- Text inputs / text areas ----------
       Always use explicit high-contrast colors. Streamlit/BaseWeb
       theme inheritance can otherwise make typed text and placeholders
       nearly invisible against dark or inherited control backgrounds. */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        background: var(--surface) !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        caret-color: var(--forest) !important;
        border: 1px solid #CFCFC4 !important;
        border-radius: 12px !important;
        box-shadow: none !important;
    }

    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
        color: #718078 !important;
        -webkit-text-fill-color: #718078 !important;
        opacity: 1 !important;
    }

    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        background: #FFFEFA !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        border-color: var(--forest) !important;
        box-shadow: 0 0 0 1px var(--forest) !important;
        outline: none !important;
    }

    [data-testid="stTextArea"] textarea {
        min-height: 7rem !important;
        line-height: 1.5 !important;
        padding: .8rem .9rem !important;
        resize: vertical !important;
    }

    /* Streamlit validation/error states should not override readable
       text inside the actual control. */
    [data-testid="stTextInput"] input[aria-invalid="true"],
    [data-testid="stTextArea"] textarea[aria-invalid="true"] {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        background: #FFFEFA !important;
    }

    /* ---------- Upload area ---------- */
    [data-testid="stFileUploaderDropzone"] {
        background: var(--surface) !important;
        border: 1.5px dashed #BFC8BB !important;
        border-radius: 16px !important;
    }

    [data-testid="stFileUploaderDropzone"] * {
        color: var(--ink) !important;
    }

    [data-testid="stFileUploaderDropzone"] button {
        background: var(--sage) !important;
        color: var(--forest) !important;
        border: 1px solid var(--sage-strong) !important;
    }

    /* ---------- Radio controls in main content ---------- */
    div[data-testid="stRadio"] label {
        border-radius: 12px !important;
        padding: .42rem .6rem !important;
    }

    div[data-testid="stRadio"] label:has(input:checked) {
        background: var(--sage) !important;
        color: var(--forest) !important;
    }

    div[data-testid="stRadio"] label:has(input:checked) span {
        color: var(--forest) !important;
    }

    /* ---------- Editorial cards ---------- */
    .hero-wrap,
    .analysis-hero,
    .page-hero {
        background: #FBF8F0 !important;
        border: 1px solid #DDD9CD !important;
        box-shadow: 0 14px 34px var(--shadow) !important;
    }

    .hero-wrap {
        padding: 2.2rem 2.4rem;
        border-radius: 24px;
        margin-bottom: 1.4rem;
    }

    .analysis-hero,
    .page-hero {
        padding: 1.75rem 2rem;
        border-radius: 22px;
        margin-bottom: 1.25rem;
    }

    .hero-copy,
    .analysis-copy,
    .page-copy {
        color: #56625A !important;
        line-height: 1.65;
    }

    .hero-pill,
    .utilizer-badge {
        color: var(--forest) !important;
        border-color: #C9D8C3 !important;
        background: var(--sage) !important;
        border-radius: 999px !important;
    }

    .eyebrow,
    .analysis-kicker,
    .page-kicker,
    .section-kicker,
    .context-label,
    .metric-label,
    .tech-name,
    .result-kicker,
    .validation-status {
        color: #667A6B !important;
    }

    .section-heading {
        color: var(--ink) !important;
    }

    /* ---------- Cards ---------- */
    .stat-card,
    .feature-card,
    .result-card,
    .pathway-card,
    .metric-card,
    .score-card,
    .utilizer-card,
    .tech-card,
    .about-block,
    .validation-card,
    .history-card,
    .upload-card {
        background: rgba(255, 252, 246, .72) !important;
        border: 1px solid #DDDAD0 !important;
        box-shadow: 0 8px 24px rgba(38, 55, 44, .045) !important;
        box-sizing: border-box !important;
    }

    /* Comfortable editorial spacing inside all content cards.
       The previous version placed text too close to the left border. */
    .result-card,
    .metric-card,
    .score-card,
    .pathway-card,
    .utilizer-card,
    .tech-card,
    .about-block,
    .validation-card,
    .history-card,
    .upload-card {
        padding: 1.15rem 1.35rem !important;
        border-radius: 16px !important;
        margin-bottom: .8rem !important;
    }

    .stat-card {
        padding: 1.1rem 1.2rem;
        border-radius: 16px;
    }

    .feature-card {
        padding: 1.35rem;
        border-radius: 18px;
    }

    /* Give badges/pills their own breathing room so they do not look
       like full-width cylinders attached to the card edges. */
    .utilizer-badge,
    .hero-pill {
        display: inline-flex !important;
        align-items: center !important;
        width: fit-content !important;
        max-width: 100% !important;
        padding: .32rem .78rem !important;
        margin: .45rem 0 .55rem 0 !important;
        line-height: 1.35 !important;
        box-sizing: border-box !important;
    }

    .pathway-name,
    .score-name,
    .feature-title {
        margin-bottom: .4rem !important;
    }

    .pathway-score {
        margin-bottom: .45rem !important;
    }

    .metric-label,
    .result-kicker,
    .context-label {
        margin-bottom: .45rem !important;
    }

    .metric-value,
    .result-value,
    .score-number {
        margin-bottom: .3rem !important;
    }

    .feature-number,
    .metric-label,
    .tech-name {
        letter-spacing: .09em !important;
        color: #738076 !important;
    }

    .feature-icon {
        color: var(--forest) !important;
    }

    .feature-title,
    .pathway-name,
    .score-name {
        color: var(--ink) !important;
    }

    .feature-text,
    .score-reason,
    .metric-note,
    .result-small {
        color: var(--muted) !important;
    }

    .context-card,
    .residue-card,
    .about-callout,
    .architecture {
        background: #EAF0E5 !important;
        border: 1px solid #CBD8C3 !important;
        color: var(--ink) !important;
    }

    .context-value,
    .score-number,
    .validation-status {
        color: var(--forest) !important;
    }

    /* ---------- Workspace quick actions ---------- */
    .quick-action-card {
        background: #FFFCF6 !important;
        border: 1px solid #D9DED5 !important;
        border-radius: 16px !important;
        padding: 1rem 1.05rem !important;
        min-height: 112px !important;
        box-sizing: border-box !important;
        box-shadow: 0 6px 18px rgba(38, 55, 44, .035) !important;
    }

    .quick-action-title {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        font-weight: 750 !important;
        font-size: 1rem !important;
        line-height: 1.25 !important;
        margin-bottom: .38rem !important;
    }

    .quick-action-text {
        color: #647168 !important;
        -webkit-text-fill-color: #647168 !important;
        font-size: .84rem !important;
        line-height: 1.45 !important;
    }

    .mini-summary-card {
        background: #EAF0E5 !important;
        border: 1px solid #CBD8C3 !important;
        border-radius: 14px !important;
        padding: .9rem 1rem !important;
        margin-top: .8rem !important;
        box-sizing: border-box !important;
    }

    .mini-summary-label {
        display: block !important;
        color: #526359 !important;
        -webkit-text-fill-color: #526359 !important;
        font-size: .78rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: .055em !important;
        margin-bottom: .25rem !important;
    }

    .mini-summary-value {
        display: block !important;
        color: var(--forest) !important;
        -webkit-text-fill-color: var(--forest) !important;
        font-size: 1.45rem !important;
        font-weight: 750 !important;
        line-height: 1.15 !important;
    }

    /* ---------- Farmer dashboard KPI accessibility ----------
       Use custom KPI cards instead of Streamlit's native st.metric.
       This gives us deterministic typography/contrast across Streamlit
       versions and themes. */
    .farmer-kpi-card {
        background: rgba(255, 252, 246, .82) !important;
        border: 1px solid #D7DED3 !important;
        border-radius: 16px !important;
        padding: 1rem 1.15rem !important;
        min-height: 92px !important;
        box-sizing: border-box !important;
        box-shadow: 0 6px 18px rgba(38, 55, 44, .035) !important;
    }

    .farmer-kpi-label {
        display: block !important;
        color: #3F5148 !important;
        -webkit-text-fill-color: #3F5148 !important;
        font-size: .92rem !important;
        font-weight: 650 !important;
        line-height: 1.3 !important;
        margin: 0 0 .35rem 0 !important;
        opacity: 1 !important;
    }

    .farmer-kpi-value {
        display: block !important;
        color: var(--forest) !important;
        -webkit-text-fill-color: var(--forest) !important;
        font-size: 2rem !important;
        font-weight: 750 !important;
        line-height: 1.05 !important;
        margin: 0 !important;
        opacity: 1 !important;
    }

    .farmer-kpi-card * {
        opacity: 1 !important;
    }

    /* ---------- Context / notice boxes ----------
       Add the same comfortable left-right breathing room used by the
       larger editorial cards. This prevents text from touching borders. */
    .context-card,
    .residue-card,
    .about-callout {
        box-sizing: border-box !important;
        padding: 1rem 1.25rem !important;
        border-radius: 14px !important;
        margin: .65rem 0 1rem !important;
    }

    .context-label {
        display: block !important;
        margin: 0 0 .5rem !important;
        line-height: 1.35 !important;
    }

    .context-value {
        display: block !important;
        line-height: 1.45 !important;
    }

    .residue-name {
        margin: 0 0 .5rem !important;
        line-height: 1.4 !important;
    }

    /* Streamlit info/warning/success notices: keep the native component,
       but give its content proper editorial padding. */
    [data-testid="stAlert"] {
        box-sizing: border-box !important;
        padding: .9rem 1.15rem !important;
        margin: .75rem 0 1rem !important;
        border-radius: 14px !important;
    }

    [data-testid="stAlert"] > div {
        gap: .7rem !important;
        align-items: flex-start !important;
    }

    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Alert text must remain readable on Streamlit's pale notice backgrounds.
       Keep the palette warm and neutral, but never allow inherited white text
       to disappear inside yellow/info/success boxes. */
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] li,
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] strong,
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] em {
        color: var(--ink) !important;
    }

    [data-testid="stAlert"] p {
        margin: 0 !important;
        line-height: 1.55 !important;
        font-weight: 500 !important;
    }

    [data-testid="stAlert"] svg {
        flex-shrink: 0 !important;
        margin-top: .15rem !important;
        color: var(--forest) !important;
        fill: currentColor !important;
        stroke: currentColor !important;
    }


    .score-fill,
    .confidence-fill {
        background: var(--forest) !important;
    }

    .score-track,
    .confidence-track {
        background: #DCE1D8 !important;
    }

    /* Gold is reserved for small accents, not primary actions. */
    .gold-accent {
        color: var(--gold) !important;
    }

    /* ---------- Main widget labels: high-contrast on cream ---------- */
    [data-testid="stMain"] [data-testid="stWidgetLabel"],
    [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
    [data-testid="stMain"] [data-testid="stWidgetLabel"] span,
    [data-testid="stMain"] .stSelectbox label,
    [data-testid="stMain"] .stSelectbox label p,
    [data-testid="stMain"] .stRadio > label,
    [data-testid="stMain"] .stRadio > label p,
    [data-testid="stMain"] .stFileUploader > label,
    [data-testid="stMain"] .stFileUploader > label p,
    [data-testid="stMain"] .stNumberInput > label,
    [data-testid="stMain"] .stNumberInput > label p {
        color: var(--forest-deep) !important;
        -webkit-text-fill-color: var(--forest-deep) !important;
        font-weight: 700 !important;
        opacity: 1 !important;
    }

    /* Keep radio option text readable too. */
    [data-testid="stMain"] [data-testid="stRadio"] label,
    [data-testid="stMain"] [data-testid="stRadio"] label p,
    [data-testid="stMain"] [data-testid="stRadio"] label span,
    [data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label,
    [data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label p {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        opacity: 1 !important;
    }

    [data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked),
    [data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) p,
    [data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) span {
        color: var(--forest) !important;
        -webkit-text-fill-color: var(--forest) !important;
        font-weight: 700 !important;
    }

    /* Give controls the same editorial rhythm as the reference design. */
    [data-testid="stMain"] .stSelectbox,
    [data-testid="stMain"] .stRadio,
    [data-testid="stMain"] .stFileUploader,
    [data-testid="stMain"] .stNumberInput {
        margin-bottom: .7rem !important;
    }

    [data-testid="stMain"] .stSelectbox > label,
    [data-testid="stMain"] .stRadio > label,
    [data-testid="stMain"] .stFileUploader > label,
    [data-testid="stMain"] .stNumberInput > label {
        margin-bottom: .42rem !important;
        font-size: .93rem !important;
        letter-spacing: .01em !important;
    }

    /* ---------- System architecture: visual flow instead of ASCII ---------- */
    .architecture-shell {
        background: rgba(255, 252, 246, .86) !important;
        border: 1px solid #D7DDD0 !important;
        border-radius: 20px !important;
        padding: 1.35rem 1.25rem 1.25rem !important;
        box-shadow: 0 10px 28px rgba(38,55,44,.045) !important;
        overflow: hidden !important;
    }

    .architecture-subtitle {
        color: #69766D !important;
        font-size: .92rem !important;
        margin: .12rem 0 1.05rem !important;
    }

    .arch-row {
        display: grid !important;
        grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
        gap: .65rem !important;
        align-items: stretch !important;
    }

    .arch-node {
        position: relative !important;
        min-height: 112px !important;
        padding: .9rem .8rem !important;
        background: #FFFCF6 !important;
        border: 1px solid #E0DED4 !important;
        border-radius: 15px !important;
        box-sizing: border-box !important;
    }

    .arch-node:not(:last-child)::after {
        content: "→" !important;
        position: absolute !important;
        right: -.62rem !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        z-index: 2 !important;
        color: #7B8D7B !important;
        background: #F7F3E9 !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        line-height: 1 !important;
        padding: .05rem .08rem !important;
    }

    .arch-icon {
        width: 34px !important;
        height: 34px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 50% !important;
        background: #EAF0E5 !important;
        color: var(--forest) !important;
        font-size: 1rem !important;
        margin-bottom: .55rem !important;
    }

    .arch-title {
        color: var(--forest-deep) !important;
        font-size: .88rem !important;
        line-height: 1.25 !important;
        font-weight: 700 !important;
        margin-bottom: .28rem !important;
    }

    .arch-copy {
        color: #6C756E !important;
        font-size: .72rem !important;
        line-height: 1.35 !important;
    }

    .arch-branch {
        display: grid !important;
        grid-template-columns: 1fr 1fr 1fr !important;
        gap: 1.1rem !important;
        width: 66% !important;
        margin: .9rem auto .8rem !important;
        position: relative !important;
    }

    .arch-branch::before {
        content: "" !important;
        position: absolute !important;
        left: 16.66% !important;
        right: 16.66% !important;
        top: -.45rem !important;
        border-top: 2px solid #9CB19C !important;
    }

    .arch-branch .arch-node {
        min-height: 94px !important;
    }

    .arch-branch .arch-node::before {
        content: "↓" !important;
        position: absolute !important;
        left: 50% !important;
        top: -.9rem !important;
        transform: translateX(-50%) !important;
        color: #5E8064 !important;
        font-weight: 700 !important;
        background: #FFFCF6 !important;
        padding: 0 .12rem !important;
    }

    .arch-branch .arch-node::after {
        display: none !important;
    }

    .arch-final {
        width: min(58%, 720px) !important;
        margin: .25rem auto 0 !important;
        padding: .82rem 1rem !important;
        border-radius: 14px !important;
        background: linear-gradient(90deg, #EAF0E5, #F3EFD9) !important;
        border: 1px solid #D5DFC9 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: .65rem !important;
        color: var(--forest-deep) !important;
        font-weight: 700 !important;
    }

    .arch-final-icon {
        width: 30px !important;
        height: 30px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 50% !important;
        background: var(--forest) !important;
        color: #FFFFFF !important;
        font-size: .9rem !important;
    }

    .arch-final-copy strong {
        color: var(--forest-deep) !important;
        display: block !important;
        font-size: .9rem !important;
    }

    .arch-final-copy span {
        color: #6C756E !important;
        display: block !important;
        font-size: .72rem !important;
        font-weight: 500 !important;
        margin-top: .12rem !important;
    }

    @media (max-width: 900px) {
        .arch-row { grid-template-columns: 1fr !important; }
        .arch-node:not(:last-child)::after { content: "↓" !important; right: 50% !important; top: auto !important; bottom: -.72rem !important; transform: translateX(50%) !important; }
        .arch-branch { width: 100% !important; grid-template-columns: 1fr !important; }
        .arch-branch::before { display: none !important; }
        .arch-branch .arch-node::before { content: "↓" !important; top: -.85rem !important; }
        .arch-final { width: 100% !important; }
    }

    /* ---------- Plotly container ---------- */
    [data-testid="stPlotlyChart"] {
        background: var(--surface) !important;
        border: 1px solid #DDDAD0 !important;
        border-radius: 16px !important;
        padding: .35rem !important;
        box-shadow: 0 7px 20px rgba(38,55,44,.04) !important;
    }

    /* ---------- Alerts / notices ---------- */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
    }

    /* ---------- Dividers / footer ---------- */
    hr {
        border-color: #DDD9CD !important;
    }

    .footer {
        color: #737B75 !important;
        text-align: center;
        padding: 2rem 0 1rem 0;
        font-size: 13px;
    }

    /* ---------- Image treatment ---------- */
    .hero-image {
        border-radius: 18px;
        border: 1px solid #D9D7CC;
        overflow: hidden;
        box-shadow: 0 12px 28px rgba(38,55,44,.06);
    }

    .image-caption {
        color: #777D77 !important;
        text-align: center;
        font-size: 12px;
        margin-top: .4rem;
        margin-bottom: 1rem;
        font-style: italic;
    }

    /* Keep code/architecture readable on cream. */
    code, pre {
        color: var(--forest-deep) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# AUTHENTICATION / ROLE ACCESS
# ============================================================

def current_user() -> dict:
    return st.session_state["authenticated_user"]


def require_role(*roles: str) -> None:
    user = current_user()
    if user["role"] not in roles:
        st.error("This workspace is not available for your account role.")
        st.stop()


def render_auth_screen():
    """Render sign-in / account creation before protected application pages."""
    initialize_auth_db()

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Secure workspace · Phase 03A</div>
            <div class="page-title">Welcome to AgriWaste AI.</div>
            <div class="page-copy">
                Sign in to manage your residue lots, buyer requirements and marketplace activity.
                Your role controls which workspace features you can access.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


    st.markdown(
        """
        <style>
        /* Authentication tabs — BaseWeb + Streamlit fallback selectors.
           Streamlit renders tabs through BaseWeb in some versions, so
           role-only selectors are not sufficient. Keep every text node
           explicitly readable on the warm-cream background. */
        [data-testid="stTabs"] [role="tablist"],
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 2.25rem !important;
            border-bottom: 1px solid #D9D6CB !important;
        }

        [data-testid="stTabs"] [role="tab"],
        [data-testid="stTabs"] button[data-baseweb="tab"] {
            color: #26382F !important;
            -webkit-text-fill-color: #26382F !important;
            font-weight: 650 !important;
            font-size: 1rem !important;
            opacity: 1 !important;
            padding: .65rem .1rem .8rem .1rem !important;
            background: transparent !important;
            text-shadow: none !important;
        }

        [data-testid="stTabs"] [role="tab"] *,
        [data-testid="stTabs"] [role="tab"] p,
        [data-testid="stTabs"] [role="tab"] span,
        [data-testid="stTabs"] [role="tab"] div,
        [data-testid="stTabs"] button[data-baseweb="tab"] *,
        [data-testid="stTabs"] button[data-baseweb="tab"] p,
        [data-testid="stTabs"] button[data-baseweb="tab"] span,
        [data-testid="stTabs"] button[data-baseweb="tab"] div {
            color: #26382F !important;
            -webkit-text-fill-color: #26382F !important;
            opacity: 1 !important;
            text-shadow: none !important;
        }

        [data-testid="stTabs"] [role="tab"][aria-selected="true"],
        [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
            color: #1F5A3A !important;
            -webkit-text-fill-color: #1F5A3A !important;
            font-weight: 750 !important;
            border-bottom: 3px solid #1F5A3A !important;
        }

        [data-testid="stTabs"] [role="tab"][aria-selected="true"] *,
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] p,
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] span,
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] div,
        [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] *,
        [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] p,
        [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] span,
        [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] div {
            color: #1F5A3A !important;
            -webkit-text-fill-color: #1F5A3A !important;
        }

        [data-testid="stTabs"] [role="tab"]:hover,
        [data-testid="stTabs"] [role="tab"]:focus-visible,
        [data-testid="stTabs"] button[data-baseweb="tab"]:hover,
        [data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {
            color: #1F5A3A !important;
            -webkit-text-fill-color: #1F5A3A !important;
        }

        [data-testid="stTabs"] [role="tab"]:hover *,
        [data-testid="stTabs"] [role="tab"]:focus-visible *,
        [data-testid="stTabs"] button[data-baseweb="tab"]:hover *,
        [data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible * {
            color: #1F5A3A !important;
            -webkit-text-fill-color: #1F5A3A !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


    st.markdown(
        """
        <style>
        .password-guidance {
            margin: .35rem 0 1rem 0;
            padding: .75rem .9rem;
            border: 1px solid #D7DED3;
            border-radius: 10px;
            background: #F5F3EA;
            color: #3F5148 !important;
            font-size: .88rem;
            line-height: 1.5;
        }
        .password-guidance strong {
            color: #1F5A3A !important;
        }
        .password-guidance ul {
            margin: .35rem 0 0 1.1rem;
            padding: 0;
        }
        .password-guidance li {
            margin: .15rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    login_tab, register_tab = st.tabs(["Sign in", "Create account"])

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Sign in",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            user = authenticate(email, password)
            if user is None:
                st.error("The email or password is incorrect.")
            else:
                st.session_state.authenticated_user = user
                st.rerun()

        st.caption(
            "Local development security uses salted PBKDF2 password hashes. "
            "Production should use an enterprise OIDC/OAuth identity provider."
        )

    with register_tab:
        # Clear only password fields after a failed password validation.
        # Name, email and account type remain filled for convenience.
        if st.session_state.pop("clear_registration_passwords", False):
            st.session_state["register_password"] = ""
            st.session_state["register_password_confirm"] = ""

        with st.form("registration_form", clear_on_submit=False):
            full_name = st.text_input("Full name")
            email = st.text_input("Email", key="register_email")
            phone = st.text_input(
                "Phone number",
                placeholder="e.g. +91 98765 43210",
                key="register_phone",
                help="Recommended for marketplace communication. Your phone number is shared only after both parties confirm a transaction.",
            )
            role = st.selectbox(
                "Account type",
                ["farmer", "buyer"],
                format_func=lambda value: value.title(),
            )
            password = st.text_input(
                "Password",
                type="password",
                key="register_password",
            )
            confirm = st.text_input(
                "Confirm password",
                type="password",
                key="register_password_confirm",
            )

            st.markdown(
                """
                <div class="password-guidance">
                    <strong>Password requirements</strong>
                    <ul>
                        <li>At least 8 characters</li>
                        <li>At least one uppercase letter (A–Z)</li>
                        <li>At least one lowercase letter (a–z)</li>
                        <li>At least one number (0–9)</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

            create = st.form_submit_button(
                "Create account",
                type="primary",
                use_container_width=True,
            )

        if create:
            if password != confirm:
                st.session_state["clear_registration_passwords"] = True
                st.session_state["registration_password_error"] = (
                    "The passwords do not match. Please enter them again."
                )
                st.rerun()

            # Validate the password requirements before attempting account creation.
            password_error = None
            if len(password) < 8:
                password_error = "Password must contain at least 8 characters."
            elif password.lower() == password or password.upper() == password:
                password_error = "Use a mix of uppercase and lowercase characters."
            elif not any(ch.isdigit() for ch in password):
                password_error = "Include at least one number in the password."

            if password_error:
                st.session_state["clear_registration_passwords"] = True
                st.session_state["registration_password_error"] = password_error
                st.rerun()

            try:
                user = create_user(full_name, email, password, role, phone)
                st.session_state.pop("registration_password_error", None)
                st.session_state.authenticated_user = user
                st.success("Account created successfully.")
                st.rerun()
            except ValueError as error:
                message = str(error)

                # Password-specific validation is handled by clearing only the
                # two password boxes. Other account fields remain untouched.
                if (
                    "password" in message.lower()
                    or "uppercase" in message.lower()
                    or "lowercase" in message.lower()
                    or "number" in message.lower()
                ):
                    st.session_state["clear_registration_passwords"] = True

                st.session_state["registration_password_error"] = message
                st.rerun()

        password_error_message = st.session_state.pop(
            "registration_password_error",
            None,
        )
        if password_error_message:
            st.error(password_error_message)
            st.markdown(
                """
                <div class="password-guidance">
                    <strong>Please check these password requirements:</strong>
                    <ul>
                        <li>At least 8 characters</li>
                        <li>At least one uppercase letter (A–Z)</li>
                        <li>At least one lowercase letter (a–z)</li>
                        <li>At least one number (0–9)</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.info(
        "Production hardening still required: email/phone verification, MFA, "
        "rate limiting, account recovery and managed identity infrastructure."
    )
    st.stop()


# ============================================================
# SESSION STATE
# ============================================================

if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None

if st.session_state.authenticated_user is None:
    render_auth_screen()

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


if "selected_crop" not in st.session_state:
    st.session_state.selected_crop = None

if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = []

if "last_report" not in st.session_state:
    st.session_state.last_report = None

if "prediction_feedback_saved" not in st.session_state:
    st.session_state.prediction_feedback_saved = False

if "marketplace_interests" not in st.session_state:
    st.session_state.marketplace_interests = []

if "farmer_listing_draft" not in st.session_state:
    st.session_state.farmer_listing_draft = None


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_crop_name(crop_name):
    """
    Convert model class names into cleaner display names.
    """

    replacements = {
        "Pearl_millet(bajra)": "Pearl Millet (Bajra)",
        "Fox_nut(Makhana)": "Fox Nut (Makhana)",
        "Coffee-plant": "Coffee Plant",
        "Olive-tree": "Olive Tree",
        "Tobacco-plant": "Tobacco Plant",
        "vigna-radiati(Mung)": "Mung Bean",
        "mustard-oil": "Mustard",
    }

    return replacements.get(
        crop_name,
        crop_name.replace("-", " ").title()
    )


def get_confidence_level(confidence):
    """
    Convert model confidence into a human-readable level.
    """

    if confidence >= 0.80:
        return "High"

    if confidence >= 0.60:
        return "Moderate"

    return "Low"


MODEL_CROP_OPTIONS = [
    "rice", "wheat", "sugarcane", "maize", "cotton", "coconut",
    "jute", "banana", "soyabean", "jowar", "Pearl_millet(bajra)",
    "Cherry", "Coffee-plant", "Cucumber", "Fox_nut(Makhana)", "Lemon",
    "Olive-tree", "Tobacco-plant", "almond", "cardamom", "chilli",
    "clove", "gram", "mustard-oil", "papaya", "pineapple", "sunflower",
    "tea", "tomato", "vigna-radiati(Mung)",
]


def get_confidence_message(confidence):
    """
    Return an appropriate message for the confidence score.
    """

    level = get_confidence_level(
        confidence
    )

    if level == "High":
        return "The model is highly confident in this prediction."

    if level == "Moderate":
        return (
            "The model has moderate confidence. "
            "Please verify the result before proceeding."
        )

    return (
        "The model has low confidence. "
        "Please verify the crop manually."
    )


def save_uploaded_image(uploaded_file):
    """
    Save a Streamlit uploaded image temporarily
    so the prediction module can process it.
    """

    suffix = Path(
        uploaded_file.name
    ).suffix.lower()

    if suffix not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
    }:
        raise ValueError(
            "Unsupported image format."
        )

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix
    ) as temporary_file:

        temporary_file.write(
            uploaded_file.getbuffer()
        )

        return temporary_file.name


def analyze_crop(crop_name):
    """
    Generate the recommendation information
    for the selected crop.
    """

    waste_info = get_waste_information(
        crop_name
    )

    recommendations = get_recommendations(
        crop_name
    )

    return (
        waste_info,
        recommendations
    )


def record_analysis(crop_name, confidence=None, source="Manual"):
    """Store a lightweight, session-only analysis history entry."""
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "crop": format_crop_name(crop_name),
        "confidence": "—" if confidence is None else f"{confidence * 100:.2f}%",
        "source": source,
    }
    if not st.session_state.analysis_history or st.session_state.analysis_history[-1] != entry:
        st.session_state.analysis_history.append(entry)
        st.session_state.analysis_history = st.session_state.analysis_history[-10:]


def make_analysis_report(crop_name, waste_info, recommendations, predictions=None, confidence=None):
    """Build a portable Markdown report for a completed analysis."""
    now = datetime.now().strftime("%d %B %Y, %I:%M %p")
    lines = [
        "# AgriWaste AI — Analysis Report",
        "",
        f"**Generated:** {now}",
        f"**Crop:** {format_crop_name(crop_name)}",
        f"**Associated residue:** {waste_info['waste_name']}",
        "",
        "## Residue insight",
        waste_info["description"],
        "",
    ]
    if confidence is not None:
        lines += [
            "## AI identification",
            f"- Top prediction: **{format_crop_name(predictions[0]['class'] if predictions else crop_name)}**",
            f"- Confidence: **{confidence * 100:.2f}%**",
            f"- Confidence level: **{get_confidence_level(confidence)}**",
            "",
        ]
        if predictions and crop_name != predictions[0]["class"]:
            lines += [
                f"- Human-corrected working identification: **{format_crop_name(crop_name)}**",
                "- The correction is user-provided and is not an independent platform verification.",
                "",
            ]
        if predictions:
            lines.append("### Top predictions")
            for rank, item in enumerate(predictions, 1):
                lines.append(f"{rank}. {format_crop_name(item['class'])} — {item['confidence'] * 100:.2f}%")
            lines.append("")
    lines.append("## Recommended utilization pathways")
    for item in sorted(recommendations, key=lambda x: x["score"], reverse=True):
        lines += [f"### {item['name']} — {item['score']}/100", item["reason"], ""]
    lines += [
        "## Important note",
        "This is an academic prototype decision-support report. Predictions, suitability scores, and economic estimates should be verified against real-world residue quality, processing requirements, logistics, local demand, and buyer conditions.",
    ]
    return "\n".join(lines)


def model_evaluation_artifacts():
    """Read available model-evaluation artifacts without inventing metrics."""
    roots = [Path("models"), Path(".")]
    report_path = next((root / "classification_report.txt" for root in roots if (root / "classification_report.txt").exists()), None)
    def artifact_path(name):
        return next((root / name for root in roots if (root / name).exists()), None)

    artifacts = {
        "report_path": report_path,
        "accuracy": None,
        "macro_precision": None,
        "macro_recall": None,
        "macro_f1": None,
        "classes": [],
        "has_model": artifact_path("agriwaste_classifier.keras") is not None or artifact_path("agriwaste_classifier.h5") is not None,
        "has_confusion": artifact_path("confusion_matrix.png") is not None,
        "confusion_path": artifact_path("confusion_matrix.png"),
        "has_accuracy_plot": artifact_path("training_accuracy.png") is not None,
        "accuracy_path": artifact_path("training_accuracy.png"),
        "has_loss_plot": artifact_path("training_loss.png") is not None,
        "loss_path": artifact_path("training_loss.png"),
    }
    if report_path is None:
        return artifacts

    text = report_path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        match = re.match(r"^\s*(.+?)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s*$", line)
        if match and match.group(1).strip() not in {"accuracy", "macro avg", "weighted avg"}:
            artifacts["classes"].append({
                "class": match.group(1).strip(),
                "precision": float(match.group(2)),
                "recall": float(match.group(3)),
                "f1": float(match.group(4)),
                "support": int(match.group(5)),
            })

    match = re.search(r"^\s*accuracy\s+([0-9.]+)", text, re.MULTILINE)
    if match:
        artifacts["accuracy"] = float(match.group(1))
    macro = re.search(r"^\s*macro avg\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", text, re.MULTILINE)
    if macro:
        artifacts["macro_precision"] = float(macro.group(1))
        artifacts["macro_recall"] = float(macro.group(2))
        artifacts["macro_f1"] = float(macro.group(3))
    return artifacts


def history_csv_bytes():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["time", "crop", "confidence", "source"])
    writer.writeheader()
    writer.writerows(st.session_state.analysis_history)
    return output.getvalue().encode("utf-8")


def style_chart(fig):
    """Apply the warm cream / forest green visual system to Plotly charts."""
    fig.update_layout(
        paper_bgcolor="#FFFCF6",
        plot_bgcolor="#FFFCF6",
        font=dict(
            family="DM Sans, sans-serif",
            color="#24332A",
        ),
        hoverlabel=dict(
            bgcolor="#285C3A",
            font_color="#FFFFFF",
        ),
        legend=dict(
            font=dict(color="#24332A"),
        ),
    )
    fig.update_xaxes(
        gridcolor="#E4E2D9",
        zerolinecolor="#D8D6CC",
        linecolor="#D8D6CC",
        tickfont=dict(color="#5F6B63"),
        title_font=dict(color="#4D5D53"),
    )
    fig.update_yaxes(
        gridcolor="#E4E2D9",
        zerolinecolor="#D8D6CC",
        linecolor="#D8D6CC",
        tickfont=dict(color="#4D5D53"),
        title_font=dict(color="#4D5D53"),
    )
    fig.update_traces(
        marker_color="#285C3A",
        textfont=dict(color="#24332A"),
    )
    return fig


# ============================================================
# FARMER LANGUAGE SUPPORT
# ============================================================

LANGUAGE_LABELS = {
    "English": "English",
    "Hindi": "हिन्दी",
    "Odia": "ଓଡ଼ିଆ",
    "Bengali": "বাংলা",
}

TRANSLATIONS = {
    "Hindi": {
        "Dashboard": "डैशबोर्ड",
        "Waste Analysis": "कचरा विश्लेषण",
        "Recommendations": "उपयोग सुझाव",
        "Potential Utilizers": "संभावित खरीदार/उपयोगकर्ता",
        "Economic Value": "संभावित आर्थिक मूल्य",
        "Farmer Dashboard": "मेरे अवशेष लॉट",
        "Lot Quality & Evidence": "लॉट गुणवत्ता और फोटो",
        "Marketplace": "अवशेष बेचें",
        "Find Buyers": "खरीदार खोजें",
        "Buyer Requests": "खरीदार की मांग",
        "Transactions": "बातचीत और बिक्री",
        "Preparation Guide": "तैयारी गाइड",
        "About Project": "प्रोजेक्ट के बारे में",
        "Buyer Portal": "खरीदार पोर्टल",
        "Language": "भाषा",
        "Navigation": "नेविगेशन",
        "Farmer mode": "किसान मोड",
        "Upload a photo of your agricultural residue": "अपने कृषि अवशेष की फोटो अपलोड करें",
        "AI identification": "AI पहचान",
        "Top 3 predictions": "शीर्ष 3 अनुमान",
        "Does the AI prediction look correct?": "क्या AI की पहचान सही लगती है?",
        "Use AI prediction": "AI की पहचान उपयोग करें",
        "Save correction": "सुधार सेव करें",
    },
    "Odia": {
        "Dashboard": "ଡ୍ୟାସବୋର୍ଡ",
        "Waste Analysis": "ଅବଶିଷ୍ଟ ବିଶ୍ଳେଷଣ",
        "Recommendations": "ବ୍ୟବହାର ପରାମର୍ଶ",
        "Potential Utilizers": "ସମ୍ଭାବ୍ୟ ବ୍ୟବହାରକାରୀ",
        "Economic Value": "ସମ୍ଭାବ୍ୟ ଆର୍ଥିକ ମୂଲ୍ୟ",
        "Farmer Dashboard": "ମୋର ଅବଶିଷ୍ଟ ଲଟ୍",
        "Lot Quality & Evidence": "ଲଟ୍ ଗୁଣବତ୍ତା ଓ ଫଟୋ",
        "Marketplace": "ଅବଶିଷ୍ଟ ବିକ୍ରି କରନ୍ତୁ",
        "Find Buyers": "କ୍ରେତା ଖୋଜନ୍ତୁ",
        "Buyer Requests": "କ୍ରେତାଙ୍କ ଚାହିଦା",
        "Transactions": "ଆଲୋଚନା ଓ ବିକ୍ରି",
        "Preparation Guide": "ପ୍ରସ୍ତୁତି ଗାଇଡ୍",
        "About Project": "ପ୍ରକଳ୍ପ ବିଷୟରେ",
        "Buyer Portal": "କ୍ରେତା ପୋର୍ଟାଲ୍",
        "Language": "ଭାଷା",
        "Navigation": "ନେଭିଗେସନ୍",
        "Farmer mode": "ଚାଷୀ ମୋଡ୍",
        "Upload a photo of your agricultural residue": "ଆପଣଙ୍କ କୃଷି ଅବଶିଷ୍ଟର ଫଟୋ ଅପଲୋଡ୍ କରନ୍ତୁ",
        "AI identification": "AI ଚିହ୍ନଟ",
        "Top 3 predictions": "ଶୀର୍ଷ 3 ଅନୁମାନ",
        "Does the AI prediction look correct?": "AI ଚିହ୍ନଟ ସଠିକ୍ ଲାଗୁଛି କି?",
        "Use AI prediction": "AI ଚିହ୍ନଟ ବ୍ୟବହାର କରନ୍ତୁ",
        "Save correction": "ସଂଶୋଧନ ସେଭ୍ କରନ୍ତୁ",
    },
    "Bengali": {
        "Dashboard": "ড্যাশবোর্ড",
        "Waste Analysis": "বর্জ্য বিশ্লেষণ",
        "Recommendations": "ব্যবহারের পরামর্শ",
        "Potential Utilizers": "সম্ভাব্য ব্যবহারকারী",
        "Economic Value": "সম্ভাব্য অর্থনৈতিক মূল্য",
        "Farmer Dashboard": "আমার অবশিষ্ট লট",
        "Lot Quality & Evidence": "লটের গুণমান ও ছবি",
        "Marketplace": "অবশিষ্ট বিক্রি করুন",
        "Find Buyers": "ক্রেতা খুঁজুন",
        "Buyer Requests": "ক্রেতার চাহিদা",
        "Transactions": "আলোচনা ও বিক্রি",
        "Preparation Guide": "প্রস্তুতি গাইড",
        "About Project": "প্রকল্প সম্পর্কে",
        "Buyer Portal": "ক্রেতা পোর্টাল",
        "Language": "ভাষা",
        "Navigation": "নেভিগেশন",
        "Farmer mode": "কৃষক মোড",
        "Upload a photo of your agricultural residue": "আপনার কৃষি অবশিষ্টের ছবি আপলোড করুন",
        "AI identification": "AI শনাক্তকরণ",
        "Top 3 predictions": "শীর্ষ ৩ অনুমান",
        "Does the AI prediction look correct?": "AI-এর শনাক্তকরণ কি সঠিক মনে হচ্ছে?",
        "Use AI prediction": "AI শনাক্তকরণ ব্যবহার করুন",
        "Save correction": "সংশোধন সংরক্ষণ করুন",
    },
}

def t(text: str) -> str:
    language = st.session_state.get("ui_language", "English")
    return TRANSLATIONS.get(language, {}).get(text, text)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        """
        <div style="padding:.35rem .15rem .5rem .15rem;">
            <div style="font-family:Fraunces, Georgia, serif; font-size:1.55rem; font-weight:700; color:#285C3A;">
                🌾 AgriWaste AI
            </div>
            <div style="margin-top:.35rem; color:#6C756E; font-size:.88rem; line-height:1.45;">
                Agricultural Waste<br>Intelligence Platform
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    user = current_user()

    # Farmer-facing language selector. English remains the default so existing
    # technical/project content stays unchanged unless the user selects a language.
    selected_language = st.selectbox(
        t("Language"),
        list(LANGUAGE_LABELS.keys()),
        format_func=lambda x: LANGUAGE_LABELS[x],
        key="ui_language_selector",
    )
    st.session_state["ui_language"] = selected_language

    # Navigation is ordered around the farmer's natural workflow:
    # understand the residue → evaluate options → manage/sell it → prepare it.
    if user["role"] == "farmer":
        nav_options = {
            "Dashboard": "🏠  Dashboard",
            "Waste Analysis": "🔍  Waste Analysis",
            "Recommendations": "♻️  Recommendations",
            "Potential Utilizers": "👥  Potential Utilizers",
            "Economic Value": "₹  Economic Value",
            "Farmer Dashboard": "📋  My Residue Lots",
            "Lot Quality & Evidence": "🧪  Lot Quality & Evidence",
            "Marketplace": "🤝  Sell Residue",
            "Find Buyers": "🎯  Find Buyers",
            "Buyer Requests": "📨  Buyer Requests",
            "Transactions": "🤝  Negotiations & Sales",
            "Preparation Guide": "🧰  Preparation Guide",
            "About Project": "ⓘ  About Project",
        }
    elif user["role"] == "buyer":
        nav_options = {
            "Dashboard": "🏠  Dashboard",
            "Buyer Portal": "🏭  Buyer Portal",
            "Transactions": "🤝  Negotiations & Sales",
            "Waste Analysis": "🔍  Waste Analysis",
            "Recommendations": "♻️  Recommendations",
            "Potential Utilizers": "👥  Potential Utilizers",
            "Economic Value": "₹  Economic Value",
            "About Project": "ⓘ  About Project",
        }
    else:
        nav_options = {
            **common_nav,
        }

    # Translate only the farmer-facing navigation labels; internal page keys remain stable.
    translated_nav_options = {
        name: label.replace(name, t(name), 1) if t(name) != name else label
        for name, label in nav_options.items()
    }
    nav_values = list(translated_nav_options.values())
    default_nav = translated_nav_options["Dashboard"]
    if st.session_state.get("main_navigation") not in nav_values:
        st.session_state["main_navigation"] = default_nav

    selected_nav = st.radio(
        t("Navigation"),
        nav_values,
        index=nav_values.index(st.session_state["main_navigation"]),
        key="main_navigation",
    )

    def go_to_page(target_page: str) -> None:
        """Switch the main navigation safely from dashboard/action buttons."""
        target_label = translated_nav_options.get(target_page)
        if target_label:
            st.session_state["main_navigation"] = target_label
        st.rerun()
    page = next(
        name for name, label in translated_nav_options.items()
        if label == selected_nav
    )

    st.divider()

    st.caption(
        "Industry Prototype · v0.6"
    )
    st.markdown(
        '<span style="display:inline-block;padding:.28rem .62rem;border-radius:999px;background:#EAF0E5;color:#285C3A;font-size:.72rem;font-weight:700;border:1px solid #CBD8C3;">Industry Prototype</span>',
        unsafe_allow_html=True,
    )


# ============================================================
# DASHBOARD
# ============================================================

if page == "Dashboard":

    hero_left, hero_right = st.columns([1.18, 0.82], gap="large")

    with hero_left:
        st.markdown(
            """
            <div class="hero-wrap">
                <div class="eyebrow">Agricultural Waste Intelligence Platform</div>
                <div class="hero-main-title">Turn agricultural<br>waste into value.</div>
                <div class="hero-copy">
                    Identify crop residues, discover practical utilization pathways,
                    connect waste with potential industries, and estimate its
                    prototype economic potential — all in one workflow.
                </div>
                <div class="hero-pill">AI-assisted • Data-driven • Industry Prototype</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with hero_right:
        hero_image = ImageEnhance.Color(
            ImageEnhance.Contrast(
                ImageEnhance.Brightness(
                    Image.open("assets/hero_agriculture.png").convert("RGB")
                ).enhance(0.88)
            ).enhance(0.92)
        ).enhance(0.68)
        st.image(hero_image, use_container_width=True)
        st.markdown(
            '<div class="image-caption">From agricultural residue to opportunity</div>',
            unsafe_allow_html=True,
        )

    stat1, stat2, stat3, stat4 = st.columns(4)
    stats = [
        ("30+", "Crop classes supported"),
        ("3", "Core AI workflow stages"),
        ("5", "Utilization pathways"),
        ("1", "Integrated platform"),
    ]
    for col, (value, label) in zip([stat1, stat2, stat3, stat4], stats):
        with col:
            st.markdown(
                f'<div class="stat-card"><div class="stat-value">{value}</div><div class="stat-label">{label}</div></div>',
                unsafe_allow_html=True,
            )

    # ---------------------------------------------------------
    # Role-aware workspace snapshot
    # ---------------------------------------------------------
    current_role = current_user()["role"]
    if current_role == "farmer":
        farmer_dash = get_farmer_dashboard(current_user()["user_id"])
        farmer_all = farmer_dash.get("listings", [])
        farmer_active = [
            item for item in farmer_all
            if item.get("status") not in {"Sold", "Cancelled"}
            and float(item.get("quantity_kg") or 0) > 0
        ]
        farmer_active_count = sum(
            1 for item in farmer_active
            if item.get("status") in {"Published", "Under Review", "Negotiation", "Reserved"}
        )
        farmer_completed = sum(1 for item in farmer_all if item.get("status") == "Sold")

        st.markdown('<div class="section-kicker">Your workspace</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">What would you like to do?</div>', unsafe_allow_html=True)

        qa = st.columns(4, gap="medium")
        quick_actions = [
            (qa[0], "Analyze waste", "Identify a crop residue from a photo.", "Waste Analysis"),
            (qa[1], "Sell residue", "Create and publish a buyer-ready lot.", "Marketplace"),
            (qa[2], "Find buyers", "Compare your lots with open buyer requests.", "Find Buyers"),
            (qa[3], "My lots", "Track quantity, status and lot history.", "Farmer Dashboard"),
        ]
        for col, title, description, target in quick_actions:
            with col:
                st.markdown(
                    f'''<div class="quick-action-card">
                        <div class="quick-action-title">{title}</div>
                        <div class="quick-action-text">{description}</div>
                    </div>''',
                    unsafe_allow_html=True,
                )
                if st.button("Open", key=f"dashboard_action_{target}", use_container_width=True):
                    go_to_page(target)

        sm1, sm2, sm3 = st.columns(3, gap="medium")
        with sm1:
            st.markdown(f'''<div class="mini-summary-card"><span class="mini-summary-label">Active lots</span><span class="mini-summary-value">{farmer_active_count}</span></div>''', unsafe_allow_html=True)
        with sm2:
            st.markdown(f'''<div class="mini-summary-card"><span class="mini-summary-label">Available inventory</span><span class="mini-summary-value">{sum(float(x.get("quantity_kg") or 0) for x in farmer_active):,.0f} kg</span></div>''', unsafe_allow_html=True)
        with sm3:
            st.markdown(f'''<div class="mini-summary-card"><span class="mini-summary-label">Completed sales</span><span class="mini-summary-value">{farmer_completed}</span></div>''', unsafe_allow_html=True)

    elif current_role == "buyer":
        buyer = current_user()
        buyer_rfqs = get_buyer_rfqs(buyer["user_id"])
        buyer_deals = get_deals_for_buyer(buyer["user_id"])
        open_rfqs = sum(1 for item in buyer_rfqs if item.get("status") == "Open")
        active_deals = sum(1 for item in buyer_deals if item.get("status") not in {"Completed", "Cancelled"})
        completed_deals = sum(1 for item in buyer_deals if item.get("status") == "Completed")

        st.markdown('<div class="section-kicker">Buyer workspace</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Manage your residue sourcing</div>', unsafe_allow_html=True)

        qa = st.columns(3, gap="medium")
        quick_actions = [
            (qa[0], "Create buyer request", "Tell farmers exactly what material you need.", "Buyer Portal"),
            (qa[1], "Review negotiations", "Compare responses and continue active deals.", "Transactions"),
            (qa[2], "Analyze residue", "Explore crop residue information and uses.", "Waste Analysis"),
        ]
        for col, title, description, target in quick_actions:
            with col:
                st.markdown(
                    f'''<div class="quick-action-card">
                        <div class="quick-action-title">{title}</div>
                        <div class="quick-action-text">{description}</div>
                    </div>''',
                    unsafe_allow_html=True,
                )
                if st.button("Open", key=f"dashboard_action_{target}", use_container_width=True):
                    go_to_page(target)

        sm1, sm2, sm3 = st.columns(3, gap="medium")
        with sm1:
            st.markdown(f'''<div class="mini-summary-card"><span class="mini-summary-label">Open requests</span><span class="mini-summary-value">{open_rfqs}</span></div>''', unsafe_allow_html=True)
        with sm2:
            st.markdown(f'''<div class="mini-summary-card"><span class="mini-summary-label">Active deals</span><span class="mini-summary-value">{active_deals}</span></div>''', unsafe_allow_html=True)
        with sm3:
            st.markdown(f'''<div class="mini-summary-card"><span class="mini-summary-label">Completed purchases</span><span class="mini-summary-value">{completed_deals}</span></div>''', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="section-kicker">The workflow</div>', unsafe_allow_html=True)
    st.header("From crop image to actionable insight")
    st.caption("A simple three-stage pipeline designed to make agricultural residue information easier to understand and act on.")

    col1, col2, col3 = st.columns(3, gap="medium")
    features = [
        (col1, "01", "🔍", "Identify", "Upload a crop image and use the EfficientNetB0-based classifier to identify the crop source."),
        (col2, "02", "♻️", "Recommend", "Map the identified crop to agricultural residue uses and rank suitable utilization pathways."),
        (col3, "03", "₹", "Value", "Estimate potential gross value and identify categories of organizations that may utilize the residue."),
    ]
    for col, number, icon, title, text in features:
        with col:
            st.markdown(
                f"""<div class="feature-card">
                    <div class="feature-number">STEP {number}</div>
                    <div class="feature-icon">{icon}</div>
                    <div class="feature-title">{title}</div>
                    <div class="feature-text">{text}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.write("")
    st.divider()

    st.markdown('<div class="section-kicker">Visual overview</div>', unsafe_allow_html=True)
    st.header("A circular path from waste to opportunity")
    st.caption("The prototype combines residue identification with utilization and value-oriented decision support.")

    visual_left, visual_right = st.columns(2, gap="large")
    with visual_left:
        st.image("assets/waste_cycle.png", use_container_width=True)
        st.markdown('<div class="image-caption">Agricultural waste utilization cycle</div>', unsafe_allow_html=True)
    with visual_right:
        st.image("assets/value_chain.png", use_container_width=True)
        st.markdown('<div class="image-caption">From residue to potential value</div>', unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="section-kicker">What is inside</div>', unsafe_allow_html=True)
    st.header("Prototype capabilities")
    capability_cols = st.columns(2, gap="large")
    capabilities_left = [
        "Computer vision based crop identification",
        "Agricultural residue mapping",
        "Waste utilization recommendations",
        "Suitability scoring",
    ]
    capabilities_right = [
        "Economic value estimation",
        "Potential industry/utilizer matching",
        "AI-assisted explanations",
        "Interactive visual analytics",
    ]
    with capability_cols[0]:
        for item in capabilities_left:
            st.markdown(f"- {item}")
    with capability_cols[1]:
        for item in capabilities_right:
            st.markdown(f"- {item}")

    st.write("")
    st.divider()
    st.markdown('<div class="section-kicker">Session activity</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Recent analyses</div>', unsafe_allow_html=True)
    st.caption("Recent analyses are kept only for this browser session; uploaded images are not stored by this history view.")

    if st.session_state.analysis_history:
        for item in reversed(st.session_state.analysis_history[-5:]):
            crop = item["crop"]
            confidence_text = item["confidence"]
            source = item["source"]
            timestamp = item["time"]
            st.markdown(
                f'<div class="history-card"><strong>{crop}</strong> · {confidence_text} <span class="source-tag">{source}</span><br><span style="opacity:.58;font-size:12px;">{timestamp}</span></div>',
                unsafe_allow_html=True,
            )
        st.download_button(
            "Export Session History (CSV)",
            data=history_csv_bytes(),
            file_name="agriwaste_analysis_history.csv",
            mime="text/csv",
        )
    else:
        st.caption("No analyses recorded in this session yet.")

    st.info(
        "AgriWaste AI is currently an academic prototype. Model predictions, "
        "suitability scores and economic estimates should be treated as decision-support "
        "outputs and verified before real-world use."
    )


# ============================================================
# WASTE ANALYSIS
# ============================================================

elif page == "Waste Analysis":

    st.markdown(
        """
        <div class="analysis-hero">
            <div class="analysis-kicker">AI-powered crop identification</div>
            <div class="analysis-title">Understand your agricultural waste.</div>
            <div class="analysis-copy">
                Upload a crop image or select a crop manually to identify its source,
                discover the associated residue, and explore practical utilization pathways.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    input_method = st.radio(
        "Identification method",
        ["Upload Image", "Manual Selection"],
        horizontal=True,
    )

    # ------------------------------------------------------------
    # IMAGE MODE
    # ------------------------------------------------------------

    if input_method == "Upload Image":

        uploaded_file = st.file_uploader(
            "Upload an agricultural image",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            help="For best results, use a clear image with the crop clearly visible.",
        )

        if uploaded_file is None:
            st.markdown(
                """
                <div class="upload-card">
                    <div class="analysis-kicker">Step 01 · Identify</div>
                    <h3>Upload a crop image</h3>
                    <p style="opacity:.72; line-height:1.6;">
                        Choose a clear image of the crop. The EfficientNetB0-based
                        classifier will return the top predictions and confidence scores.
                    </p>
                    <div class="manual-note">
                        Supported formats: JPG, JPEG, PNG, BMP and WEBP
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if uploaded_file is not None:

            image_col, result_col = st.columns([0.95, 1.05], gap="large")

            with image_col:
                st.markdown(
                    '<div class="analysis-kicker">Step 01 · Input image</div>',
                    unsafe_allow_html=True,
                )
                st.image(
                    uploaded_file,
                    caption="Uploaded crop image",
                    use_container_width=True,
                )

            with result_col:
                st.markdown(
                    """
                    <div class="upload-card">
                        <div class="analysis-kicker">Step 02 · AI analysis</div>
                        <h3>Ready to identify the crop</h3>
                        <p style="opacity:.72; line-height:1.55;">
                            Run the model to identify the crop and estimate its confidence.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    "Analyze Image",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        temporary_path = save_uploaded_image(uploaded_file)

                        with st.spinner("AI model is analyzing the image..."):
                            predictions = predict_image(
                                temporary_path,
                                top_k=3,
                            )

                        best_prediction = predictions[0]

                        st.session_state.analysis_result = {
                            "predictions": predictions,
                            "best_prediction": best_prediction,
                        }
                        st.session_state.selected_crop = best_prediction["class"]
                        record_analysis(
                            best_prediction["class"],
                            confidence=best_prediction["confidence"],
                            source="AI image",
                        )

                        st.success("Image analysis completed.")

                    except Exception as error:
                        st.error(f"Unable to analyze image: {error}")

            # ----------------------------------------------------
            # DISPLAY PREDICTION
            # ----------------------------------------------------

            result = st.session_state.analysis_result

            if result is not None:

                best_prediction = result["best_prediction"]
                crop_name = result.get("working_crop", best_prediction["class"])
                confidence = best_prediction["confidence"]
                confidence_pct = confidence * 100
                confidence_level = get_confidence_level(confidence)

                st.divider()

                st.markdown(
                    '<div class="analysis-kicker">Step 02 · Identification result</div>',
                    unsafe_allow_html=True,
                )
                st.header(t("AI identification"))

                col1, col2, col3 = st.columns(3, gap="medium")

                with col1:
                    st.markdown(
                        f"""
                        <div class="result-card">
                            <div class="result-kicker">Detected crop</div>
                            <div class="result-value">{format_crop_name(crop_name)}</div>
                            <div class="result-small">Top model prediction</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col2:
                    st.markdown(
                        f"""
                        <div class="result-card">
                            <div class="result-kicker">Confidence</div>
                            <div class="result-value">{confidence_pct:.2f}%</div>
                            <div class="confidence-track">
                                <div class="confidence-fill" style="width:{min(confidence_pct, 100):.2f}%"></div>
                            </div>
                            <div class="result-small">{confidence_level} confidence</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col3:
                    st.markdown(
                        f"""
                        <div class="result-card">
                            <div class="result-kicker">Decision status</div>
                            <div class="result-value">{confidence_level}</div>
                            <div class="result-small">
                                {"Suitable to continue with verification." if confidence >= 0.80 else "Verify the crop before relying on downstream results."}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                if confidence >= 0.80:
                    st.success(get_confidence_message(confidence))
                elif confidence >= 0.60:
                    st.warning(get_confidence_message(confidence))
                else:
                    st.error(get_confidence_message(confidence))

                st.subheader(t("Top 3 predictions"))

                prediction_data = {
                    "Crop": [
                        format_crop_name(item["class"])
                        for item in result["predictions"]
                    ],
                    "Confidence": [
                        item["confidence"] * 100
                        for item in result["predictions"]
                    ],
                }

                chart = px.bar(
                    prediction_data,
                    x="Confidence",
                    y="Crop",
                    orientation="h",
                    text="Confidence",
                )

                chart.update_traces(
                    texttemplate="%{text:.2f}%",
                    textposition="outside",
                )

                chart.update_layout(
                    xaxis_title="Confidence (%)",
                    yaxis_title="",
                    xaxis_range=[0, 100],
                    height=300,
                    margin=dict(l=10, r=30, t=20, b=20),
                )

                st.plotly_chart(
                    chart,
                    use_container_width=True,
                )

                # ------------------------------------------------
                # HUMAN VERIFICATION / CORRECTION
                # ------------------------------------------------
                st.divider()
                st.markdown(
                    '<div class="analysis-kicker">Step 02A · Human verification</div>',
                    unsafe_allow_html=True,
                )
                st.subheader(t("Does the AI prediction look correct?"))
                st.caption(
                    "The original AI prediction and confidence are preserved. "
                    "If you know the crop is different, select the correct crop below. "
                    "Your correction is treated as a working identification for the rest of this analysis."
                )

                correction_options = MODEL_CROP_OPTIONS
                current_index = correction_options.index(best_prediction["class"]) if best_prediction["class"] in correction_options else 0
                corrected_crop = st.selectbox(
                    "Crop identification",
                    correction_options,
                    index=current_index,
                    format_func=format_crop_name,
                    key="ai_correction_crop",
                )
                correction_notes = st.text_input(
                    "Optional note",
                    placeholder="Example: Image contains mature rice straw, not wheat.",
                    key="ai_correction_notes",
                )

                verify_col1, verify_col2 = st.columns(2, gap="medium")
                with verify_col1:
                    if st.button(t("Use AI prediction"), use_container_width=True):
                        result["working_crop"] = best_prediction["class"]
                        st.session_state.selected_crop = best_prediction["class"]
                        st.session_state.prediction_feedback_saved = False
                        st.rerun()
                with verify_col2:
                    if st.button(t("Save correction"), type="primary", use_container_width=True):
                        try:
                            feedback_id = save_prediction_feedback(
                                ai_prediction=best_prediction["class"],
                                ai_confidence=best_prediction["confidence"],
                                corrected_crop=corrected_crop,
                                notes=correction_notes,
                                actor_id=str(current_user().get("user_id", "DEMO-FARMER-001")),
                            )
                            result["working_crop"] = corrected_crop
                            result["correction"] = {
                                "feedback_id": feedback_id,
                                "corrected_crop": corrected_crop,
                            }
                            st.session_state.selected_crop = corrected_crop
                            st.session_state.prediction_feedback_saved = True
                            st.rerun()
                        except Exception as error:
                            st.error(f"Unable to save correction: {error}")

                if result.get("correction"):
                    st.success(
                        f"Working identification updated to {format_crop_name(result['correction']['corrected_crop'])}. "
                        "The original AI prediction remains recorded separately."
                    )
                elif best_prediction["class"] == corrected_crop:
                    st.info("The selected crop matches the AI prediction. You can continue with the model result.")

                # ------------------------------------------------
                # RESIDUE INFORMATION
                # ------------------------------------------------

                waste_info, recommendations = analyze_crop(crop_name)

                st.divider()

                st.markdown(
                    '<div class="analysis-kicker">Step 03 · Residue insight</div>',
                    unsafe_allow_html=True,
                )
                st.header("What residue does this crop generate?")

                st.markdown(
                    f"""
                    <div class="residue-card">
                        <div class="analysis-kicker">Associated agricultural residue</div>
                        <div class="residue-name">{waste_info["waste_name"]}</div>
                        <div style="opacity:.78; line-height:1.6;">
                            {waste_info["description"]}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.subheader("Recommended utilization pathways")

                for recommendation in recommendations:
                    st.markdown(
                        f"""
                        <div class="pathway-card">
                            <div class="pathway-name">{recommendation["name"]}</div>
                            <div class="pathway-score">
                                Suitability Score: <strong>{recommendation["score"]}/100</strong>
                            </div>
                            <div style="opacity:.78; line-height:1.55;">
                                {recommendation["reason"]}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.info(
                    "Next step: use Recommendations for detailed pathway comparison, "
                    "Potential Utilizers to explore relevant organization categories, "
                    "and Economic Value to estimate prototype gross value."
                )

                st.session_state.last_report = make_analysis_report(
                    crop_name, waste_info, recommendations,
                    predictions=result["predictions"], confidence=confidence,
                )
                st.download_button(
                    "Download Analysis Report",
                    data=st.session_state.last_report,
                    file_name=f"agriwaste_{crop_name.lower().replace(' ', '_')}_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    # ------------------------------------------------------------
    # MANUAL MODE
    # ------------------------------------------------------------

    else:

        st.markdown(
            """
            <div class="upload-card">
                <div class="analysis-kicker">Alternative input</div>
                <h3>Select a crop manually</h3>
                <p style="opacity:.72; line-height:1.55;">
                    Use this mode when an image is unavailable or when you want to
                    inspect a known crop directly.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        crop_options = [
            "rice",
            "wheat",
            "sugarcane",
            "maize",
            "cotton",
            "coconut",
            "jute",
            "banana",
            "soyabean",
            "jowar",
            "Pearl_millet(bajra)",
            "Cherry",
            "Coffee-plant",
            "Cucumber",
            "Fox_nut(Makhana)",
            "Lemon",
            "Olive-tree",
            "Tobacco-plant",
            "almond",
            "cardamom",
            "chilli",
            "clove",
            "gram",
            "mustard-oil",
            "papaya",
            "pineapple",
            "sunflower",
            "tea",
            "tomato",
            "vigna-radiati(Mung)",
        ]

        selected_crop = st.selectbox(
            "Select crop",
            crop_options,
            format_func=format_crop_name,
        )

        if st.button(
            "Analyze Selected Crop",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.selected_crop = selected_crop
            st.session_state.analysis_result = None
            record_analysis(selected_crop, source="Manual")

        if st.session_state.selected_crop:

            crop_name = st.session_state.selected_crop
            waste_info, recommendations = analyze_crop(crop_name)

            st.divider()

            st.markdown(
                '<div class="analysis-kicker">Identification result</div>',
                unsafe_allow_html=True,
            )
            st.header("Crop & residue overview")

            col1, col2 = st.columns(2, gap="medium")

            with col1:
                st.markdown(
                    f"""
                    <div class="result-card">
                        <div class="result-kicker">Selected crop</div>
                        <div class="result-value">{format_crop_name(crop_name)}</div>
                        <div class="result-small">Manual identification</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col2:
                st.markdown(
                    f"""
                    <div class="result-card">
                        <div class="result-kicker">Associated residue</div>
                        <div class="result-value">{waste_info["waste_name"]}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"""
                <div class="residue-card">
                    <div class="analysis-kicker">Residue insight</div>
                    <div style="opacity:.82; line-height:1.6;">
                        {waste_info["description"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.subheader("Recommended utilization pathways")

            for recommendation in recommendations:
                st.markdown(
                    f"""
                    <div class="pathway-card">
                        <div class="pathway-name">{recommendation["name"]}</div>
                        <div class="pathway-score">
                            Suitability Score: <strong>{recommendation["score"]}/100</strong>
                        </div>
                        <div style="opacity:.78; line-height:1.55;">
                            {recommendation["reason"]}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.info(
                "Manual selection bypasses image classification and directly uses "
                "the crop-to-residue knowledge base."
            )

            st.download_button(
                "Download Analysis Report",
                data=make_analysis_report(crop_name, waste_info, recommendations),
                file_name=f"agriwaste_{crop_name.lower().replace(' ', '_')}_report.md",
                mime="text/markdown",
                use_container_width=True,
            )


# ============================================================
# RECOMMENDATIONS
# ============================================================

elif page == "Recommendations":

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Decision support · Step 02</div>
            <div class="page-title">Find the best use for agricultural residue.</div>
            <div class="page-copy">
                Compare practical utilization pathways, understand their suitability,
                and see why each pathway may be appropriate for the selected crop residue.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    crop_options = [
        "rice",
        "wheat",
        "sugarcane",
        "maize",
        "cotton",
        "coconut",
        "jute",
        "banana",
        "soyabean",
        "jowar",
        "Pearl_millet(bajra)",
    ]

    selected_crop = st.selectbox(
        "Select crop",
        crop_options,
        format_func=format_crop_name,
    )

    waste_info, recommendations = analyze_crop(selected_crop)

    st.markdown(
        f"""
        <div class="context-card">
            <div class="context-label">Selected crop · associated residue</div>
            <div class="context-value">{format_crop_name(selected_crop)} · {waste_info["waste_name"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if recommendations:
        best = max(recommendations, key=lambda item: item["score"])
        avg_score = sum(item["score"] for item in recommendations) / len(recommendations)

        m1, m2, m3 = st.columns(3, gap="medium")
        with m1:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Top pathway</div>
                    <div class="metric-value">{best["name"]}</div>
                    <div class="metric-note">Highest suitability</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Best score</div>
                    <div class="metric-value">{best["score"]}/100</div>
                    <div class="metric-note">Suitability score</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Pathways compared</div>
                    <div class="metric-value">{len(recommendations)}</div>
                    <div class="metric-note">Average: {avg_score:.0f}/100</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.write("")
        st.markdown('<div class="section-kicker">Pathway comparison</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Suitability at a glance</div>', unsafe_allow_html=True)
        st.caption("Higher scores indicate a stronger fit within the prototype knowledge base.")

        chart_data = {
            "Application": [item["name"] for item in recommendations],
            "Suitability": [item["score"] for item in recommendations],
        }

        chart = px.bar(
            chart_data,
            x="Suitability",
            y="Application",
            orientation="h",
            text="Suitability",
        )
        chart.update_traces(
            texttemplate="%{text}/100",
            textposition="outside",
        )
        chart.update_layout(
            xaxis_title="Suitability Score",
            yaxis_title="",
            xaxis_range=[0, 100],
            height=max(330, 75 * len(recommendations)),
            margin=dict(l=10, r=35, t=20, b=20),
        )
        style_chart(chart)
        st.plotly_chart(chart, use_container_width=True)

        st.markdown('<div class="section-heading">Why these pathways?</div>', unsafe_allow_html=True)
        st.caption("Review the reasoning behind each recommendation.")

        for recommendation in sorted(recommendations, key=lambda item: item["score"], reverse=True):
            score = max(0, min(100, recommendation["score"]))
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="score-top">
                        <div class="score-name">{recommendation["name"]}</div>
                        <div class="score-number">{recommendation["score"]}/100</div>
                    </div>
                    <div class="score-track">
                        <div class="score-fill" style="width:{score}%"></div>
                    </div>
                    <div class="score-reason">{recommendation["reason"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.info(
            "These recommendations are prototype decision-support outputs. "
            "Actual suitability depends on residue quality, processing requirements, "
            "logistics and local demand."
        )

# ============================================================
# POTENTIAL UTILIZERS
# ============================================================

elif page == "Potential Utilizers":

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Market connection · Step 03</div>
            <div class="page-title">Discover who could use this residue.</div>
            <div class="page-copy">
                Explore organization and industry categories that may be able to
                utilize the identified agricultural residue, ranked by prototype match score.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    crop_options = [
        "rice", "wheat", "sugarcane", "maize", "cotton", "coconut",
        "jute", "banana", "soyabean", "jowar", "Pearl_millet(bajra)"
    ]

    selected_crop = st.selectbox(
        "Select crop",
        crop_options,
        format_func=format_crop_name,
    )

    waste_info, recommendations = analyze_crop(selected_crop)
    utilizers = get_utilizers(selected_crop)

    st.markdown(
        f"""
        <div class="context-card">
            <div class="context-label">Selected crop · associated residue</div>
            <div class="context-value">{format_crop_name(selected_crop)} · {waste_info["waste_name"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if utilizers:
        top = max(utilizers, key=lambda item: item["score"])
        average = sum(item["score"] for item in utilizers) / len(utilizers)

        c1, c2, c3 = st.columns(3, gap="medium")
        with c1:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Top match</div>
                    <div class="metric-value">{top["name"]}</div>
                    <div class="metric-note">Highest-ranked utilizer</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Match score</div>
                    <div class="metric-value">{top["score"]}/100</div>
                    <div class="metric-note">Prototype ranking</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Categories</div>
                    <div class="metric-value">{len(utilizers)}</div>
                    <div class="metric-note">Average match: {average:.0f}/100</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.write("")
        st.markdown('<div class="section-kicker">Potential industry matches</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-heading">Ranked utilization partners</div>', unsafe_allow_html=True)

        for rank, utilizer in enumerate(sorted(utilizers, key=lambda item: item["score"], reverse=True), start=1):
            score = max(0, min(100, utilizer["score"]))
            st.markdown(
                f"""
                <div class="utilizer-card">
                    <div class="score-top">
                        <div class="score-name">{rank}. {utilizer["name"]}</div>
                        <div class="score-number">{utilizer["score"]}/100</div>
                    </div>
                    <div class="score-track">
                        <div class="score-fill" style="width:{score}%"></div>
                    </div>
                    <div class="utilizer-badge">{utilizer["type"]}</div>
                    <div class="score-reason" style="margin-top:.55rem;">{utilizer["reason"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('<div class="section-heading">Match overview</div>', unsafe_allow_html=True)
        st.caption("A visual comparison of prototype match scores across potential utilizer categories.")

        utilizer_chart_data = {
            "Utilizer": [item["name"] for item in utilizers],
            "Match Score": [item["score"] for item in utilizers],
        }

        utilizer_chart = px.bar(
            utilizer_chart_data,
            x="Match Score",
            y="Utilizer",
            orientation="h",
            text="Match Score",
        )
        utilizer_chart.update_traces(
            texttemplate="%{text}/100",
            textposition="outside",
        )
        utilizer_chart.update_layout(
            xaxis_title="Match Score",
            yaxis_title="",
            xaxis_range=[0, 100],
            height=max(330, 75 * len(utilizers)),
            margin=dict(l=10, r=35, t=20, b=20),
        )
        style_chart(utilizer_chart)
        st.plotly_chart(utilizer_chart, use_container_width=True)

        st.info(
            "These are potential utilizer categories, not confirmed buyers or live marketplace listings. "
            "Actual suitability depends on quality, quantity, logistics, processing requirements and local demand."
        )
    else:
        st.warning("No potential utilizers are currently available for this crop.")

# ============================================================
# MARKETPLACE
# ============================================================

elif page == "Farmer Dashboard":

    require_role("farmer")

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Farmer workspace · Step 04A</div>
            <div class="page-title">Manage every residue lot from one place.</div>
            <div class="page-copy">
                Track your published lots, review buyer interest, and keep each lot's
                status up to date from preparation through completion.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="context-card">
            <div class="context-label">Farmer workspace</div>
            <div class="context-value">Use this page as your control center: check what is available, see where each lot is in the transaction workflow, and open the next action without searching through the marketplace.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    dashboard = get_farmer_dashboard(current_user()['user_id'])
    all_listings = dashboard.get("listings", [])
    interests = dashboard.get("interests", [])

    # Sold/cancelled records remain in the database for audit/history,
    # but are intentionally removed from the active lot inventory shown to farmers.
    listings = [
        x for x in all_listings
        if x["status"] not in {"Sold", "Cancelled"} and float(x["quantity_kg"]) > 0
    ]

    total_listings = len(listings)
    active_listings = sum(1 for x in listings if x["status"] in {"Published", "Under Review", "Negotiation", "Reserved"})
    interested_buyers = len(interests)
    completed = sum(1 for x in all_listings if x["status"] == "Sold")

    m1, m2, m3, m4 = st.columns(4, gap="medium")
    kpis = [
        (m1, "My lots", total_listings),
        (m2, "Active lots", active_listings),
        (m3, "Buyer leads", interested_buyers),
        (m4, "Completed", completed),
    ]
    for col, label, value in kpis:
        with col:
            st.markdown(
                f"""
                <div class="farmer-kpi-card">
                    <div class="farmer-kpi-label">{label}</div>
                    <div class="farmer-kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown('<div class="section-kicker">Quick actions</div>', unsafe_allow_html=True)
    action_cols = st.columns(3, gap="medium")
    farmer_actions = [
        (action_cols[0], "Analyze new residue", "Start with a crop photo.", "Waste Analysis"),
        (action_cols[1], "Find a buyer", "Match an active lot with open RFQs.", "Find Buyers"),
        (action_cols[2], "Add quality evidence", "Record quality details or lot photos.", "Lot Quality & Evidence"),
    ]
    for col, title, description, target in farmer_actions:
        with col:
            st.markdown(
                f'''<div class="quick-action-card">
                    <div class="quick-action-title">{title}</div>
                    <div class="quick-action-text">{description}</div>
                </div>''',
                unsafe_allow_html=True,
            )
            if st.button("Open", key=f"farmer_dashboard_action_{target}", use_container_width=True):
                go_to_page(target)

    st.markdown('<div class="section-kicker">My residue lots</div>', unsafe_allow_html=True)

    if not listings:
        st.markdown(
            """
            <div class="context-card">
                <div class="context-label">No lots yet</div>
                <div class="context-value">Create your first buyer-ready residue listing from Sell Residue.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for item in listings:
            with st.container(border=True):
                left, mid, right = st.columns([2.2, 1.4, 1.1], gap="medium")
                with left:
                    st.markdown(
                        f"### AW-{item['listing_id']:05d} · {format_crop_name(item['crop'])}"
                    )
                    st.write(f"**Residue:** {item['residue']}")
                    st.caption(f"Created {item['created_at']} · {item['location']}")
                with mid:
                    st.write(f"**Quantity**  \n{item['quantity_kg']:,.0f} kg")
                    st.write(f"**Form**  \n{item['form'].title()}")
                    if item.get("moisture_pct") is not None:
                        st.write(f"**Moisture**  \n{item['moisture_pct']:.1f}%")
                with right:
                    st.markdown(
                        f'<span class="status-pill">{item["status"]}</span>',
                        unsafe_allow_html=True,
                    )
                    st.caption("Lot status")
                    current = item["status"] if item["status"] in LISTING_TRANSITIONS else "Published"
                    status_options = [current] + sorted(LISTING_TRANSITIONS.get(current, set()))
                    new_status = st.selectbox(
                        "Update status",
                        status_options,
                        index=0,
                        key=f"status_{item['listing_id']}",
                    )
                    if new_status != current and st.button("Save status", key=f"save_status_{item['listing_id']}"):
                        try:
                            update_listing_status(item["listing_id"], new_status, farmer_id=current_user()['user_id'])
                            st.success("Listing status updated.")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))

                    if st.button("Find buyers", key=f"lot_find_buyers_{item['listing_id']}", use_container_width=True):
                        st.session_state["preparation_listing_id"] = item["listing_id"]
                        go_to_page("Find Buyers")

                with st.expander("View lot timeline"):
                    events = get_audit_events("listing", str(item["listing_id"]), limit=10)
                    if not events:
                        st.caption("No timeline events recorded.")
                    for event in reversed(events):
                        if event["action"] == "status_changed":
                            st.write(f"{event['created_at']} · **{event['old_value']} → {event['new_value']}**")
                        else:
                            st.write(f"{event['created_at']} · **{event['action'].replace('_', ' ').title()}**")

    st.markdown('<div class="section-kicker">Buyer leads linked to your lots</div>', unsafe_allow_html=True)

    if not interests:
        st.caption("No buyer leads have been saved yet.")
    else:
        for item in interests:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.2, 1.5, 1.1], gap="medium")
                with c1:
                    listing_ref = f"AW-{item['listing_id']:05d}" if item.get("listing_id") else "Unlinked lot"
                    st.markdown(f"### {item['buyer_name']}")
                    st.caption(f"{listing_ref} · {format_crop_name(item['crop'])} · {item['residue']}")
                with c2:
                    st.write(f"**Lot**  \n{item['quantity_kg']:,.0f} kg · {item['form'].title()}")
                    st.write(f"**Farmer location**  \n{item['location']}")
                with c3:
                    current = item["status"] if item["status"] in INTEREST_TRANSITIONS else "Saved"
                    interest_statuses = [current] + sorted(INTEREST_TRANSITIONS.get(current, set()))
                    new_status = st.selectbox(
                        "Lead status",
                        interest_statuses,
                        index=0,
                        key=f"interest_status_{item['interest_id']}",
                    )
                    if new_status != current and st.button("Update", key=f"update_interest_{item['interest_id']}"):
                        try:
                            update_interest_status(item["interest_id"], new_status, farmer_id=current_user()['user_id'])
                            st.success("Buyer lead updated.")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))

    st.markdown('<div class="section-kicker">Recommended workflow</div>', unsafe_allow_html=True)
    st.markdown(
        """
        1. **Prepare** the residue according to the selected buyer's requirements.
        2. **Publish** a listing only after quantity and quality information is checked.
        3. **Review buyer leads** and confirm requirements before committing the lot.
        4. Move the lot through **Negotiation → Reserved → Sold** only after the relevant agreement is confirmed.
        5. Keep the final quantity, agreed price, pickup and payment records for traceability when the production transaction system is added.
        """
    )

    st.caption(
        "Current release: local prototype persistence. Production deployment should add authenticated users, "
        "role-based access control, a managed PostgreSQL database, audit logs and verified buyer accounts."
    )

elif page == "Lot Quality & Evidence":

    require_role("farmer")
    farmer_id = current_user()["user_id"]

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Trust layer · Prototype</div>
            <div class="page-title">Document the condition of each residue lot.</div>
            <div class="page-copy">
                Add factual quality information, moisture context, and photo evidence to a specific lot.
                Everything here is recorded as farmer-reported information unless a future verification process is added.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    lots = [
        x for x in get_recent_listings(100, farmer_id=farmer_id)
        if x["status"] not in {"Sold", "Cancelled"}
    ]
    if not lots:
        st.info("Create a residue lot first. Quality information and evidence are attached to a specific lot.")
    else:
        labels = {
            x["listing_id"]: f"AW-{x['listing_id']:05d} · {format_crop_name(x['crop'])} · {x['residue']} · {float(x['quantity_kg']):,.0f} kg"
            for x in lots
        }
        selected_id = st.selectbox(
            "Choose a residue lot",
            list(labels.keys()),
            format_func=lambda x: labels[x],
            key="quality_listing_id",
        )
        listing = next(x for x in lots if x["listing_id"] == selected_id)

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Quantity", f"{float(listing['quantity_kg']):,.0f} kg")
        q2.metric("Form", str(listing["form"]).title())
        q3.metric("Moisture", "Not recorded" if listing.get("moisture_pct") is None else f"{float(listing['moisture_pct']):.1f}%")
        q4.metric("Evidence photos", len(get_listing_evidence(selected_id, farmer_id)))

        st.markdown("### Quality information")
        existing = get_listing_quality(selected_id, farmer_id) or {}
        c1, c2 = st.columns(2)
        with c1:
            cleanliness = st.selectbox(
                "Visible cleanliness",
                ["", "Clean", "Mostly clean", "Needs cleaning"],
                index=["", "Clean", "Mostly clean", "Needs cleaning"].index(existing.get("cleanliness", "")) if existing.get("cleanliness", "") in ["", "Clean", "Mostly clean", "Needs cleaning"] else 0,
                key=f"quality_cleanliness_{selected_id}",
            )
            foreign_material = st.text_input(
                "Visible foreign material / contamination",
                value=existing.get("foreign_material", ""),
                placeholder="Example: small amount of soil; no visible plastic",
                key=f"quality_foreign_{selected_id}",
            )
            storage_condition = st.selectbox(
                "Current storage condition",
                ["", "Covered and dry", "Covered", "Open storage", "Needs review"],
                index=["", "Covered and dry", "Covered", "Open storage", "Needs review"].index(existing.get("storage_condition", "")) if existing.get("storage_condition", "") in ["", "Covered and dry", "Covered", "Open storage", "Needs review"] else 0,
                key=f"quality_storage_{selected_id}",
            )
        with c2:
            measurement_method = st.text_input(
                "Measurement / inspection method",
                value=existing.get("measurement_method", ""),
                placeholder="Example: handheld moisture meter; visual inspection",
                key=f"quality_method_{selected_id}",
            )
            quality_notes = st.text_area(
                "Additional quality notes",
                value=existing.get("notes", ""),
                placeholder="Record observations relevant to the buyer requirement.",
                key=f"quality_notes_{selected_id}",
            )
            st.caption("Status: Farmer reported. This does not mean independently verified quality.")

        if st.button("Save quality information", type="primary", use_container_width=True):
            try:
                save_listing_quality(
                    selected_id,
                    farmer_id=farmer_id,
                    cleanliness=cleanliness,
                    foreign_material=foreign_material,
                    storage_condition=storage_condition,
                    measurement_method=measurement_method,
                    notes=quality_notes,
                )
                st.success("Quality information saved to the selected lot.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

        st.markdown("### Photo evidence")
        st.caption("Upload clear photos of the actual lot. Photos are evidence of appearance only; they do not independently verify moisture, weight, or ownership.")
        uploads = st.file_uploader(
            "Add lot photos",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key=f"quality_photos_{selected_id}",
        )
        photo_caption = st.text_input(
            "Photo caption (optional)",
            placeholder="Example: Stored under cover after drying",
            key=f"quality_photo_caption_{selected_id}",
        )
        if uploads and st.button("Save selected photos", use_container_width=True):
            saved = 0
            base = Path("data") / "listing_evidence" / f"AW-{selected_id:05d}"
            base.mkdir(parents=True, exist_ok=True)
            for upload in uploads:
                try:
                    image = Image.open(upload)
                    image.verify()
                    upload.seek(0)
                    suffix = Path(upload.name).suffix.lower()
                    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(upload.name).stem)[:80] + suffix
                    target = base / f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
                    target.write_bytes(upload.getbuffer())
                    add_listing_evidence(
                        selected_id,
                        file_name=safe_name,
                        file_path=str(target),
                        caption=photo_caption.strip(),
                        farmer_id=farmer_id,
                    )
                    saved += 1
                except Exception as error:
                    st.warning(f"Could not save {upload.name}: {error}")
            if saved:
                st.success(f"Saved {saved} photo(s) to AW-{selected_id:05d}.")
                st.rerun()

        evidence = get_listing_evidence(selected_id, farmer_id)
        if evidence:
            st.markdown("### Stored evidence")
            cols = st.columns(min(3, len(evidence)))
            for idx, item in enumerate(evidence):
                with cols[idx % len(cols)]:
                    if Path(item["file_path"]).exists():
                        st.image(item["file_path"], use_container_width=True)
                    st.caption(f"{item['file_name']} · {item['created_at']}")
                    if item.get("caption"):
                        st.write(item["caption"])
        else:
            st.caption("No photos have been added to this lot yet.")

        st.markdown("### Lot traceability")
        events = get_audit_events("listing", str(selected_id), limit=50)
        quality_events = get_audit_events("listing_quality", str(selected_id), limit=20)
        combined = events + quality_events
        combined.sort(key=lambda x: x.get("event_id", 0), reverse=True)
        if combined:
            for event in combined:
                action = event.get("action", "event").replace("_", " ").title()
                detail = event.get("new_value") or event.get("old_value") or ""
                st.write(f"**{event['created_at']}** · {action}" + (f" · {detail}" if detail else ""))
        else:
            st.caption("Traceability events will appear as the lot moves through the marketplace workflow.")



elif page == "Marketplace":

    require_role("farmer")

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Market connection · Step 04</div>
            <div class="page-title">Sell agricultural residue with a clear buyer-ready listing.</div>
            <div class="page-copy">
                Describe one residue lot, check buyer requirements, review the listing,
                and publish it to the prototype marketplace.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "Prototype marketplace: buyer profiles shown here are sample requirements. "
        "They are not verified businesses, live prices, or guaranteed transactions."
    )

    # ---------- Step 1: Lot details ----------
    st.markdown('<div class="section-kicker">Step 1 · Describe your residue lot</div>', unsafe_allow_html=True)

    crop_options = [
        "rice", "wheat", "sugarcane", "maize", "cotton", "coconut",
        "jute", "banana", "soyabean", "jowar", "Pearl_millet(bajra)"
    ]
    default_crop = st.session_state.selected_crop if st.session_state.selected_crop in crop_options else "rice"

    selected_crop = st.selectbox(
        "Crop / residue",
        crop_options,
        index=crop_options.index(default_crop),
        format_func=format_crop_name,
        key="market_crop",
    )
    waste_info, _ = analyze_crop(selected_crop)

    st.markdown(
        f"""
        <div class="context-card">
            <div class="context-label">Residue identified for this listing</div>
            <div class="context-value">{format_crop_name(selected_crop)} · {waste_info["waste_name"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        quantity = st.number_input("Available quantity (kg)", min_value=1.0, value=500.0, step=10.0, key="market_quantity")
    with c2:
        form = st.selectbox("Current form", ["raw", "dry", "processed"], format_func=lambda x: x.title(), key="market_form")
    with c3:
        moisture = st.number_input(
            "Measured moisture (%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5,
            help="Use a moisture meter when a buyer specifies a moisture limit.", key="market_moisture",
        )

    c4, c5 = st.columns(2, gap="medium")
    with c4:
        cleaned = st.checkbox(
            "I have removed visible soil, stones, plastic and other contamination.",
            value=True, key="market_cleaned",
        )
    with c5:
        processed = st.checkbox(
            "The residue has already been processed as requested.",
            value=(form == "processed"), key="market_processed",
        )

    location = st.text_input(
        "Farmer location / nearest village or town",
        placeholder="Example: nearest village, block or town",
        key="market_location",
    )
    pickup = st.checkbox("I can make the lot available for buyer pickup.", value=True, key="market_pickup")

    processing_note = st.text_input(
        "Preparation / processing details",
        placeholder="Example: sun-dried, cleaned, baled",
        key="market_processing",
    )
    listing_notes = st.text_area(
        "Additional notes for the buyer",
        placeholder="Harvest date, approximate storage duration, separation of grades, etc.",
        key="market_notes",
    )

    # ---------- Step 2: Buyer requirements ----------
    st.markdown('<div class="section-kicker">Step 2 · Check buyer requirements</div>', unsafe_allow_html=True)

    buyers = get_buyer_listings(selected_crop)
    if not buyers:
        st.warning("No demo buyer requirements are loaded for this crop yet.")
    else:
        results = []
        for buyer in buyers:
            result = match_buyer(
                buyer,
                farmer_form=form,
                quantity_kg=quantity,
                moisture_pct=moisture,
                cleaned=cleaned,
                processed=processed,
            )
            results.append((buyer, result))
        results.sort(key=lambda item: item[1]["score"], reverse=True)

        for buyer, result in results:
            gap = build_requirement_gap(
                buyer,
                farmer_form=form,
                quantity_kg=quantity,
                moisture_pct=moisture,
                cleaned=cleaned,
                processed=processed,
            )
            with st.container(border=True):
                h1, h2 = st.columns([4, 1])
                with h1:
                    st.markdown(f"### {buyer['buyer_name']}")
                    st.caption(f"{buyer['buyer_type']} · {buyer['location']}")
                with h2:
                    st.metric("Prototype match", f"{result['score']:.0f}/100")

                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Minimum", f"{buyer['min_quantity_kg']:,.0f} kg")
                r2.metric("Moisture", "Not specified" if buyer['max_moisture_pct'] is None else f"≤ {buyer['max_moisture_pct']:.1f}%")
                r3.metric("Forms", ", ".join(x.title() for x in buyer['accepted_forms']))
                r4.metric("Pickup", "Available" if buyer['pickup_available'] else "Not listed")

                st.markdown("**Requirement check**")
                render_requirement_gap(buyer, gap)

                if result["reasons"]:
                    st.markdown("**Why the lot matches**")
                    for reason in result["reasons"]:
                        st.markdown(f"- {reason}")

                if buyer["notes"]:
                    st.caption(f"Buyer note: {buyer['notes']}")

    # ---------- Step 3: Publish ----------
    st.markdown('<div class="section-kicker">Step 3 · Review and publish</div>', unsafe_allow_html=True)

    if st.button("Create listing draft", type="primary", use_container_width=True):
        if not location.strip():
            st.error("Enter a location before creating the listing.")
        else:
            st.session_state.farmer_listing_draft = build_farmer_listing(
                crop=selected_crop,
                residue=waste_info["waste_name"],
                quantity_kg=quantity,
                form=form,
                moisture_pct=moisture,
                processing=processing_note,
                location=location,
                pickup=pickup,
                notes=listing_notes,
            )
            st.success("Listing draft created. Review the details below before publishing.")

    draft = st.session_state.get("farmer_listing_draft")
    if draft:
        st.markdown("### Listing preview")
        preview_cols = st.columns(3)
        preview_cols[0].metric("Quantity", f"{draft['quantity_kg']:,.0f} kg")
        preview_cols[1].metric("Form", draft["form"].title())
        preview_cols[2].metric("Moisture", f"{draft['moisture_pct']:.1f}%")

        p1, p2 = st.columns(2)
        with p1:
            st.markdown(
                f"**Residue**  \n{format_crop_name(draft['crop'])} · {draft['residue']}  \n\n"
                f"**Location**  \n{draft['location']}"
            )
        with p2:
            st.markdown(
                f"**Processing**  \n{draft['processing'] or 'Not specified'}  \n\n"
                f"**Pickup**  \n{'Available' if draft['pickup_available'] else 'Not available'}"
            )

        if draft.get("notes"):
            st.markdown(f"**Buyer note**  \n{draft['notes']}")

        if draft.get("status") == "Published":
            st.success(f"Published · AW-{draft['listing_id']:05d}")
        else:
            st.caption("Draft only — nothing has been published yet.")
            if st.button("Publish listing to prototype marketplace", type="primary", use_container_width=True):
                publish_payload = dict(draft)
                publish_payload["status"] = "Published"
                listing_id = create_listing(publish_payload, farmer_id=current_user()["user_id"])
                st.session_state.farmer_listing_draft["listing_id"] = listing_id
                st.session_state.farmer_listing_draft["status"] = "Published"
                st.session_state.active_listing_id = listing_id
                st.success(f"Listing published successfully. Reference: AW-{listing_id:05d}")

    # ---------- Marketplace records ----------
    st.markdown('<div class="section-kicker">Your marketplace activity</div>', unsafe_allow_html=True)
    recent_listings = get_recent_listings(limit=5, farmer_id=current_user()["user_id"])
    recent_interests = get_recent_interests(limit=5, farmer_id=current_user()["user_id"])

    if recent_listings:
        st.markdown("### Your recent lots")
        for item in recent_listings:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f"**AW-{item['listing_id']:05d} · {format_crop_name(item['crop'])} · {item['residue']}**")
                    st.caption(
                        f"{item['quantity_kg']:,.0f} kg · {item['form'].title()} · "
                        f"{item['location']} · Created {item['created_at']}"
                    )
                with b:
                    st.markdown(f'<span class="status-pill">{item["status"]}</span>', unsafe_allow_html=True)

    if recent_interests:
        st.markdown("### Buyer interest")
        for item in recent_interests:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f"**#{item['interest_id']} · {item['buyer_name']} · {format_crop_name(item['crop'])}**")
                    st.caption(f"{item['quantity_kg']:,.0f} kg · {item['form'].title()} · {item['location']}")
                with b:
                    st.markdown(f'<span class="status-pill">{item["status"]}</span>', unsafe_allow_html=True)

    st.caption(
        "Prototype storage uses local SQLite. Live buyer accounts, live pricing and real transactions are not connected in this release."
    )

# ============================================================
# PREPARATION GUIDE
# ============================================================

elif page == "Find Buyers":

    require_role("farmer")
    farmer_id=current_user()["user_id"]

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Marketplace intelligence · Step 05</div>
            <div class="page-title">Find buyers that fit your residue lot.</div>
            <div class="page-copy">
                Compare active lots with open buyer requests and see what matches,
                what needs preparation, and what currently does not fit.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    lots=[
        x for x in get_recent_listings(100, farmer_id=farmer_id)
        if x["status"] not in {"Sold","Cancelled"} and float(x["quantity_kg"])>0
    ]
    rfqs=get_open_rfqs()

    if not lots:
        st.info("Create an active residue lot first. Buyer matches will appear here.")
    elif not rfqs:
        st.info("There are no open buyer requests yet.")
    else:
        labels={
            x["listing_id"]:
            f"AW-{x['listing_id']:05d} · {format_crop_name(x['crop'])} · {x['residue']} · {float(x['quantity_kg']):,.0f} kg"
            for x in lots
        }
        selected_id=st.selectbox(
            "Choose a residue lot",
            list(labels.keys()),
            format_func=lambda x: labels[x],
            key="matching_listing_id",
        )
        listing=next(x for x in lots if x["listing_id"]==selected_id)

        matches=[
            (r,match_listing_to_rfq(listing,r))
            for r in rfqs
            if _normalize_text(r.get("crop"))==_normalize_text(listing.get("crop"))
            and _normalize_text(r.get("residue"))==_normalize_text(listing.get("residue"))
        ]

        if not matches:
            st.info("No open buyer request currently matches this crop and residue type.")
        else:
            ready=[x for x in matches if x[1]["category"]=="Ready to respond"]
            prep=[x for x in matches if x[1]["category"]=="Preparation needed"]
            blocked=[x for x in matches if x[1]["category"]=="Not currently compatible"]

            a,b,c=st.columns(3)
            a.metric("Ready to respond",len(ready))
            b.metric("Preparation needed",len(prep))
            c.metric("Not currently compatible",len(blocked))
            st.caption(
                "This is a requirement comparison, not a purchase guarantee. "
                "Confirm final quality, transport, price and buyer acceptance."
            )

            for rfq,result in ready+prep+blocked:
                with st.container(border=True):
                    left,right=st.columns([3,1])
                    with left:
                        st.markdown(f"### RFQ-{rfq['rfq_id']:05d} · {rfq['buyer_name']}")
                        st.caption(
                            f"{format_crop_name(rfq['crop'])} · {rfq['residue']} · "
                            f"Minimum {float(rfq['min_quantity_kg']):,.0f} kg"
                        )
                    with right:
                        _render_deal_status(result["category"])

                    if result["matched"]:
                        st.markdown("**Already aligned**")
                        for item in result["matched"]:
                            st.markdown(f"- {item}")
                    if result["preparation"]:
                        st.markdown("**What to prepare or confirm**")
                        for item in result["preparation"]:
                            st.markdown(f"- {item}")
                    if result["blockers"]:
                        st.markdown("**Current blockers**")
                        for item in result["blockers"]:
                            st.markdown(f"- {item}")

                    if result["category"] in {"Ready to respond","Preparation needed"}:
                        if st.button(
                            "Prepare this lot",
                            key=f"prepare_match_{selected_id}_{rfq['rfq_id']}",
                            use_container_width=True,
                        ):
                            st.session_state["preparation_listing_id"]=selected_id
                            st.session_state["preparation_rfq_id"]=rfq["rfq_id"]
                            st.success("Buyer requirement selected. Open Preparation Guide to continue.")

                        if st.button(
                            "Create response draft",
                            key=f"draft_match_{selected_id}_{rfq['rfq_id']}",
                            use_container_width=True,
                        ):
                            draft = build_farmer_response_draft(listing, rfq, result)
                            draft_key = f"rfq_message_{rfq['rfq_id']}_{selected_id}"
                            st.session_state[draft_key] = draft
                            st.session_state["rfq_draft_rfq_id"] = rfq["rfq_id"]
                            st.session_state["rfq_draft_listing_id"] = selected_id
                            st.success(
                                "Draft created. Open Buyer Requests to review and edit it before submitting."
                            )


elif page == "Buyer Requests":

    require_role("farmer")

    farmer_id = current_user()["user_id"]

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Farmer marketplace · Step 04B</div>
            <div class="page-title">See what buyers are looking for.</div>
            <div class="page-copy">
                Browse open buyer requests, compare them with your own residue lots,
                and respond only when the selected lot meets the buyer's stated hard requirements.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    open_rfqs = get_open_rfqs()

    if not open_rfqs:
        st.info(
            "There are no open buyer requests at the moment. New requests will appear here "
            "when buyers publish them."
        )
    else:
        my_lots = [
            item
            for item in get_recent_listings(limit=50, farmer_id=farmer_id)
            if item["status"] not in {"Sold", "Cancelled"}
        ]

        for rfq in open_rfqs:
            with st.container(border=True):
                st.markdown(
                    f"### RFQ-{rfq['rfq_id']:05d} · {format_crop_name(rfq['crop'])}"
                )
                st.caption(
                    f"{rfq['buyer_name']} · {rfq['location']} · {rfq['residue']}"
                )

                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Minimum quantity", f"{rfq['min_quantity_kg']:,.0f} kg")
                q2.metric(
                    "Max moisture",
                    "Not specified"
                    if rfq["max_moisture_pct"] is None
                    else f"{rfq['max_moisture_pct']:.1f}%",
                )
                q3.metric(
                    "Accepted form",
                    ", ".join(x.title() for x in rfq["accepted_forms"]),
                )
                q4.metric(
                    "Pickup",
                    "Required" if rfq["pickup_required"] else "Not required",
                )

                if rfq["processing_required"]:
                    st.write(f"**Processing:** {rfq['processing_required']}")
                if rfq["packaging"]:
                    st.write(f"**Packaging:** {rfq['packaging']}")
                if rfq["notes"]:
                    st.write(f"**Buyer notes:** {rfq['notes']}")

                matching_lots = [
                    lot for lot in my_lots
                    if lot["crop"] == rfq["crop"]
                ]

                if not matching_lots:
                    st.warning(
                        "You do not currently have an active lot for this crop. "
                        "Create a residue lot first."
                    )
                    continue

                lot_labels = {
                    lot["listing_id"]: (
                        f"AW-{lot['listing_id']:05d} · "
                        f"{lot['quantity_kg']:,.0f} kg · "
                        f"{lot['form'].title()} · "
                        f"{'moisture ' + format(lot['moisture_pct'], '.1f') + '%' if lot.get('moisture_pct') is not None else 'moisture not recorded'}"
                    )
                    for lot in matching_lots
                }

                selected_lot_id = st.selectbox(
                    "Select a lot to compare",
                    list(lot_labels.keys()),
                    format_func=lambda x: lot_labels[x],
                    key=f"rfq_lot_{rfq['rfq_id']}",
                )
                selected_lot = next(
                    lot for lot in matching_lots
                    if lot["listing_id"] == selected_lot_id
                )

                gap = build_requirement_gap(
                    rfq,
                    farmer_form=selected_lot["form"],
                    quantity_kg=selected_lot["quantity_kg"],
                    moisture_pct=float(selected_lot.get("moisture_pct") or 0),
                    cleaned=None,
                    processed=selected_lot["form"] == "processed",
                )
                render_requirement_gap(rfq, gap)

                form_ok = (
                    not rfq["accepted_forms"]
                    or selected_lot["form"].lower() in rfq["accepted_forms"]
                )
                quantity_ok = selected_lot["quantity_kg"] >= rfq["min_quantity_kg"]
                moisture_ok = (
                    rfq["max_moisture_pct"] is None
                    or (
                        selected_lot.get("moisture_pct") is not None
                        and float(selected_lot["moisture_pct"]) <= float(rfq["max_moisture_pct"])
                    )
                )
                hard_requirements_met = form_ok and quantity_ok and moisture_ok

                if not hard_requirements_met:
                    st.warning(
                        "This lot does not currently meet all hard RFQ requirements. "
                        "Use Preparation Guide to prepare the lot and re-measure it before responding."
                    )
                    continue

                response_qty = st.number_input(
                    "Quantity you want to offer (kg)",
                    min_value=float(rfq["min_quantity_kg"]),
                    max_value=float(selected_lot["quantity_kg"]),
                    value=min(
                        float(selected_lot["quantity_kg"]),
                        float(rfq["min_quantity_kg"]),
                    ),
                    step=10.0,
                    key=f"rfq_qty_{rfq['rfq_id']}_{selected_lot_id}",
                )
                response_price = st.number_input(
                    "Your offered price (₹/kg) — optional",
                    min_value=0.0,
                    value=0.0,
                    step=0.50,
                    key=f"rfq_price_{rfq['rfq_id']}_{selected_lot_id}",
                )
                response_message_key = f"rfq_message_{rfq['rfq_id']}_{selected_lot_id}"
                if (
                    st.session_state.get("rfq_draft_rfq_id") == rfq["rfq_id"]
                    and st.session_state.get("rfq_draft_listing_id") == selected_lot_id
                    and response_message_key not in st.session_state
                ):
                    st.session_state[response_message_key] = build_farmer_response_draft(
                        selected_lot,
                        rfq,
                        match_listing_to_rfq(selected_lot, rfq),
                    )

                response_message = st.text_area(
                    "Message to buyer",
                    placeholder="Example: Lot is ready for pickup; final weight will be confirmed at loading.",
                    key=response_message_key,
                    help="Review and edit this message before submitting. The draft is based only on the selected lot and buyer request.",
                )

                if st.button(
                    "Respond to this RFQ",
                    type="primary",
                    key=f"rfq_respond_{rfq['rfq_id']}_{selected_lot_id}",
                    use_container_width=True,
                ):
                    try:
                        response_id = create_rfq_response(
                            rfq_id=rfq["rfq_id"],
                            farmer_id=farmer_id,
                            listing_id=selected_lot_id,
                            offered_quantity_kg=response_qty,
                            offered_price_per_kg=response_price if response_price > 0 else None,
                            message=response_message,
                        )
                        st.success(
                            f"Response #{response_id} submitted to {rfq['buyer_name']}."
                        )
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

    st.markdown('<div class="section-kicker">My RFQ responses</div>', unsafe_allow_html=True)
    responses = get_rfq_responses_for_farmer(farmer_id)

    if not responses:
        st.caption("You have not responded to any buyer RFQ yet.")
    else:
        for response in responses:
            with st.container(border=True):
                st.write(
                    f"**RFQ-{response['rfq_id']:05d} · {response['buyer_name']}**"
                )
                st.caption(
                    f"AW-{response['listing_id']:05d} · {format_crop_name(response['crop'])} · "
                    f"{response['offered_quantity_kg']:,.0f} kg · {response['status']}"
                )
                if response["offered_price_per_kg"] is not None:
                    st.write(
                        f"Offered price: ₹{response['offered_price_per_kg']:,.2f}/kg"
                    )

                deal = get_deal_for_response(response["response_id"])
                if deal:
                    st.markdown("**Negotiation available in the transaction center**")
                    _render_deal_status(deal["status"])
                elif response["status"] not in {"Declined", "Withdrawn"}:
                    st.caption(
                        "The buyer can open a negotiation from your submitted response. "
                        "Once they do, it will appear in Negotiations & Sales."
                    )


elif page == "Preparation Guide":

    require_role("farmer")

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Farmer workspace · Step 05</div>
            <div class="page-title">Prepare your residue for a specific buyer.</div>
            <div class="page-copy">
                Select your residue lot, compare the buyer's requirements, and record
                each preparation step. Buyer specifications take priority over generic advice.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    farmer_id = current_user()["user_id"]
    preparation_lots = [
        item
        for item in get_recent_listings(limit=50, farmer_id=farmer_id)
        if item["status"] not in {"Sold", "Cancelled"}
    ]

    if not preparation_lots:
        st.info(
            "You do not have an active residue lot yet. Create and publish a lot from "
            "Sell Residue first, then return here to prepare it for a buyer."
        )
    else:
        lot_labels = {
            item["listing_id"]: (
                f"AW-{item['listing_id']:05d} · "
                f"{format_crop_name(item['crop'])} · "
                f"{item['quantity_kg']:,.0f} kg · "
                f"{item['form'].title()} · {item['status']}"
            )
            for item in preparation_lots
        }

        _preselected_listing_id = st.session_state.get("preparation_listing_id")
        _listing_index = (
            list(lot_labels.keys()).index(_preselected_listing_id)
            if _preselected_listing_id in lot_labels else 0
        )
        selected_listing_id = st.selectbox(
            "Residue lot to prepare",
            list(lot_labels.keys()),
            index=_listing_index,
            format_func=lambda x: lot_labels[x],
            key="preparation_listing_selector",
        )

        selected_listing = next(
            item for item in preparation_lots
            if item["listing_id"] == selected_listing_id
        )

        # Industry workflow: prefer an explicit buyer RFQ over generic buyer
        # profiles. An RFQ contains the actual requirements the farmer is trying
        # to satisfy for a real marketplace request.
        open_rfqs = get_open_rfqs(selected_listing["crop"])

        requirement_options = {None: "No buyer requirement selected"}
        requirement_records = {}

        for rfq in open_rfqs:
            key = f"rfq:{rfq['rfq_id']}"
            requirement_options[key] = (
                f"RFQ-{rfq['rfq_id']:05d} · {rfq['buyer_name']} · "
                f"{rfq['min_quantity_kg']:,.0f} kg"
            )
            requirement_records[key] = normalize_rfq_requirement(rfq)

        # Keep legacy/demo buyer profiles available when no RFQ exists for
        # the selected crop, but label them clearly as general requirements.
        if not open_rfqs:
            buyers = get_buyer_listings(selected_listing["crop"])
            for buyer in buyers:
                key = f"buyer:{buyer['buyer_id']}"
                requirement_options[key] = (
                    f"General profile · {buyer['buyer_name']} · {buyer['location']}"
                )
                requirement_records[key] = {
                    **buyer,
                    "source": "Buyer profile",
                }

        _preselected_rfq_id = st.session_state.get("preparation_rfq_id")
        _preselected_key = (
            f"rfq:{_preselected_rfq_id}" if _preselected_rfq_id is not None else None
        )
        _requirement_index = (
            list(requirement_options.keys()).index(_preselected_key)
            if _preselected_key in requirement_options else 0
        )

        selected_requirement_key = st.selectbox(
            "Buyer requirement to prepare for",
            list(requirement_options.keys()),
            index=_requirement_index,
            format_func=lambda x: requirement_options[x],
            key="preparation_buyer_requirement",
            help=(
                "For marketplace preparation, select an open RFQ whenever possible. "
                "Its requirements are the buyer's stated specification for that request."
            ),
        )

        selected_buyer = requirement_records.get(selected_requirement_key)
        selected_buyer_id = (
            selected_buyer.get("buyer_id")
            if selected_buyer
            else None
        )

        if selected_buyer and selected_buyer.get("source") == "RFQ":
            st.info(
                f"Preparing against RFQ-{selected_buyer['rfq_id']:05d}. "
                "These are the buyer's stated requirements for this request."
            )

        st.markdown("### Current lot")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Quantity", f"{selected_listing['quantity_kg']:,.0f} kg")
        c2.metric("Current form", selected_listing["form"].title())
        c3.metric(
            "Moisture",
            "Not recorded"
            if selected_listing.get("moisture_pct") is None
            else f"{selected_listing['moisture_pct']:.1f}%",
        )
        c4.metric("Status", selected_listing["status"])

        target_form = None
        target_moisture = None
        target_quantity = None
        packaging = ""

        if selected_buyer:
            st.markdown("### Buyer requirements")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric(
                "Accepted form",
                ", ".join(x.title() for x in selected_buyer["accepted_forms"])
                or "Not specified",
            )
            r2.metric(
                "Minimum quantity",
                f"{selected_buyer['min_quantity_kg']:,.0f} kg",
            )
            r3.metric(
                "Maximum moisture",
                "Not specified"
                if selected_buyer["max_moisture_pct"] is None
                else f"{selected_buyer['max_moisture_pct']:.1f}%",
            )
            r4.metric(
                "Packaging",
                selected_buyer["packaging"] or "Not specified",
            )

            if selected_buyer["accepted_forms"]:
                target_form = st.selectbox(
                    "Target form for this buyer",
                    selected_buyer["accepted_forms"],
                    index=0,
                    key=f"prep_target_form_{selected_listing_id}",
                    help="Choose the form you intend to deliver. Do not select a form the buyer has not accepted.",
                )
            target_moisture = selected_buyer["max_moisture_pct"]
            target_quantity = selected_buyer["min_quantity_kg"]
            packaging = selected_buyer["packaging"]

            gap = build_requirement_gap(
                selected_buyer,
                farmer_form=selected_listing["form"],
                quantity_kg=selected_listing["quantity_kg"],
                moisture_pct=float(selected_listing.get("moisture_pct") or 0),
                cleaned=None,
                processed=selected_listing["form"] == "processed",
            )

            render_requirement_gap(selected_buyer, gap)
        else:
            st.info(
                "Select a buyer to turn the general preparation guide into a buyer-specific plan."
            )

        st.markdown("### Preparation checklist")

        checklist = [
            ("clean", "Remove visible soil, stones, plastic and other contamination."),
            ("separate", "Separate different grades or materials so the lot stays consistent."),
            ("dry", "Dry the residue if the buyer requires a dry form or moisture limit."),
            ("measure", "Measure the actual moisture of the lot before delivery."),
            ("process", "Complete only the processing requested by the buyer."),
            ("package", "Prepare packaging according to the buyer's stated requirement."),
            ("photos", "Take clear photos showing the prepared lot."),
            ("store", "Keep the prepared lot protected from rain and contamination until pickup."),
            ("confirm", "Confirm quantity, quality, pickup and final specifications with the buyer."),
        ]

        existing = get_preparation(selected_listing_id, farmer_id=farmer_id)
        existing_steps = set(
            x for x in (existing or {}).get("completed_steps", "").split(",") if x
        )

        completed = []
        for key, label in checklist:
            checked = st.checkbox(
                label,
                value=(key in existing_steps),
                key=f"prep_{selected_listing_id}_{key}",
            )
            if checked:
                completed.append(key)

        final_moisture = st.number_input(
            "Final measured moisture (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(
                (existing or {}).get("final_moisture_pct")
                or selected_listing.get("moisture_pct")
                or 0.0
            ),
            step=0.1,
            help="Enter the measured value from the actual lot. Do not estimate it.",
        )

        prep_notes = st.text_area(
            "Preparation notes",
            value=(existing or {}).get("notes", ""),
            placeholder="Example: dried, cleaned, packed in 25 kg bags; measurement taken on 24 Sep.",
            key=f"prep_notes_{selected_listing_id}",
        )

        all_steps_done = len(completed) == len(checklist)

        moisture_ok = True
        if selected_buyer and selected_buyer["max_moisture_pct"] is not None:
            moisture_ok = final_moisture <= float(selected_buyer["max_moisture_pct"])

        quantity_ok = True
        if selected_buyer:
            quantity_ok = float(selected_listing["quantity_kg"]) >= float(
                selected_buyer["min_quantity_kg"]
            )

        form_ok = True
        if selected_buyer and selected_buyer["accepted_forms"]:
            form_ok = (
                selected_listing["form"].lower()
                in {str(x).lower() for x in selected_buyer["accepted_forms"]}
                or bool(target_form)
            )

        buyer_ready = (
            bool(selected_buyer)
            and all_steps_done
            and moisture_ok
            and quantity_ok
            and form_ok
        )

        if buyer_ready:
            st.success(
                "The preparation checklist is complete and the recorded final moisture "
                "meets the buyer's stated limit. Confirm the final buyer specification before dispatch."
            )
        else:
            st.info(
                "Complete the applicable preparation steps and record the final measured "
                "condition before marking the lot ready for buyer review."
            )
            if selected_buyer and selected_buyer["max_moisture_pct"] is not None and not moisture_ok:
                st.warning(
                    f"The recorded final moisture ({final_moisture:.1f}%) is above the "
                    f"buyer's stated limit ({float(selected_buyer['max_moisture_pct']):.1f}%). "
                    "Do not mark the lot ready until the actual lot meets the buyer's specification."
                )

            if selected_buyer and not quantity_ok:
                st.warning(
                    f"The available lot quantity ({float(selected_listing['quantity_kg']):,.0f} kg) "
                    f"is below the buyer's minimum ({float(selected_buyer['min_quantity_kg']):,.0f} kg). "
                    "Ask the buyer whether a smaller lot is acceptable before responding."
                )

        save_col, status_col = st.columns([2, 1])
        with save_col:
            if st.button(
                "Save preparation progress",
                type="primary",
                use_container_width=True,
            ):
                status = "Ready for Buyer Review" if buyer_ready else "In Progress"
                try:
                    preparation_id = create_or_update_preparation(
                        listing_id=selected_listing_id,
                        farmer_id=farmer_id,
                        buyer_id=selected_buyer_id,
                        target_form=target_form,
                        target_moisture_pct=target_moisture,
                        target_quantity_kg=target_quantity,
                        packaging=packaging,
                        completed_steps=",".join(completed),
                        final_moisture_pct=final_moisture,
                        notes=prep_notes,
                        status=status,
                    )
                    st.success(
                        f"Preparation record #{preparation_id} saved. Status: {status}."
                    )
                except ValueError as error:
                    st.error(str(error))

        with status_col:
            st.metric(
                "Preparation status",
                "Ready for review" if buyer_ready else "In progress",
            )

        st.caption(
            "Important: the preparation checklist is a workflow aid. It does not certify "
            "quality or replace the buyer's inspection, laboratory testing, agricultural guidance, "
            "or applicable safety requirements."
        )


# ============================================================
# ECONOMIC VALUE
# ============================================================

elif page == "Buyer Portal":

    require_role("buyer")

    buyer_user = current_user()
    buyer_id = buyer_user["user_id"]
    buyer_name = buyer_user["full_name"]

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Buyer workspace · Phase 03B</div>
            <div class="page-title">Create a clear residue request.</div>
            <div class="page-copy">
                Tell farmers exactly what residue you need, what form and quality you accept,
                how much you need, and how the material should be prepared.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-kicker">Step 1 · Create RFQ</div>', unsafe_allow_html=True)

    crop_options = [
        "rice", "wheat", "sugarcane", "maize", "cotton", "coconut",
        "jute", "banana", "soyabean", "jowar", "Pearl_millet(bajra)"
    ]

    rfq_crop = st.selectbox(
        "Crop / residue source",
        crop_options,
        format_func=format_crop_name,
        key="rfq_crop",
    )
    rfq_waste, _ = analyze_crop(rfq_crop)

    st.markdown(
        f"""
        <div class="context-card">
            <div class="context-label">Residue requested</div>
            <div class="context-value">{format_crop_name(rfq_crop)} · {rfq_waste["waste_name"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    accepted_forms = st.multiselect(
        "Accepted residue form",
        ["raw", "dry", "processed"],
        default=["dry"],
        format_func=lambda x: x.title(),
        key="rfq_forms",
        help="Select every form you are prepared to receive. Do not select a form unless your process can accept it.",
    )

    r1, r2 = st.columns(2, gap="medium")
    with r1:
        rfq_min_qty = st.number_input(
            "Minimum quantity required (kg)",
            min_value=1.0,
            value=1000.0,
            step=50.0,
            key="rfq_min_qty",
        )
    with r2:
        rfq_max_moisture = st.number_input(
            "Maximum moisture (%)",
            min_value=0.0,
            max_value=100.0,
            value=15.0,
            step=0.5,
            key="rfq_max_moisture",
            help="Only enter a limit if your process has a defined moisture specification.",
        )

    rfq_processing = st.text_input(
        "Processing requirement",
        placeholder="Example: cleaned and dried; baled; chipped; no additional processing",
        key="rfq_processing",
    )
    rfq_packaging = st.text_input(
        "Packaging requirement",
        placeholder="Example: loose, bale, 25 kg bags",
        key="rfq_packaging",
    )

    pickup_required = st.checkbox(
        "Pickup is required from the farmer's location",
        value=True,
        key="rfq_pickup",
    )

    rfq_location = st.text_input(
        "Buyer location / preferred collection area",
        placeholder="Example: Bhubaneswar industrial area",
        key="rfq_location",
    )
    rfq_notes = st.text_area(
        "Additional requirements",
        placeholder="Quality checks, acceptable contamination level, preferred delivery window, etc.",
        key="rfq_notes",
    )

    if st.button("Publish RFQ to farmer marketplace", type="primary", use_container_width=True):
        try:
            rfq_id = create_rfq(
                buyer_id=buyer_id,
                buyer_name=buyer_name,
                crop=rfq_crop,
                residue=rfq_waste["waste_name"],
                accepted_forms=accepted_forms,
                max_moisture_pct=rfq_max_moisture,
                min_quantity_kg=rfq_min_qty,
                processing_required=rfq_processing,
                packaging=rfq_packaging,
                pickup_required=pickup_required,
                location=rfq_location,
                notes=rfq_notes,
            )
            st.success(f"RFQ #{rfq_id} is now open for farmer responses.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))

    st.divider()

    st.markdown('<div class="section-kicker">Step 2 · My RFQs</div>', unsafe_allow_html=True)
    my_rfqs = get_buyer_rfqs(buyer_id)

    if not my_rfqs:
        st.info("You have not published an RFQ yet.")
    else:
        for rfq in my_rfqs:
            with st.container(border=True):
                a, b = st.columns([3, 1])
                with a:
                    st.markdown(
                        f"### RFQ-{rfq['rfq_id']:05d} · {format_crop_name(rfq['crop'])}"
                    )
                    st.caption(
                        f"{rfq['residue']} · {rfq['location']} · Created {rfq['created_at']}"
                    )
                with b:
                    _render_deal_status(rfq["status"])

                st.write(
                    f"**Accepted form:** {', '.join(x.title() for x in rfq['accepted_forms'])}  \n"
                    f"**Minimum quantity:** {rfq['min_quantity_kg']:,.0f} kg  \n"
                    f"**Maximum moisture:** "
                    f"{'Not specified' if rfq['max_moisture_pct'] is None else f'{rfq["max_moisture_pct"]:.1f}%'}  \n"
                    f"**Processing:** {rfq['processing_required'] or 'Not specified'}  \n"
                    f"**Packaging:** {rfq['packaging'] or 'Not specified'}  \n"
                    f"**Pickup:** {'Required' if rfq['pickup_required'] else 'Not required'}"
                )

                responses = get_rfq_responses_for_buyer(
                    buyer_id,
                    rfq_id=rfq["rfq_id"],
                )

                if not responses:
                    st.caption("No farmer responses yet.")
                else:
                    st.markdown("**Farmer responses**")
                    for response in responses:
                        with st.container(border=True):
                            st.write(
                                f"**Lot:** AW-{response['listing_id']:05d} · "
                                f"**Quantity offered:** {response['offered_quantity_kg']:,.0f} kg"
                            )
                            price = response["offered_price_per_kg"]
                            st.write(
                                f"**Price offered:** "
                                f"{'Not specified' if price is None else f'₹{price:,.2f}/kg'}"
                            )
                            if response["message"]:
                                st.caption(response["message"])

                            # Buyer-facing prototype view: expose lot quality/evidence, not private contact details.
                            response_listing = get_listing(response["listing_id"], farmer_id=response.get("farmer_id", "DEMO-FARMER-001"))
                            if response_listing:
                                quality = get_listing_quality(response_listing["listing_id"], response_listing.get("farmer_id", "DEMO-FARMER-001"))
                                photos = get_listing_evidence(response_listing["listing_id"])
                                with st.expander("View lot quality & evidence"):
                                    st.write(f"**Form:** {response_listing['form'].title()}")
                                    moisture_text = "Not recorded" if response_listing.get("moisture_pct") is None else f"{float(response_listing['moisture_pct']):.1f}%"
                                    st.write(f"**Moisture:** {moisture_text}")
                                    st.write(f"**Processing:** {response_listing.get('processing') or 'Not recorded'}")
                                    st.write(f"**Location:** {response_listing.get('location') or 'Not recorded'}")
                                    if quality:
                                        st.write(f"**Quality status:** {quality['status']}")
                                        if quality.get("cleanliness"): st.write(f"**Cleanliness:** {quality['cleanliness']}")
                                        if quality.get("foreign_material"): st.write(f"**Foreign material:** {quality['foreign_material']}")
                                        if quality.get("storage_condition"): st.write(f"**Storage:** {quality['storage_condition']}")
                                        if quality.get("measurement_method"): st.write(f"**Measurement method:** {quality['measurement_method']}")
                                        if quality.get("notes"): st.write(f"**Notes:** {quality['notes']}")
                                    if photos:
                                        photo_cols = st.columns(min(3, len(photos)))
                                        for photo_index, photo in enumerate(photos):
                                            with photo_cols[photo_index % len(photo_cols)]:
                                                if Path(photo["file_path"]).exists():
                                                    st.image(photo["file_path"], use_container_width=True)
                                                if photo.get("caption"): st.caption(photo["caption"])
                                    else:
                                        st.caption("No photo evidence has been added to this lot.")

                            st.caption(f"Response status: {response['status']}")

                            deal = get_deal_for_response(response["response_id"])
                            if deal is None and response["status"] not in {"Declined", "Withdrawn"}:
                                if st.button(
                                    "Open negotiation",
                                    type="primary",
                                    key=f"open_deal_{response['response_id']}",
                                    use_container_width=True,
                                ):
                                    try:
                                        deal_id = create_or_get_deal(
                                            response["response_id"],
                                            buyer_id,
                                        )
                                        st.success(f"Negotiation Deal-{deal_id:05d} opened.")
                                        st.rerun()
                                    except ValueError as error:
                                        st.error(str(error))
                            elif deal:
                                st.markdown("**Negotiation started**")
                                _render_deal_status(deal["status"])
                                st.caption(
                                    "Open Negotiations & Sales to review terms, send a counter-offer, "
                                    "confirm the purchase, and coordinate pickup."
                                )

    st.caption(
        "RFQs are marketplace requests, not purchase contracts. Final quality, price, "
        "transport, payment and delivery terms must be agreed by the buyer and farmer."
    )


elif page == "Transactions":

    user = current_user()
    actor_id = user["user_id"]
    actor_role = user["role"]

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Marketplace transaction center · Industry workflow</div>
            <div class="page-title">Negotiate, confirm, and complete residue sales.</div>
            <div class="page-copy">
                Keep every buyer–farmer discussion, agreed quantity, price, confirmation,
                pickup detail and completion event connected to the same residue lot.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "Contact details are intentionally hidden during negotiation. "
        "They become visible only after both buyer and farmer confirm the same terms."
    )

    deals = (
        get_deals_for_buyer(actor_id)
        if actor_role == "buyer"
        else get_deals_for_farmer(actor_id)
    )

    if not deals:
        st.info(
            "No active negotiations yet. "
            "Buyers can open a negotiation from a farmer response; farmers can respond from Buyer Requests."
        )
    else:
        for deal in deals:
            with st.container(border=True):
                top_left, top_right = st.columns([3.2, 1])
                with top_left:
                    st.markdown(
                        f"### Deal-{deal['deal_id']:05d} · AW-{deal['listing_id']:05d}"
                    )
                    st.caption(
                        f"{format_crop_name(deal['crop'])} · {deal['residue']} · "
                        f"{deal['quantity_kg'] if 'quantity_kg' in deal else deal['agreed_quantity_kg']:,.0f} kg"
                    )
                with top_right:
                    _render_deal_status(deal["status"])

                if actor_role == "buyer":
                    st.write(
                        f"**Farmer:** {get_user_contact(deal['farmer_id'])['full_name'] if get_user_contact(deal['farmer_id']) else deal['farmer_id']}"
                    )
                else:
                    st.write(f"**Buyer:** {deal['buyer_name']}")

                _render_deal_messages(deal["deal_id"], actor_id)
                st.divider()
                _render_deal_actions(deal, actor_id, actor_role)


elif page == "Economic Value":

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Value estimation · Step 04</div>
            <div class="page-title">Estimate the economic potential of residue.</div>
            <div class="page-copy">
                Enter an estimated residue quantity and utilization pathway to calculate
                a prototype gross-value range based on the project's value model.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    crop_options = [
        "rice", "wheat", "sugarcane", "maize", "cotton", "coconut",
        "jute", "banana", "soyabean", "jowar", "Pearl_millet(bajra)"
    ]

    selected_crop = st.selectbox(
        "Crop",
        crop_options,
        format_func=format_crop_name,
    )

    waste_info, recommendations = analyze_crop(selected_crop)

    st.markdown(
        f"""
        <div class="context-card">
            <div class="context-label">Selected crop · associated residue</div>
            <div class="context-value">{format_crop_name(selected_crop)} · {waste_info["waste_name"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="manual-note"><strong>Price basis:</strong> static prototype ranges from the project knowledge base. They are not live market prices and should be replaced with validated local data for deployment.</div>',
        unsafe_allow_html=True,
    )

    use_options = [item["name"] for item in recommendations]

    selected_use = st.selectbox(
        "Potential utilization method",
        use_options,
    )

    quantity = st.number_input(
        "Waste quantity (kg)",
        min_value=1.0,
        value=500.0,
        step=10.0,
    )

    if st.button(
        "Estimate Value",
        type="primary",
        use_container_width=True,
    ):
        try:
            result = estimate_value(
                crop_name=selected_crop,
                waste_name=waste_info["waste_name"],
                use_name=selected_use,
                quantity_kg=quantity,
            )

            st.divider()

            col1, col2, col3 = st.columns(3, gap="medium")

            with col1:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Quantity</div>
                        <div class="metric-value">{result["quantity_kg"]:,.0f} kg</div>
                        <div class="metric-note">Residue quantity entered</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col2:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Estimated value / kg</div>
                        <div class="metric-value">₹{result["min_price_per_kg"]} – ₹{result["max_price_per_kg"]}</div>
                        <div class="metric-note">Prototype price range</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col3:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Potential gross value</div>
                        <div class="metric-value">{result["display_range"]}</div>
                        <div class="metric-note">Estimated range</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.write("")
            st.markdown('<div class="section-kicker">Estimated outcome</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-heading">Value breakdown</div>', unsafe_allow_html=True)
            st.caption(
                f"Estimated range for {result['quantity_kg']:,.0f} kg of {waste_info['waste_name']} "
                f"using {selected_use}."
            )

            breakdown_data = {
                "Scenario": ["Lower Estimate", "Upper Estimate"],
                "Value": [result["minimum_value"], result["maximum_value"]],
            }

            chart = px.bar(
                breakdown_data,
                x="Scenario",
                y="Value",
                text="Value",
            )
            chart.update_traces(
                texttemplate="₹%{text:,.0f}",
                textposition="outside",
            )
            chart.update_layout(
                yaxis_title="Estimated Gross Value (₹)",
                xaxis_title="",
                height=350,
                margin=dict(l=10, r=25, t=25, b=20),
            )
            style_chart(chart)
            st.plotly_chart(chart, use_container_width=True)

            st.markdown(
                """
                <div class="about-callout">
                    <strong>Interpretation:</strong> This estimate represents potential gross
                    value under the prototype's assumed price range. It is not a guaranteed
                    selling price, profit estimate, or farmer income forecast.
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.write("")
            st.markdown(
                """
                <div class="disclaimer">
                    <strong>Important:</strong><br><br>
                    This is a prototype estimate, not a live market quotation or guaranteed farmer income.
                    Actual value may vary depending on residue quality, moisture, contamination,
                    transportation, local demand, processing requirements and buyer.
                </div>
                """,
                unsafe_allow_html=True,
            )

        except ValueError as error:
            st.error(str(error))

# ============================================================
# ABOUT PROJECT
# ============================================================

elif page == "About Project":

    st.markdown(
        """
        <div class="page-hero">
            <div class="page-kicker">Project overview · Academic prototype</div>
            <div class="page-title">AgriWaste AI</div>
            <div class="page-copy">
                An AI-assisted agricultural-residue management platform that helps farmers
                identify residue, understand potential uses, estimate prototype value, prepare
                it for buyer requirements, and connect with potential buyers through a structured
                marketplace workflow.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-kicker">Project objective</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-heading">Turning agricultural residue into a usable resource.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="about-callout">
            AgriWaste AI is designed to reduce the information gap between farmers who generate
            agricultural residue and organizations or buyers that may be able to use it. The
            prototype combines AI-assisted identification, utilization guidance, economic-value
            estimation, buyer requirements, preparation guidance, matching, negotiation and
            transaction tracking in one workflow.
        </div>
        """,
        unsafe_allow_html=True,
    )

    problem_col, solution_col = st.columns(2, gap="large")
    with problem_col:
        st.markdown(
            """
            <div class="about-block">
                <h3>The problem</h3>
                <p>
                    Agricultural residues can be burned, discarded or left underutilized even when
                    they may have useful applications. Farmers may also lack accessible information
                    about alternative uses, quality requirements, potential buyers and the economic
                    value of available residue.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with solution_col:
        st.markdown(
            """
            <div class="about-block">
                <h3>The proposed solution</h3>
                <p>
                    AgriWaste AI starts with residue identification and recommendations, then extends
                    into a farmer-buyer marketplace. Farmers can create residue lots, compare them
                    with buyer requirements, receive preparation guidance, submit responses, negotiate,
                    confirm deals and record handover information.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-kicker">Core capabilities</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">One workflow from residue identification to transaction.</div>', unsafe_allow_html=True)

    capabilities = [
        ("01", "AI residue identification", "Upload an image, receive a model prediction and confidence information, and correct the working identification when the farmer disagrees with the model."),
        ("02", "Utilization recommendations", "Explore potential pathways such as composting, mushroom cultivation, animal feed, biofuel, biomass products and industrial applications."),
        ("03", "Prototype economic value", "Use the available residue information to generate an indicative value estimate. The result is clearly presented as a prototype estimate rather than a guaranteed market price."),
        ("04", "Farmer residue lots", "Record quantity, form, moisture, processing, location, pickup availability and notes for a specific residue lot."),
        ("05", "Buyer RFQs", "Buyers can state minimum quantity, accepted forms, maximum moisture, processing, packaging, pickup and other requirements."),
        ("06", "Smart buyer matching", "Compare a farmer's active lot with open buyer requirements and classify the result as ready to respond, preparation needed or not currently compatible."),
        ("07", "Preparation & response assistance", "Show the requirements that still need attention and generate an editable, factual response draft for the farmer to review before submission."),
        ("08", "Negotiation & transaction workflow", "Support responses, negotiation, mutual confirmation, pickup scheduling, handover recording and transaction completion."),
        ("09", "Quality & evidence", "Store farmer-reported quality information and photo evidence alongside the relevant residue lot without presenting it as independent verification."),
        ("10", "Lot traceability", "Maintain an auditable history of important listing and transaction events associated with a residue lot."),
        ("11", "Human-in-the-loop AI", "Keep the original AI prediction separate from any farmer correction so future model-improvement workflows can distinguish model output from user feedback."),
        ("12", "Multilingual farmer interface", "Provide farmer-facing navigation and key interactions in English, Hindi, Odia and Bengali."),
    ]
    for i in range(0, len(capabilities), 3):
        cols = st.columns(3, gap="medium")
        for col, (number, title, text) in zip(cols, capabilities[i:i+3]):
            with col:
                st.markdown(
                    f"""
                    <div class="validation-card" style="height:100%;box-sizing:border-box;">
                        <div class="validation-status">{number} · Capability</div>
                        <h4 style="margin:.35rem 0 .35rem 0;">{title}</h4>
                        <div style="opacity:.76;line-height:1.55;">{text}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.write("")
    st.markdown('<div class="section-kicker">End-to-end workflow</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">From a residue photo to a completed marketplace transaction.</div>', unsafe_allow_html=True)

    workflow = [
        ("1", "Identify", "Farmer uploads a residue image and reviews the AI prediction."),
        ("2", "Understand", "The system provides utilization pathways and an indicative economic-value estimate."),
        ("3", "List", "Farmer creates a structured residue lot with quantity, form, moisture and processing information."),
        ("4", "Match", "The lot is compared with open buyer requirements."),
        ("5", "Prepare", "The farmer reviews outstanding buyer requirements and prepares the lot when needed."),
        ("6", "Respond", "The farmer reviews and edits a factual response before submitting it to the buyer."),
        ("7", "Agree", "Buyer and farmer negotiate and mutually confirm the transaction."),
        ("8", "Handover", "Pickup and actual handover information are recorded."),
        ("9", "Complete", "The transaction is marked complete and the lot history remains traceable."),
    ]
    for i in range(0, len(workflow), 3):
        cols = st.columns(3, gap="medium")
        for col, (number, title, text) in zip(cols, workflow[i:i+3]):
            with col:
                st.markdown(
                    f"""
                    <div class="about-block" style="height:100%;box-sizing:border-box;">
                        <div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#5c8061;">STEP {number}</div>
                        <h3 style="margin:.35rem 0 .35rem 0;">{title}</h3>
                        <p>{text}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.write("")
    st.markdown('<div class="section-kicker">Technology</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Built as a practical AI and marketplace prototype.</div>', unsafe_allow_html=True)

    technology = [
        ("Frontend", "Streamlit"),
        ("Machine Learning", "TensorFlow / Keras"),
        ("Computer Vision", "EfficientNetB0"),
        ("Data Processing", "Pandas / NumPy"),
        ("Visualization", "Plotly"),
        ("Database", "SQLite"),
        ("Language", "Python"),
        ("Dataset", "Kaggle agricultural crop image dataset"),
    ]
    tech_cols = st.columns(4, gap="medium")
    for index, (technology_name, technology_value) in enumerate(technology):
        with tech_cols[index % 4]:
            st.markdown(
                f"""
                <div class="tech-card">
                    <div class="tech-name">{technology_name}</div>
                    <div class="tech-value">{technology_value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown('<div class="section-kicker">System architecture</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">AI intelligence connected to a farmer-buyer marketplace.</div>', unsafe_allow_html=True)

    architecture_html = """
    <div class="agri-architecture">
      <div class="arch-subtitle">The prototype connects the AI pipeline, farmer workflow and marketplace transaction lifecycle.</div>
      <div class="arch-flow">
        <div class="arch-card"><div class="arch-icon">AI</div><div class="arch-title">AI identification</div><div class="arch-copy">Image classification, confidence and human correction.</div></div>
        <div class="arch-card"><div class="arch-icon">R</div><div class="arch-title">Residue intelligence</div><div class="arch-copy">Utilization recommendations and prototype value estimation.</div></div>
        <div class="arch-card"><div class="arch-icon">L</div><div class="arch-title">Farmer lot</div><div class="arch-copy">Quantity, form, moisture, processing, location and evidence.</div></div>
        <div class="arch-card"><div class="arch-icon">M</div><div class="arch-title">Smart marketplace</div><div class="arch-copy">RFQs, matching, preparation guidance and responses.</div></div>
        <div class="arch-card"><div class="arch-icon">T</div><div class="arch-title">Transaction</div><div class="arch-copy">Negotiation, confirmation, pickup, handover and traceability.</div></div>
      </div>
    </div>
    """
    st.markdown(architecture_html, unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="section-kicker">Quality and trust principles</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Keep model output, farmer input and verified events distinct.</div>', unsafe_allow_html=True)
    trust_items = [
        ("AI output", "The model prediction and confidence are retained as model-generated information."),
        ("Farmer input", "Corrections, quality observations and uploaded photos are identified as farmer-provided information."),
        ("Transaction record", "Deal confirmations, actual handover quantity and other workflow events are recorded separately."),
        ("Prototype limitation", "The platform does not independently verify residue ownership, quality, weight, market price or buyer suitability unless a future verification process is added."),
    ]
    for title, text in trust_items:
        st.markdown(
            f'<div class="validation-card"><div class="validation-status">{title}</div><div style="opacity:.78;line-height:1.55;">{text}</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-kicker">Real-world validation</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">What should be validated before deployment?</div>', unsafe_allow_html=True)
    validation_items = [
        ("01", "Model validation", "Evaluate on held-out, field-like images and report class-wise performance for the intended deployment population."),
        ("02", "Residue validation", "Confirm crop-to-residue mappings and utilization guidance with agricultural domain sources or expert review."),
        ("03", "Market validation", "Replace prototype value estimates with verified local buyer quotations or a maintained market dataset."),
        ("04", "Buyer validation", "Move from prototype buyer requirements toward verified organizations, requirements and location-aware matching."),
        ("05", "Operational validation", "Test pickup, quality verification, dispute handling, payments and identity controls before real transactions."),
    ]
    for number, title, text in validation_items:
        st.markdown(
            f'<div class="validation-card"><div class="validation-status">{number} · Validation target</div><h4 style="margin:.3rem 0 .2rem 0;">{title}</h4><div style="opacity:.72;line-height:1.55;">{text}</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown(
        """
        <div class="about-callout">
            <strong>Academic prototype:</strong> AgriWaste AI is a decision-support and marketplace
            prototype. AI predictions, utilization recommendations, suitability matches and economic
            estimates should be validated against real-world residue quality, market conditions,
            processing requirements, logistics and local demand before practical deployment.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown(
        """
        <div class="footer">
            <strong>AgriWaste AI</strong> · Agricultural Residue Intelligence & Marketplace Platform<br>
            Industry Prototype · Version 0.6
        </div>
        """,
        unsafe_allow_html=True,
    )
