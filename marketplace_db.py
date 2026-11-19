"""AgriWaste AI marketplace persistence layer.

Development-stage persistence for the industry-oriented prototype.

Design goals:
- preserve existing SQLite data through additive migrations
- keep farmer listings and buyer leads traceable
- use explicit lifecycle statuses instead of deleting business records
- record important status changes in an audit table
- keep a farmer_id boundary ready for authenticated accounts later

SQLite is appropriate for local development/demo use. Production deployment
should move this schema to a managed PostgreSQL service and enforce
authentication, authorization and transactional controls at the API layer.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from marketplace import DEMO_BUYERS

DB_PATH = Path("data") / "agriwaste_marketplace.db"
DEMO_FARMER_ID = "DEMO-FARMER-001"

LISTING_STATUSES = (
    "Draft",
    "Published",
    "Under Review",
    "Negotiation",
    "Reserved",
    "Sold",
    "Cancelled",
)

INTEREST_STATUSES = (
    "Saved",
    "Contacted",
    "Negotiation",
    "Accepted",
    "Declined",
    "Withdrawn",
)

LISTING_TRANSITIONS = {
    "Draft": {"Published", "Cancelled"},
    "Published": {"Under Review", "Negotiation", "Cancelled"},
    "Under Review": {"Published", "Negotiation", "Cancelled"},
    "Negotiation": {"Published", "Reserved", "Cancelled"},
    "Reserved": {"Negotiation", "Sold", "Cancelled"},
    "Sold": set(),
    "Cancelled": set(),
}

INTEREST_TRANSITIONS = {
    "Saved": {"Contacted", "Declined", "Withdrawn"},
    "Contacted": {"Negotiation", "Declined", "Withdrawn"},
    "Negotiation": {"Accepted", "Declined", "Withdrawn"},
    "Accepted": {"Withdrawn"},
    "Declined": set(),
    "Withdrawn": set(),
}

DEAL_STATUSES = (
    "Negotiation",
    "Buyer Confirmed",
    "Farmer Confirmed",
    "Confirmed",
    "Pickup Scheduled",
    "Handover Review",
    "Picked Up",
    "Completed",
    "Cancelled",
)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _seed_demo_buyers(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS n FROM buyers").fetchone()["n"]
    if count:
        return

    for buyer in DEMO_BUYERS:
        conn.execute(
            """
            INSERT INTO buyers (
                buyer_id, buyer_name, buyer_type, crop, residue,
                accepted_forms, max_moisture_pct, min_quantity_kg,
                processing_required, packaging, pickup_available,
                location, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                buyer.buyer_id,
                buyer.buyer_name,
                buyer.buyer_type,
                buyer.crop,
                buyer.residue,
                ",".join(buyer.accepted_forms),
                buyer.max_moisture_pct,
                buyer.min_quantity_kg,
                buyer.processing_required,
                buyer.packaging,
                int(buyer.pickup_available),
                buyer.location,
                buyer.notes,
            ),
        )


