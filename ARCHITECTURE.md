# AgriWaste AI — Industry-Oriented Architecture

## Product goal

AgriWaste AI is being developed as a farmer-first agricultural-residue intelligence and marketplace platform.

The product flow is:

```text
Crop / residue identification
        ↓
Residue intelligence
        ↓
Utilization pathways
        ↓
Buyer requirements
        ↓
Requirement matching
        ↓
Preparation guidance
        ↓
Buyer-ready lot
        ↓
Marketplace listing
        ↓
Buyer lead / negotiation
        ↓
Reservation
        ↓
Sale completion
```

## Current release

The current development release adds:

- persistent SQLite marketplace storage for local development
- farmer listing lifecycle states
- buyer-lead lifecycle states
- farmer dashboard
- lot-linked buyer leads
- audit events for listing and buyer-lead status changes
- additive database migration for earlier marketplace databases
- explicit transition guards to prevent invalid lifecycle changes
- a `farmer_id` boundary ready for authenticated accounts
- UI contrast/accessibility checks as part of the development workflow

## Production target architecture

```text
                         Web / Mobile Client
                                │
                                ▼
                         Authentication Layer
                                │
                                ▼
                              API Layer
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
      AI Service          Marketplace Service    User Service
          │                     │                     │
          ▼                     ▼                     ▼
     Model Registry       PostgreSQL DB        Identity Provider
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
             ▼                  ▼                  ▼
          Logistics          Quality          Notification
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ▼
                         Audit / Observability
```

## Domain boundaries

### Farmer

- create and manage residue lots
- view preparation requirements
- review buyer leads
- move a lot through its permitted lifecycle
- retain lot history and transaction evidence

### Buyer

- create residue requirements
- specify accepted form, moisture, quantity and packaging
- review eligible farmer lots
- submit interest or quotation
- progress a negotiation

### Marketplace

- match residue characteristics against buyer requirements
- distinguish hard incompatibilities from preparation gaps
- maintain listing and lead lifecycle state
- keep an auditable record of important changes

### AI / Decision Support

- identify crop from an image
- map crop to residue information
- recommend utilization pathways
- provide confidence and limitations

AI output must remain decision support. It must not silently override buyer specifications or verified quality measurements.

## Data principles

1. **Traceability:** a buyer lead should be linked to a specific residue lot whenever possible.
2. **No destructive business deletes:** completed/cancelled records should remain available for history and audit purposes.
3. **Explicit states:** listing and lead status changes are controlled by an allowed transition map.
4. **Ownership boundary:** database queries use `farmer_id`; authentication can later supply the real identity.
5. **Verified data separation:** demo buyer requirements must never be presented as verified businesses.
6. **Measured quality:** moisture and other quality attributes should come from measured/declared lot data, not assumptions.
7. **Human confirmation:** buyer requirements remain authoritative over generic preparation guidance.

## Current vs production infrastructure

| Area | Current development | Production target |
|---|---|---|
| UI | Streamlit | Web/mobile client + API |
| Database | SQLite | Managed PostgreSQL |
| Authentication | Demo farmer workspace | Identity provider + MFA where appropriate |
| Authorization | Farmer ID boundary | Role/tenant-based access control |
| Buyers | Seeded demo requirements | Verified buyer organizations |
| Matching | Transparent rule-based prototype | Versioned matching service |
| AI | Local TensorFlow/Keras model | Versioned model service/registry |
| Audit | SQLite audit table | Centralized immutable audit/observability pipeline |
| Files | Local project storage | Object storage with access controls |
| Notifications | UI feedback | Email/SMS/WhatsApp/push through approved providers |
| Payments | Not implemented | Payment provider + reconciliation workflow |

## Engineering rule for future changes

Every new feature should be reviewed in this order:

1. user value and farmer workflow
2. data model
3. authorization/ownership boundary
4. validation and failure states
5. lifecycle/audit implications
6. UI accessibility and contrast
7. automated tests
8. integration testing
9. production migration path

A feature is not considered complete merely because its Streamlit page renders.