def initialize_database() -> None:
    """Create the schema and perform safe additive migrations."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS buyers (
                buyer_id TEXT PRIMARY KEY,
                buyer_name TEXT NOT NULL,
                buyer_type TEXT NOT NULL,
                crop TEXT NOT NULL,
                residue TEXT NOT NULL,
                accepted_forms TEXT NOT NULL,
                max_moisture_pct REAL,
                min_quantity_kg REAL NOT NULL,
                processing_required TEXT NOT NULL,
                packaging TEXT NOT NULL,
                pickup_available INTEGER NOT NULL DEFAULT 0,
                location TEXT NOT NULL,
                notes TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS farmer_listings (
                listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                crop TEXT NOT NULL,
                residue TEXT NOT NULL,
                quantity_kg REAL NOT NULL CHECK(quantity_kg > 0),
                form TEXT NOT NULL CHECK(form IN ('raw','dry','processed')),
                moisture_pct REAL,
                processing TEXT DEFAULT '',
                location TEXT NOT NULL,
                pickup_available INTEGER NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Draft',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS buyer_interests (
                interest_id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER,
                buyer_id TEXT NOT NULL,
                buyer_name TEXT NOT NULL,
                crop TEXT NOT NULL,
                residue TEXT NOT NULL,
                quantity_kg REAL NOT NULL,
                form TEXT NOT NULL,
                moisture_pct REAL,
                location TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Saved',
                created_at TEXT NOT NULL,
                FOREIGN KEY(listing_id) REFERENCES farmer_listings(listing_id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                actor_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listing_quality_checks (
                quality_id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL UNIQUE,
                farmer_id TEXT NOT NULL,
                cleanliness TEXT DEFAULT '',
                foreign_material TEXT DEFAULT '',
                storage_condition TEXT DEFAULT '',
                measurement_method TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Farmer reported',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(listing_id) REFERENCES farmer_listings(listing_id)
            );

            CREATE TABLE IF NOT EXISTS listing_evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                farmer_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                caption TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(listing_id) REFERENCES farmer_listings(listing_id)
            );

            CREATE TABLE IF NOT EXISTS prediction_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ai_prediction TEXT NOT NULL,
                ai_confidence REAL NOT NULL,
                corrected_crop TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'AI image',
                actor_id TEXT NOT NULL DEFAULT 'DEMO-FARMER-001',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preparation_records (
                preparation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                farmer_id TEXT NOT NULL,
                buyer_id TEXT,
                target_form TEXT,
                target_moisture_pct REAL,
                target_quantity_kg REAL,
                packaging TEXT,
                completed_steps TEXT NOT NULL DEFAULT '',
                final_moisture_pct REAL,
                notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'In Progress',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(listing_id, farmer_id),
                FOREIGN KEY(listing_id) REFERENCES farmer_listings(listing_id)
            );

            CREATE TABLE IF NOT EXISTS buyer_rfqs (
                rfq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id TEXT NOT NULL,
                buyer_name TEXT NOT NULL,
                crop TEXT NOT NULL,
                residue TEXT NOT NULL,
                accepted_forms TEXT NOT NULL,
                max_moisture_pct REAL,
                min_quantity_kg REAL NOT NULL CHECK(min_quantity_kg > 0),
                processing_required TEXT DEFAULT '',
                packaging TEXT DEFAULT '',
                pickup_required INTEGER NOT NULL DEFAULT 0,
                location TEXT NOT NULL,
                notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Open'
                    CHECK(status IN ('Open','Closed','Cancelled')),
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rfq_responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id INTEGER NOT NULL,
                farmer_id TEXT NOT NULL,
                listing_id INTEGER NOT NULL,
                offered_quantity_kg REAL NOT NULL CHECK(offered_quantity_kg > 0),
                offered_price_per_kg REAL,
                message TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Submitted'
                    CHECK(status IN ('Submitted','Accepted','Declined','Withdrawn')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(rfq_id, farmer_id, listing_id),
                FOREIGN KEY(rfq_id) REFERENCES buyer_rfqs(rfq_id),
                FOREIGN KEY(listing_id) REFERENCES farmer_listings(listing_id)
            );

            CREATE TABLE IF NOT EXISTS residue_deals (
                deal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id INTEGER NOT NULL UNIQUE,
                rfq_id INTEGER NOT NULL,
                listing_id INTEGER NOT NULL,
                buyer_id TEXT NOT NULL,
                farmer_id TEXT NOT NULL,
                agreed_quantity_kg REAL NOT NULL CHECK(agreed_quantity_kg > 0),
                agreed_price_per_kg REAL,
                pickup_date TEXT,
                pickup_notes TEXT DEFAULT '',
                buyer_confirmed INTEGER NOT NULL DEFAULT 0,
                farmer_confirmed INTEGER NOT NULL DEFAULT 0,
                buyer_pickup_confirmed INTEGER NOT NULL DEFAULT 0,
                farmer_pickup_confirmed INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Negotiation',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(response_id) REFERENCES rfq_responses(response_id),
                FOREIGN KEY(rfq_id) REFERENCES buyer_rfqs(rfq_id),
                FOREIGN KEY(listing_id) REFERENCES farmer_listings(listing_id)
            );

            CREATE TABLE IF NOT EXISTS deal_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id INTEGER NOT NULL,
                sender_id TEXT NOT NULL,
                sender_role TEXT NOT NULL CHECK(sender_role IN ('buyer','farmer')),
                message_type TEXT NOT NULL DEFAULT 'Message'
                    CHECK(message_type IN ('Message','Counter Offer','Confirmation','Pickup Update')),
                proposed_quantity_kg REAL,
                proposed_price_per_kg REAL,
                proposed_pickup_date TEXT,
                message TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(deal_id) REFERENCES residue_deals(deal_id)
            );
            """
        )

        # Additive migration for databases created by v1/v2/v3/v4.
        _add_column_if_missing(conn, "farmer_listings", "farmer_id", f"TEXT NOT NULL DEFAULT '{DEMO_FARMER_ID}'")
        _add_column_if_missing(conn, "farmer_listings", "updated_at", "TEXT")
        _add_column_if_missing(conn, "buyer_interests", "farmer_id", f"TEXT NOT NULL DEFAULT '{DEMO_FARMER_ID}'")
        _add_column_if_missing(conn, "buyer_interests", "updated_at", "TEXT")

        # Handover verification fields. These are additive so existing
        # marketplace databases remain usable.
        _add_column_if_missing(conn, "residue_deals", "actual_quantity_kg", "REAL")
        _add_column_if_missing(conn, "residue_deals", "actual_moisture_pct", "REAL")
        _add_column_if_missing(conn, "residue_deals", "handover_notes", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "residue_deals", "buyer_handover_confirmed", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "residue_deals", "farmer_handover_confirmed", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "residue_deals", "completed_at", "TEXT")

        conn.execute(
            "UPDATE farmer_listings SET updated_at = COALESCE(updated_at, created_at)"
        )
        conn.execute(
            "UPDATE buyer_interests SET updated_at = COALESCE(updated_at, created_at)"
        )

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_listings_farmer_status
                ON farmer_listings(farmer_id, status);
            CREATE INDEX IF NOT EXISTS idx_listings_crop_residue
                ON farmer_listings(crop, residue);
            CREATE INDEX IF NOT EXISTS idx_interests_farmer_status
                ON buyer_interests(farmer_id, status);
            CREATE INDEX IF NOT EXISTS idx_interests_listing
                ON buyer_interests(listing_id);
            CREATE INDEX IF NOT EXISTS idx_audit_entity
                ON audit_events(entity_type, entity_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_quality_listing
                ON listing_quality_checks(listing_id);
            CREATE INDEX IF NOT EXISTS idx_evidence_listing
                ON listing_evidence(listing_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_preparation_farmer
                ON preparation_records(farmer_id, status);
            CREATE INDEX IF NOT EXISTS idx_preparation_listing
                ON preparation_records(listing_id);

            CREATE INDEX IF NOT EXISTS idx_rfqs_buyer_status
                ON buyer_rfqs(buyer_id, status);
            CREATE INDEX IF NOT EXISTS idx_rfqs_crop_status
                ON buyer_rfqs(crop, status);
            CREATE INDEX IF NOT EXISTS idx_rfq_responses_rfq
                ON rfq_responses(rfq_id, status);
            CREATE INDEX IF NOT EXISTS idx_rfq_responses_farmer
                ON rfq_responses(farmer_id, status);

            CREATE INDEX IF NOT EXISTS idx_deals_buyer_status
                ON residue_deals(buyer_id, status);
            CREATE INDEX IF NOT EXISTS idx_deals_farmer_status
                ON residue_deals(farmer_id, status);
            CREATE INDEX IF NOT EXISTS idx_deal_messages_deal
                ON deal_messages(deal_id, created_at);
            """
        )

        _seed_demo_buyers(conn)



def get_preparation(
    listing_id: int,
    farmer_id: str = DEMO_FARMER_ID,
) -> Optional[Dict[str, Any]]:
    """Return the preparation record for a farmer-owned listing."""
    initialize_database()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM preparation_records
            WHERE listing_id = ? AND farmer_id = ?
            """,
            (listing_id, farmer_id),
        ).fetchone()
    return dict(row) if row else None


def create_or_update_preparation(
    listing_id: int,
    farmer_id: str,
    buyer_id: Optional[str],
    target_form: Optional[str],
    target_moisture_pct: Optional[float],
    target_quantity_kg: Optional[float],
    packaging: str,
    completed_steps: str,
    final_moisture_pct: Optional[float],
    notes: str,
    status: str = "In Progress",
) -> int:
    """
    Upsert a preparation plan for a farmer-owned listing.

    The database stores the farmer's progress and final measured value,
    while buyer requirements remain sourced from the buyer record.
    """
    initialize_database()

    if status not in {"In Progress", "Ready for Buyer Review", "Completed"}:
        raise ValueError(f"Unsupported preparation status: {status}")

    with _connect() as conn:
        owner = conn.execute(
            "SELECT farmer_id FROM farmer_listings WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if not owner or owner["farmer_id"] != farmer_id:
            raise ValueError("Listing does not belong to the active farmer workspace.")

        existing = conn.execute(
            """
            SELECT preparation_id
            FROM preparation_records
            WHERE listing_id = ? AND farmer_id = ?
            """,
            (listing_id, farmer_id),
        ).fetchone()

        if existing:
            preparation_id = int(existing["preparation_id"])
            conn.execute(
                """
                UPDATE preparation_records
                SET buyer_id = ?,
                    target_form = ?,
                    target_moisture_pct = ?,
                    target_quantity_kg = ?,
                    packaging = ?,
                    completed_steps = ?,
                    final_moisture_pct = ?,
                    notes = ?,
                    status = ?,
                    updated_at = datetime('now','localtime')
                WHERE preparation_id = ?
                  AND listing_id = ?
                  AND farmer_id = ?
                """,
                (
                    buyer_id,
                    target_form,
                    target_moisture_pct,
                    target_quantity_kg,
                    packaging,
                    completed_steps,
                    final_moisture_pct,
                    notes,
                    status,
                    preparation_id,
                    listing_id,
                    farmer_id,
                ),
            )
            _audit(
                conn,
                "preparation",
                str(preparation_id),
                "updated",
                None,
                status,
                farmer_id,
            )
            return preparation_id

        cursor = conn.execute(
            """
            INSERT INTO preparation_records (
                listing_id, farmer_id, buyer_id, target_form,
                target_moisture_pct, target_quantity_kg, packaging,
                completed_steps, final_moisture_pct, notes, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      datetime('now','localtime'), datetime('now','localtime'))
            """,
            (
                listing_id,
                farmer_id,
                buyer_id,
                target_form,
                target_moisture_pct,
                target_quantity_kg,
                packaging,
                completed_steps,
                final_moisture_pct,
                notes,
                status,
            ),
        )
        preparation_id = int(cursor.lastrowid)
        _audit(
            conn,
            "preparation",
            str(preparation_id),
            "created",
            None,
            status,
            farmer_id,
        )
        return preparation_id



def create_rfq(
    buyer_id: str,
    buyer_name: str,
    crop: str,
    residue: str,
    accepted_forms: List[str],
    max_moisture_pct: Optional[float],
    min_quantity_kg: float,
    processing_required: str,
    packaging: str,
    pickup_required: bool,
    location: str,
    notes: str,
    expires_at: Optional[str] = None,
) -> int:
    """Create a buyer RFQ with the buyer identity attached to the record."""
    initialize_database()

    if not buyer_id or not buyer_name:
        raise ValueError("Buyer identity is required.")
    if not crop or not residue:
        raise ValueError("Crop and residue are required.")
    if not accepted_forms:
        raise ValueError("Select at least one accepted residue form.")
    if min_quantity_kg <= 0:
        raise ValueError("Minimum quantity must be greater than zero.")
    if max_moisture_pct is not None and not 0 <= max_moisture_pct <= 100:
        raise ValueError("Maximum moisture must be between 0 and 100%.")
    if not location.strip():
        raise ValueError("Buyer location is required.")

    forms = ",".join(sorted({str(x).strip().lower() for x in accepted_forms if str(x).strip()}))

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO buyer_rfqs (
                buyer_id, buyer_name, crop, residue, accepted_forms,
                max_moisture_pct, min_quantity_kg, processing_required,
                packaging, pickup_required, location, notes, status,
                expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?,
                      datetime('now','localtime'), datetime('now','localtime'))
            """,
            (
                buyer_id,
                buyer_name.strip(),
                crop.strip(),
                residue.strip(),
                forms,
                max_moisture_pct,
                min_quantity_kg,
                processing_required.strip(),
                packaging.strip(),
                int(bool(pickup_required)),
                location.strip(),
                notes.strip(),
                expires_at,
            ),
        )
        rfq_id = int(cursor.lastrowid)
        _audit(conn, "rfq", str(rfq_id), "created", None, "Open", buyer_id)
        return rfq_id


def _rfq_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["accepted_forms"] = [
        x.strip().lower()
        for x in str(item.get("accepted_forms", "")).split(",")
        if x.strip()
    ]
    item["pickup_required"] = bool(item.get("pickup_required"))
    return item


def get_open_rfqs(crop: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return open RFQs, optionally filtered by crop."""
    initialize_database()
    with _connect() as conn:
        if crop:
            rows = conn.execute(
                """
                SELECT *
                FROM buyer_rfqs
                WHERE status = 'Open' AND crop = ?
                ORDER BY created_at DESC
                """,
                (crop,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM buyer_rfqs
                WHERE status = 'Open'
                ORDER BY created_at DESC
                """
            ).fetchall()
    return [_rfq_row_to_dict(row) for row in rows]


def get_buyer_rfqs(buyer_id: str) -> List[Dict[str, Any]]:
    """Return RFQs owned by the authenticated buyer."""
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM buyer_rfqs
            WHERE buyer_id = ?
            ORDER BY created_at DESC
            """,
            (buyer_id,),
        ).fetchall()
    return [_rfq_row_to_dict(row) for row in rows]


def get_rfq(rfq_id: int) -> Optional[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM buyer_rfqs WHERE rfq_id = ?",
            (rfq_id,),
        ).fetchone()
    return _rfq_row_to_dict(row) if row else None


def create_rfq_response(
    rfq_id: int,
    farmer_id: str,
    listing_id: int,
    offered_quantity_kg: float,
    offered_price_per_kg: Optional[float],
    message: str,
) -> int:
    """Submit a farmer response only for an open RFQ and farmer-owned listing."""
    initialize_database()

    if offered_quantity_kg <= 0:
        raise ValueError("Offered quantity must be greater than zero.")
    if offered_price_per_kg is not None and offered_price_per_kg < 0:
        raise ValueError("Offered price cannot be negative.")

    with _connect() as conn:
        rfq = conn.execute(
            "SELECT * FROM buyer_rfqs WHERE rfq_id = ?",
            (rfq_id,),
        ).fetchone()
        if not rfq:
            raise ValueError("RFQ could not be found.")
        if rfq["status"] != "Open":
            raise ValueError("This RFQ is no longer open for responses.")

        listing = conn.execute(
            """
            SELECT *
            FROM farmer_listings
            WHERE listing_id = ? AND farmer_id = ?
            """,
            (listing_id, farmer_id),
        ).fetchone()
        if not listing:
            raise ValueError("The selected residue lot does not belong to the active farmer.")
        if listing["status"] in {"Sold", "Cancelled"}:
            raise ValueError("This residue lot is no longer available.")

        if offered_quantity_kg > float(listing["quantity_kg"]):
            raise ValueError("Offered quantity cannot exceed the quantity available in the selected lot.")

        accepted_forms = {
            x.strip().lower()
            for x in str(rfq["accepted_forms"]).split(",")
            if x.strip()
        }
        if accepted_forms and listing["form"].lower() not in accepted_forms:
            raise ValueError(
                "The selected lot's current form is not one of the forms accepted by this RFQ."
            )

        if offered_quantity_kg < float(rfq["min_quantity_kg"]):
            raise ValueError(
                f"The response quantity must be at least {float(rfq['min_quantity_kg']):,.0f} kg "
                "for this RFQ."
            )

        if rfq["max_moisture_pct"] is not None:
            if listing["moisture_pct"] is None:
                raise ValueError(
                    "This RFQ has a moisture limit. Record a measured moisture value "
                    "for the selected lot before responding."
                )
            if float(listing["moisture_pct"]) > float(rfq["max_moisture_pct"]):
                raise ValueError(
                    f"The selected lot moisture ({float(listing['moisture_pct']):.1f}%) "
                    f"is above the RFQ limit ({float(rfq['max_moisture_pct']):.1f}%). "
                    "Prepare and re-measure the lot before responding."
                )

        existing = conn.execute(
            """
            SELECT response_id
            FROM rfq_responses
            WHERE rfq_id = ? AND farmer_id = ? AND listing_id = ?
            """,
            (rfq_id, farmer_id, listing_id),
        ).fetchone()

        if existing:
            raise ValueError("You have already responded to this RFQ with this residue lot.")

        cursor = conn.execute(
            """
            INSERT INTO rfq_responses (
                rfq_id, farmer_id, listing_id, offered_quantity_kg,
                offered_price_per_kg, message, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Submitted',
                      datetime('now','localtime'), datetime('now','localtime'))
            """,
            (
                rfq_id,
                farmer_id,
                listing_id,
                offered_quantity_kg,
                offered_price_per_kg,
                message.strip(),
            ),
        )
        response_id = int(cursor.lastrowid)
        _audit(
            conn,
            "rfq_response",
            str(response_id),
            "created",
            None,
            "Submitted",
            farmer_id,
        )
        return response_id


def get_rfq_responses_for_farmer(farmer_id: str) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.*, q.buyer_name, q.crop, q.residue,
                   q.min_quantity_kg, q.max_moisture_pct
            FROM rfq_responses r
            JOIN buyer_rfqs q ON q.rfq_id = r.rfq_id
            WHERE r.farmer_id = ?
            ORDER BY r.created_at DESC
            """,
            (farmer_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_rfq_responses_for_buyer(buyer_id: str, rfq_id: Optional[int] = None) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        if rfq_id is None:
            rows = conn.execute(
                """
                SELECT r.*, q.buyer_name, q.crop, q.residue,
                       q.min_quantity_kg, q.max_moisture_pct
                FROM rfq_responses r
                JOIN buyer_rfqs q ON q.rfq_id = r.rfq_id
                WHERE q.buyer_id = ?
                ORDER BY r.created_at DESC
                """,
                (buyer_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT r.*, q.buyer_name, q.crop, q.residue,
                       q.min_quantity_kg, q.max_moisture_pct
                FROM rfq_responses r
                JOIN buyer_rfqs q ON q.rfq_id = r.rfq_id
                WHERE q.buyer_id = ? AND r.rfq_id = ?
                ORDER BY r.created_at DESC
                """,
                (buyer_id, rfq_id),
            ).fetchall()
    return [dict(row) for row in rows]




def get_deal_for_response(response_id: int) -> Optional[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM residue_deals WHERE response_id = ?",
            (response_id,),
        ).fetchone()
    return dict(row) if row else None


def create_or_get_deal(
    response_id: int,
    buyer_id: str,
) -> int:
    """Open a negotiation for a farmer response owned by the buyer."""
    initialize_database()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT r.*, q.buyer_id, q.status AS rfq_status
            FROM rfq_responses r
            JOIN buyer_rfqs q ON q.rfq_id = r.rfq_id
            WHERE r.response_id = ?
            """,
            (response_id,),
        ).fetchone()

        if not row:
            raise ValueError("Farmer response could not be found.")
        if row["buyer_id"] != buyer_id:
            raise ValueError("You are not authorized to negotiate this response.")
        if row["rfq_status"] != "Open":
            raise ValueError("This buyer request is no longer open.")
        if row["status"] in {"Declined", "Withdrawn"}:
            raise ValueError("This farmer response is no longer available for negotiation.")

        existing = conn.execute(
            "SELECT deal_id FROM residue_deals WHERE response_id = ?",
            (response_id,),
        ).fetchone()
        if existing:
            return int(existing["deal_id"])

        # A physical residue lot can have many marketplace responses, but only
        # one active transaction may reserve it at a time.
        competing = conn.execute(
            """
            SELECT deal_id, status
            FROM residue_deals
            WHERE listing_id = ?
              AND deal_id != COALESCE(?, -1)
              AND status IN (
                  'Negotiation',
                  'Buyer Confirmed',
                  'Farmer Confirmed',
                  'Confirmed',
                  'Pickup Scheduled'
              )
            ORDER BY deal_id DESC
            LIMIT 1
            """,
            (row["listing_id"], None),
        ).fetchone()
        if competing:
            raise ValueError(
                "This residue lot is already in an active buyer negotiation. "
                "Please choose another available lot."
            )

        listing = conn.execute(
            "SELECT status FROM farmer_listings WHERE listing_id = ?",
            (row["listing_id"],),
        ).fetchone()
        if not listing or listing["status"] in {"Sold", "Cancelled"}:
            raise ValueError("The residue lot is no longer available.")

        # Reserve the lot for the negotiation state, preventing a silent
        # multi-buyer race once a buyer starts a serious negotiation.
        if listing["status"] == "Published":
            conn.execute(
                """
                UPDATE farmer_listings
                SET status = 'Negotiation', updated_at = datetime('now','localtime')
                WHERE listing_id = ? AND status = 'Published'
                """,
                (row["listing_id"],),
            )
            _audit(
                conn, "listing", str(row["listing_id"]),
                "status_changed", "Published", "Negotiation", buyer_id
            )

        cursor = conn.execute(
            """
            INSERT INTO residue_deals (
                response_id, rfq_id, listing_id, buyer_id, farmer_id,
                agreed_quantity_kg, agreed_price_per_kg, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Negotiation',
                      datetime('now','localtime'), datetime('now','localtime'))
            """,
            (
                response_id,
                row["rfq_id"],
                row["listing_id"],
                buyer_id,
                row["farmer_id"],
                row["offered_quantity_kg"],
                row["offered_price_per_kg"],
            ),
        )
        deal_id = int(cursor.lastrowid)

        if row["message"]:
            conn.execute(
                """
                INSERT INTO deal_messages (
                    deal_id, sender_id, sender_role, message_type,
                    proposed_quantity_kg, proposed_price_per_kg, message, created_at
                ) VALUES (?, ?, 'farmer', 'Message', ?, ?, ?, datetime('now','localtime'))
                """,
                (
                    deal_id,
                    row["farmer_id"],
                    row["offered_quantity_kg"],
                    row["offered_price_per_kg"],
                    row["message"],
                ),
            )

        _audit(conn, "deal", str(deal_id), "created", None, "Negotiation", buyer_id)
        return deal_id


def get_deal(deal_id: int) -> Optional[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()
    return dict(row) if row else None


def get_deals_for_buyer(buyer_id: str) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*, q.buyer_name, q.crop, q.residue,
                   r.offered_quantity_kg, r.offered_price_per_kg,
                   l.form, l.moisture_pct, l.location AS farmer_location
            FROM residue_deals d
            JOIN buyer_rfqs q ON q.rfq_id = d.rfq_id
            JOIN rfq_responses r ON r.response_id = d.response_id
            JOIN farmer_listings l ON l.listing_id = d.listing_id
            WHERE d.buyer_id = ?
            ORDER BY d.updated_at DESC
            """,
            (buyer_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_deals_for_farmer(farmer_id: str) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*, q.buyer_name, q.crop, q.residue,
                   r.offered_quantity_kg, r.offered_price_per_kg,
                   l.form, l.moisture_pct, l.location AS farmer_location
            FROM residue_deals d
            JOIN buyer_rfqs q ON q.rfq_id = d.rfq_id
            JOIN rfq_responses r ON r.response_id = d.response_id
            JOIN farmer_listings l ON l.listing_id = d.listing_id
            WHERE d.farmer_id = ?
            ORDER BY d.updated_at DESC
            """,
            (farmer_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_deal_messages(deal_id: int, actor_id: str) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        allowed = conn.execute(
            """
            SELECT 1
            FROM residue_deals
            WHERE deal_id = ? AND (buyer_id = ? OR farmer_id = ?)
            """,
            (deal_id, actor_id, actor_id),
        ).fetchone()
        if not allowed:
            raise ValueError("You are not authorized to view this negotiation.")

        rows = conn.execute(
            """
            SELECT *
            FROM deal_messages
            WHERE deal_id = ?
            ORDER BY message_id ASC
            """,
            (deal_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def send_deal_message(
    deal_id: int,
    sender_id: str,
    sender_role: str,
    message: str,
    proposed_quantity_kg: Optional[float] = None,
    proposed_price_per_kg: Optional[float] = None,
    proposed_pickup_date: Optional[str] = None,
) -> int:
    """Send a message/counter-offer and make the proposed terms the current terms."""
    initialize_database()

    if sender_role not in {"buyer", "farmer"}:
        raise ValueError("Invalid negotiation participant role.")
    if not message.strip() and proposed_quantity_kg is None and proposed_price_per_kg is None:
        raise ValueError("Add a message or proposed terms.")

    with _connect() as conn:
        deal = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()
        if not deal:
            raise ValueError("Negotiation could not be found.")
        if sender_id not in {deal["buyer_id"], deal["farmer_id"]}:
            raise ValueError("You are not authorized to negotiate this deal.")
        if deal["status"] in {"Completed", "Cancelled", "Picked Up"}:
            raise ValueError("This transaction is no longer open for negotiation.")

        quantity = proposed_quantity_kg
        price = proposed_price_per_kg

        if quantity is not None and quantity <= 0:
            raise ValueError("Proposed quantity must be greater than zero.")
        if price is not None and price < 0:
            raise ValueError("Proposed price cannot be negative.")

        if quantity is not None:
            listing = conn.execute(
                "SELECT quantity_kg FROM farmer_listings WHERE listing_id = ?",
                (deal["listing_id"],),
            ).fetchone()
            if not listing or quantity > float(listing["quantity_kg"]):
                raise ValueError("Proposed quantity exceeds the residue currently available.")

        cursor = conn.execute(
            """
            INSERT INTO deal_messages (
                deal_id, sender_id, sender_role, message_type,
                proposed_quantity_kg, proposed_price_per_kg,
                proposed_pickup_date, message, created_at
            ) VALUES (?, ?, ?, 'Counter Offer', ?, ?, ?, ?, datetime('now','localtime'))
            """,
            (
                deal_id,
                sender_id,
                sender_role,
                quantity,
                price,
                proposed_pickup_date,
                message.strip(),
            ),
        )

        # A counter-offer becomes the current terms only for fields actually supplied.
        conn.execute(
            """
            UPDATE residue_deals
            SET agreed_quantity_kg = COALESCE(?, agreed_quantity_kg),
                agreed_price_per_kg = COALESCE(?, agreed_price_per_kg),
                pickup_date = COALESCE(?, pickup_date),
                pickup_notes = CASE WHEN ? <> '' THEN ? ELSE pickup_notes END,
                buyer_confirmed = 0,
                farmer_confirmed = 0,
                status = 'Negotiation',
                updated_at = datetime('now','localtime')
            WHERE deal_id = ?
            """,
            (
                quantity,
                price,
                proposed_pickup_date,
                message.strip(),
                message.strip(),
                deal_id,
            ),
        )
        _audit(conn, "deal", str(deal_id), "counter_offer", deal["status"], "Negotiation", sender_id)
        return int(cursor.lastrowid)


def confirm_deal(
    deal_id: int,
    actor_id: str,
    actor_role: str,
) -> str:
    """Record one party's confirmation; only mutual confirmation creates a confirmed deal."""
    initialize_database()

    with _connect() as conn:
        deal = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()
        if not deal:
            raise ValueError("Negotiation could not be found.")
        if actor_role not in {"buyer", "farmer"}:
            raise ValueError("Invalid participant role.")
        if actor_id not in {deal["buyer_id"], deal["farmer_id"]}:
            raise ValueError("You are not authorized to confirm this transaction.")
        if deal["status"] in {"Completed", "Cancelled", "Picked Up"}:
            raise ValueError("This transaction is already closed.")

        if actor_role == "buyer":
            conn.execute(
                """
                UPDATE residue_deals
                SET buyer_confirmed = 1,
                    status = CASE
                        WHEN farmer_confirmed = 1 THEN 'Confirmed'
                        ELSE 'Buyer Confirmed'
                    END,
                    updated_at = datetime('now','localtime')
                WHERE deal_id = ?
                """,
                (deal_id,),
            )
        else:
            conn.execute(
                """
                UPDATE residue_deals
                SET farmer_confirmed = 1,
                    status = CASE
                        WHEN buyer_confirmed = 1 THEN 'Confirmed'
                        ELSE 'Farmer Confirmed'
                    END,
                    updated_at = datetime('now','localtime')
                WHERE deal_id = ?
                """,
                (deal_id,),
            )

        updated = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()

        if updated["status"] == "Confirmed":
            conn.execute(
                """
                UPDATE rfq_responses
                SET status = 'Accepted', updated_at = datetime('now','localtime')
                WHERE response_id = ?
                """,
                (deal["response_id"],),
            )
            listing = conn.execute(
                "SELECT status FROM farmer_listings WHERE listing_id = ?",
                (deal["listing_id"],),
            ).fetchone()

            if not listing:
                raise ValueError("The residue lot could not be found.")

            # Confirm that another active deal has not already reserved this
            # physical lot. This check makes the reservation operation safe
            # even if the UI was left open in another browser/session.
            competing = conn.execute(
                """
                SELECT deal_id, status
                FROM residue_deals
                WHERE listing_id = ?
                  AND deal_id != ?
                  AND status IN (
                      'Negotiation',
                      'Buyer Confirmed',
                      'Farmer Confirmed',
                      'Confirmed',
                      'Pickup Scheduled'
                  )
                LIMIT 1
                """,
                (deal["listing_id"], deal_id),
            ).fetchone()

            if competing:
                raise ValueError(
                    "This residue lot is already reserved or under active negotiation "
                    "with another buyer."
                )

            if listing["status"] in {"Published", "Under Review", "Negotiation"}:
                conn.execute(
                    """
                    UPDATE farmer_listings
                    SET status = 'Reserved', updated_at = datetime('now','localtime')
                    WHERE listing_id = ?
                      AND status IN ('Published', 'Under Review', 'Negotiation')
                    """,
                    (deal["listing_id"],),
                )
                _audit(
                    conn, "listing", str(deal["listing_id"]),
                    "status_changed", listing["status"], "Reserved", actor_id
                )
            elif listing["status"] == "Reserved":
                # The lot is already reserved. It is valid only when this deal
                # is the active transaction holding it.
                holder = conn.execute(
                    """
                    SELECT deal_id
                    FROM residue_deals
                    WHERE listing_id = ?
                      AND deal_id != ?
                      AND status IN (
                          'Negotiation',
                          'Buyer Confirmed',
                          'Farmer Confirmed',
                          'Confirmed',
                          'Pickup Scheduled'
                      )
                    LIMIT 1
                    """,
                    (deal["listing_id"], deal_id),
                ).fetchone()
                if holder:
                    raise ValueError(
                        "This residue lot is already reserved by another active transaction."
                    )
            elif listing["status"] in {"Sold", "Cancelled"}:
                raise ValueError(
                    "This residue lot is no longer available for purchase."
                )
            else:
                raise ValueError(
                    f"The residue lot is in an unsupported state: {listing['status']}."
                )

            _audit(conn, "deal", str(deal_id), "mutually_confirmed", deal["status"], "Confirmed", actor_id)

        else:
            _audit(conn, "deal", str(deal_id), "participant_confirmed", deal["status"], updated["status"], actor_id)

        return str(updated["status"])


def schedule_pickup(
    deal_id: int,
    actor_id: str,
    pickup_date: str,
    pickup_notes: str = "",
) -> None:
    initialize_database()
    with _connect() as conn:
        deal = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()
        if not deal:
            raise ValueError("Transaction could not be found.")
        if actor_id not in {deal["buyer_id"], deal["farmer_id"]}:
            raise ValueError("You are not authorized to schedule this pickup.")
        if deal["status"] != "Confirmed":
            raise ValueError("Both parties must confirm the deal before pickup can be scheduled.")
        if not pickup_date.strip():
            raise ValueError("Enter a pickup date.")

        conn.execute(
            """
            UPDATE residue_deals
            SET pickup_date = ?, pickup_notes = ?, status = 'Pickup Scheduled',
                updated_at = datetime('now','localtime')
            WHERE deal_id = ?
            """,
            (pickup_date.strip(), pickup_notes.strip(), deal_id),
        )
        _audit(conn, "deal", str(deal_id), "pickup_scheduled", deal["status"], "Pickup Scheduled", actor_id)


def submit_handover(
    deal_id: int,
    actor_id: str,
    actual_quantity_kg: float,
    actual_moisture_pct: Optional[float],
    handover_notes: str = "",
) -> None:
    """
    Record the measured quantity/quality at physical handover.

    The farmer submits the physical handover record. The buyer then reviews
    and confirms the delivered lot. No universal moisture target is imposed;
    buyer-specific requirements remain the source of truth.
    """
    initialize_database()

    if actual_quantity_kg <= 0:
        raise ValueError("Actual delivered quantity must be greater than 0.")
    if actual_moisture_pct is not None and not 0 <= actual_moisture_pct <= 100:
        raise ValueError("Moisture must be between 0% and 100%.")

    with _connect() as conn:
        deal = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()

        if not deal:
            raise ValueError("Transaction could not be found.")
        if actor_id != deal["farmer_id"]:
            raise ValueError("Only the farmer can submit the handover measurement.")
        if deal["status"] != "Pickup Scheduled":
            raise ValueError("Handover measurements can be submitted after pickup is scheduled.")

        listing = conn.execute(
            "SELECT quantity_kg FROM farmer_listings WHERE listing_id = ?",
            (deal["listing_id"],),
        ).fetchone()
        if not listing:
            raise ValueError("The residue lot could not be found.")

        if actual_quantity_kg > float(listing["quantity_kg"]):
            raise ValueError(
                f"Actual delivered quantity cannot exceed the available lot "
                f"({float(listing['quantity_kg']):,.0f} kg)."
            )

        conn.execute(
            """
            UPDATE residue_deals
            SET actual_quantity_kg = ?,
                actual_moisture_pct = ?,
                handover_notes = ?,
                farmer_handover_confirmed = 1,
                buyer_handover_confirmed = 0,
                status = 'Handover Review',
                updated_at = datetime('now','localtime')
            WHERE deal_id = ?
            """,
            (
                float(actual_quantity_kg),
                actual_moisture_pct,
                handover_notes.strip(),
                deal_id,
            ),
        )

        _audit(
            conn,
            "deal",
            str(deal_id),
            "handover_submitted",
            deal["status"],
            "Handover Review",
            actor_id,
        )


def confirm_handover(
    deal_id: int,
    actor_id: str,
    actor_role: str,
) -> str:
    """
    Buyer verifies the physical handover.

    The buyer's confirmation is the inventory-changing event: the agreed
    physical quantity is removed from the active listing. The original lot
    record remains in the database for history/audit.
    """
    initialize_database()

    with _connect() as conn:
        deal = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()

        if not deal:
            raise ValueError("Transaction could not be found.")
        if actor_role != "buyer" or actor_id != deal["buyer_id"]:
            raise ValueError("Only the buyer can confirm the received residue.")
        if deal["status"] != "Handover Review":
            raise ValueError("The farmer must submit the handover details before you can confirm receipt.")
        if not deal["actual_quantity_kg"] or float(deal["actual_quantity_kg"]) <= 0:
            raise ValueError("A valid delivered quantity is required before confirmation.")

        listing = conn.execute(
            "SELECT quantity_kg, status FROM farmer_listings WHERE listing_id = ?",
            (deal["listing_id"],),
        ).fetchone()
        if not listing:
            raise ValueError("The residue lot could not be found.")

        actual_qty = float(deal["actual_quantity_kg"])
        available_qty = float(listing["quantity_kg"])

        if actual_qty > available_qty:
            raise ValueError("Delivered quantity is greater than the quantity currently available.")

        conn.execute(
            """
            UPDATE residue_deals
            SET buyer_handover_confirmed = 1,
                status = 'Completed',
                completed_at = datetime('now','localtime'),
                updated_at = datetime('now','localtime')
            WHERE deal_id = ?
            """,
            (deal_id,),
        )

        if actual_qty >= available_qty:
            conn.execute(
                """
                UPDATE farmer_listings
                SET status = 'Sold',
                    updated_at = datetime('now','localtime')
                WHERE listing_id = ?
                """,
                (deal["listing_id"],),
            )
            _audit(
                conn,
                "listing",
                str(deal["listing_id"]),
                "sold",
                listing["status"],
                "Sold",
                actor_id,
            )
        else:
            remaining = available_qty - actual_qty
            conn.execute(
                """
                UPDATE farmer_listings
                SET quantity_kg = ?,
                    status = 'Published',
                    updated_at = datetime('now','localtime')
                WHERE listing_id = ?
                """,
                (remaining, deal["listing_id"]),
            )
            _audit(
                conn,
                "listing",
                str(deal["listing_id"]),
                "quantity_reduced_after_handover",
                listing["status"],
                f"Published:{remaining:g}kg",
                actor_id,
            )

        _audit(
            conn,
            "deal",
            str(deal_id),
            "handover_confirmed",
            "Handover Review",
            "Completed",
            actor_id,
        )

        return "Completed"


def get_transaction_receipt(deal_id: int) -> Optional[Dict[str, Any]]:
    """Return a read-only transaction receipt view for completed/verified deals."""
    initialize_database()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                d.*,
                q.buyer_name,
                q.crop,
                q.residue,
                q.location AS buyer_location,
                l.location AS farmer_location,
                l.form,
                l.moisture_pct AS listed_moisture_pct
            FROM residue_deals d
            JOIN buyer_rfqs q ON q.rfq_id = d.rfq_id
            JOIN farmer_listings l ON l.listing_id = d.listing_id
            WHERE d.deal_id = ?
            """,
            (deal_id,),
        ).fetchone()

    return dict(row) if row else None


def mark_pickup_complete(
    deal_id: int,
    actor_id: str,
    actor_role: str,
) -> None:
    """
    Mark the physical handover as complete.

    Buyer confirmation is sufficient to move the lot out of active inventory:
    the database preserves the lot as Sold for audit/history instead of deleting it.
    """
    initialize_database()

    with _connect() as conn:
        deal = conn.execute(
            "SELECT * FROM residue_deals WHERE deal_id = ?",
            (deal_id,),
        ).fetchone()
        if not deal:
            raise ValueError("Transaction could not be found.")
        if actor_id not in {deal["buyer_id"], deal["farmer_id"]}:
            raise ValueError("You are not authorized to confirm pickup.")
        if actor_role not in {"buyer", "farmer"}:
            raise ValueError("Invalid participant role.")
        if deal["status"] not in {"Confirmed", "Pickup Scheduled"}:
            raise ValueError("The deal must be mutually confirmed before pickup can be completed.")

        if actor_role == "buyer":
            conn.execute(
                """
                UPDATE residue_deals
                SET buyer_pickup_confirmed = 1,
                    status = 'Completed',
                    updated_at = datetime('now','localtime')
                WHERE deal_id = ?
                """,
                (deal_id,),
            )
        else:
            conn.execute(
                """
                UPDATE residue_deals
                SET farmer_pickup_confirmed = 1,
                    status = CASE
                        WHEN buyer_pickup_confirmed = 1 THEN 'Completed'
                        ELSE 'Picked Up'
                    END,
                    updated_at = datetime('now','localtime')
                WHERE deal_id = ?
                """,
                (deal_id,),
            )

        # A buyer-confirmed pickup removes the quantity from active farmer inventory.
        listing = conn.execute(
            "SELECT quantity_kg, status FROM farmer_listings WHERE listing_id = ?",
            (deal["listing_id"],),
        ).fetchone()
        if not listing:
            raise ValueError("The residue lot could not be found.")

        if float(deal["agreed_quantity_kg"]) >= float(listing["quantity_kg"]):
            # Keep the original sold quantity for audit/history. The listing
            # disappears from active inventory because its status becomes Sold;
            # quantity_kg must remain positive because the schema enforces that.
            conn.execute(
                """
                UPDATE farmer_listings
                SET status = 'Sold',
                    updated_at = datetime('now','localtime')
                WHERE listing_id = ?
                """,
                (deal["listing_id"],),
            )
            _audit(
                conn, "listing", str(deal["listing_id"]),
                "sold", listing["status"], "Sold", actor_id
            )
        else:
            remaining = float(listing["quantity_kg"]) - float(deal["agreed_quantity_kg"])
            conn.execute(
                """
                UPDATE farmer_listings
                SET quantity_kg = ?, status = 'Published',
                    updated_at = datetime('now','localtime')
                WHERE listing_id = ?
                """,
                (remaining, deal["listing_id"]),
            )
            _audit(
                conn, "listing", str(deal["listing_id"]),
                "quantity_reduced_after_pickup",
                listing["status"],
                f"Published:{remaining:g}kg",
                actor_id,
            )

        _audit(
            conn, "deal", str(deal_id),
            "pickup_confirmed",
            deal["status"],
            "Picked Up",
            actor_id,
        )



def get_buyer_listings(crop: str) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM buyers WHERE crop = ? ORDER BY buyer_name",
            (crop,),
        ).fetchall()
    return [_buyer_row_to_dict(row) for row in rows]


def _buyer_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["accepted_forms"] = [x for x in data["accepted_forms"].split(",") if x]
    data["pickup_available"] = bool(data["pickup_available"])
    return data


def _audit(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: Optional[str],
    new_value: Optional[str],
    actor_id: str = DEMO_FARMER_ID,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (
            entity_type, entity_id, action, old_value, new_value, actor_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """,
        (entity_type, str(entity_id), action, old_value, new_value, actor_id),
    )


def create_listing(listing: Dict[str, Any], farmer_id: str = DEMO_FARMER_ID) -> int:
    initialize_database()
    status = listing.get("status", "Published")
    if status not in LISTING_STATUSES:
        raise ValueError(f"Unsupported listing status: {status}")

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO farmer_listings (
                farmer_id, crop, residue, quantity_kg, form, moisture_pct,
                processing, location, pickup_available, notes, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
            """,
            (
                farmer_id,
                listing["crop"],
                listing["residue"],
                float(listing["quantity_kg"]),
                listing["form"],
                listing.get("moisture_pct"),
                listing.get("processing", ""),
                listing["location"],
                int(bool(listing.get("pickup", False))),
                listing.get("notes", ""),
                status,
            ),
        )
        listing_id = int(cursor.lastrowid)
        _audit(conn, "listing", str(listing_id), "created", None, status, farmer_id)
        return listing_id


def get_listing(listing_id: int, farmer_id: str = DEMO_FARMER_ID) -> Optional[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM farmer_listings WHERE listing_id = ? AND farmer_id = ?",
            (listing_id, farmer_id),
        ).fetchone()
    return dict(row) if row else None


def save_interest(
    interest: Dict[str, Any],
    listing_id: Optional[int] = None,
    farmer_id: str = DEMO_FARMER_ID,
) -> int:
    initialize_database()
    with _connect() as conn:
        if listing_id is not None:
            owner = conn.execute(
                "SELECT farmer_id FROM farmer_listings WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()
            if not owner or owner["farmer_id"] != farmer_id:
                raise ValueError("Listing does not belong to the active farmer workspace.")
            listing_row = conn.execute(
                "SELECT crop, residue, status FROM farmer_listings WHERE listing_id = ? AND farmer_id = ?",
                (listing_id, farmer_id),
            ).fetchone()
            if not listing_row:
                raise ValueError("Listing could not be loaded.")
            if listing_row["crop"] != interest["crop"] or listing_row["residue"] != interest["residue"]:
                raise ValueError("Buyer lead does not match the selected residue listing.")
            if listing_row["status"] in {"Sold", "Cancelled"}:
                raise ValueError("Buyer leads cannot be added to a sold or cancelled listing.")

        cursor = conn.execute(
            """
            INSERT INTO buyer_interests (
                listing_id, farmer_id, buyer_id, buyer_name, crop, residue,
                quantity_kg, form, moisture_pct, location, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Saved', datetime('now','localtime'), datetime('now','localtime'))
            """,
            (
                listing_id,
                farmer_id,
                interest["buyer_id"],
                interest["buyer_name"],
                interest["crop"],
                interest["residue"],
                float(interest["quantity_kg"]),
                interest["form"],
                interest.get("moisture_pct"),
                interest["location"],
            ),
        )
        interest_id = int(cursor.lastrowid)
        _audit(conn, "buyer_interest", str(interest_id), "created", None, "Saved", farmer_id)
        return interest_id


def get_recent_listings(limit: int = 10, farmer_id: str = DEMO_FARMER_ID) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM farmer_listings WHERE farmer_id = ? ORDER BY listing_id DESC LIMIT ?",
            (farmer_id, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_recent_interests(limit: int = 10, farmer_id: str = DEMO_FARMER_ID) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM buyer_interests WHERE farmer_id = ? ORDER BY interest_id DESC LIMIT ?",
            (farmer_id, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_farmer_dashboard(farmer_id: str = DEMO_FARMER_ID) -> Dict[str, List[Dict[str, Any]]]:
    """Return the farmer's own listings and buyer leads only."""
    return {
        "listings": get_recent_listings(limit=100, farmer_id=farmer_id),
        "interests": get_recent_interests(limit=100, farmer_id=farmer_id),
    }


def update_listing_status(
    listing_id: int,
    new_status: str,
    farmer_id: str = DEMO_FARMER_ID,
) -> None:
    initialize_database()
    if new_status not in LISTING_STATUSES:
        raise ValueError(f"Unsupported listing status: {new_status}")

    with _connect() as conn:
        row = conn.execute(
            "SELECT status FROM farmer_listings WHERE listing_id = ? AND farmer_id = ?",
            (listing_id, farmer_id),
        ).fetchone()
        if not row:
            raise ValueError("Listing not found in the active farmer workspace.")

        old_status = row["status"]
        if old_status == new_status:
            return
        if new_status not in LISTING_TRANSITIONS.get(old_status, set()):
            raise ValueError(f"Invalid listing transition: {old_status} → {new_status}")

        conn.execute(
            "UPDATE farmer_listings SET status = ?, updated_at = datetime('now','localtime') WHERE listing_id = ? AND farmer_id = ?",
            (new_status, listing_id, farmer_id),
        )
        _audit(conn, "listing", str(listing_id), "status_changed", old_status, new_status, farmer_id)


def update_interest_status(
    interest_id: int,
    new_status: str,
    farmer_id: str = DEMO_FARMER_ID,
) -> None:
    initialize_database()
    if new_status not in INTEREST_STATUSES:
        raise ValueError(f"Unsupported buyer-lead status: {new_status}")

    with _connect() as conn:
        row = conn.execute(
            "SELECT status FROM buyer_interests WHERE interest_id = ? AND farmer_id = ?",
            (interest_id, farmer_id),
        ).fetchone()
        if not row:
            raise ValueError("Buyer lead not found in the active farmer workspace.")

        old_status = row["status"]
        if old_status == new_status:
            return
        if new_status not in INTEREST_TRANSITIONS.get(old_status, set()):
            raise ValueError(f"Invalid buyer-lead transition: {old_status} → {new_status}")

        conn.execute(
            "UPDATE buyer_interests SET status = ?, updated_at = datetime('now','localtime') WHERE interest_id = ? AND farmer_id = ?",
            (new_status, interest_id, farmer_id),
        )
        _audit(conn, "buyer_interest", str(interest_id), "status_changed", old_status, new_status, farmer_id)


def get_audit_events(
    entity_type: str,
    entity_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY event_id DESC LIMIT ?
            """,
            (entity_type, str(entity_id), max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_listing_quality(listing_id: int, farmer_id: str = DEMO_FARMER_ID) -> Optional[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        owner = conn.execute(
            "SELECT farmer_id FROM farmer_listings WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if not owner or owner["farmer_id"] != farmer_id:
            raise ValueError("Listing does not belong to the active farmer workspace.")
        row = conn.execute(
            "SELECT * FROM listing_quality_checks WHERE listing_id = ? AND farmer_id = ?",
            (listing_id, farmer_id),
        ).fetchone()
    return dict(row) if row else None


def save_listing_quality(
    listing_id: int,
    farmer_id: str = DEMO_FARMER_ID,
    cleanliness: str = "",
    foreign_material: str = "",
    storage_condition: str = "",
    measurement_method: str = "",
    notes: str = "",
) -> int:
    initialize_database()
    with _connect() as conn:
        owner = conn.execute(
            "SELECT farmer_id FROM farmer_listings WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if not owner or owner["farmer_id"] != farmer_id:
            raise ValueError("Listing does not belong to the active farmer workspace.")

        existing = conn.execute(
            "SELECT quality_id FROM listing_quality_checks WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE listing_quality_checks
                   SET cleanliness = ?, foreign_material = ?, storage_condition = ?,
                       measurement_method = ?, notes = ?, status = 'Farmer reported',
                       updated_at = datetime('now','localtime')
                   WHERE listing_id = ? AND farmer_id = ?""",
                (cleanliness, foreign_material, storage_condition, measurement_method, notes, listing_id, farmer_id),
            )
            quality_id = int(existing["quality_id"])
            _audit(conn, "listing_quality", str(listing_id), "updated", "Farmer reported", "Farmer reported", farmer_id)
        else:
            cur = conn.execute(
                """INSERT INTO listing_quality_checks (
                    listing_id, farmer_id, cleanliness, foreign_material, storage_condition,
                    measurement_method, notes, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Farmer reported', datetime('now','localtime'), datetime('now','localtime'))""",
                (listing_id, farmer_id, cleanliness, foreign_material, storage_condition, measurement_method, notes),
            )
            quality_id = int(cur.lastrowid)
            _audit(conn, "listing_quality", str(listing_id), "created", None, "Farmer reported", farmer_id)
    return quality_id


def add_listing_evidence(
    listing_id: int,
    file_name: str,
    file_path: str,
    caption: str = "",
    farmer_id: str = DEMO_FARMER_ID,
) -> int:
    initialize_database()
    with _connect() as conn:
        owner = conn.execute(
            "SELECT farmer_id FROM farmer_listings WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if not owner or owner["farmer_id"] != farmer_id:
            raise ValueError("Listing does not belong to the active farmer workspace.")
        cur = conn.execute(
            """INSERT INTO listing_evidence (
                listing_id, farmer_id, file_name, file_path, caption, created_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))""",
            (listing_id, farmer_id, file_name, file_path, caption),
        )
        evidence_id = int(cur.lastrowid)
        _audit(conn, "listing", str(listing_id), "evidence_added", None, file_name, farmer_id)
        return evidence_id


def get_listing_evidence(listing_id: int, farmer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    initialize_database()
    with _connect() as conn:
        if farmer_id is None:
            rows = conn.execute(
                "SELECT * FROM listing_evidence WHERE listing_id = ? ORDER BY evidence_id DESC",
                (listing_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM listing_evidence WHERE listing_id = ? AND farmer_id = ? ORDER BY evidence_id DESC",
                (listing_id, farmer_id),
            ).fetchall()
    return [dict(row) for row in rows]


initialize_database()


def save_prediction_feedback(
    ai_prediction: str,
    ai_confidence: float,
    corrected_crop: str,
    notes: str = "",
    source: str = "AI image",
    actor_id: str = DEMO_FARMER_ID,
) -> int:
    """Store a human correction without overwriting the original AI result."""
    initialize_database()
    from datetime import datetime
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO prediction_feedback (
                ai_prediction, ai_confidence, corrected_crop, source,
                actor_id, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ai_prediction),
                float(ai_confidence),
                str(corrected_crop),
                str(source),
                str(actor_id),
                str(notes or ""),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)


def get_prediction_feedback(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent human corrections for prototype review/training analysis."""
    initialize_database()
    safe_limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT feedback_id, ai_prediction, ai_confidence, corrected_crop,
                   source, actor_id, notes, created_at
            FROM prediction_feedback
            ORDER BY feedback_id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]
