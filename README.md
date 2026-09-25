# FLT — Flight & Visa Management

Production-grade Odoo 19 Community module for flight bookings, visas,
passports, travel documents, cancellations/refunds and a secure customer
portal.

**Technical name:** `flt_flight_visa_management`
**Prefix:** `flt.` / `flt_`
**Author:** Automater
**License:** OPL-1

## Purpose

Gives internal staff a single place to manage customer flight bookings
(including multi-segment journeys), visas, passports and travel documents,
with a configurable cancellation-policy engine and refund workflow — and
gives customers a secure self-service portal to view their own travel
information and request cancellations.

## Features

- Multi-segment flight bookings with a full status lifecycle (Draft →
  Reserved → Confirmed → Ticketed → Checked In → Completed / Cancelled /
  Airline Cancelled / No Show)
- Configurable, extensible cancellation policies (percentage or fixed
  charge, by airline/class/time-before-departure)
- Cancellation request workflow with staff approval and computed refund
  amounts
- Airline-initiated cancellation recording with mandatory reason and
  automatic customer notification
- Visa and passport records with configurable-threshold expiry status and
  batched, duplicate-safe renewal reminders
- Generic document management on top of `ir.attachment`
- Generic notification center (`flt.notification`) driving `mail.template`
  emails, with a provider-agnostic hook for future WhatsApp/SMS modules
- Secure customer portal: dashboard, flights, visas, passports, documents,
  cancellation requests, notifications — all server-side, own-records-only
- Backend KPI dashboard and native list/pivot/graph reports
- A single centralized daily cron processes all expiry/reminder logic

## Dependencies

`base`, `mail`, `portal`, `web` (all Odoo 19 Community core modules — no
third-party Python or JS packages required).

## Installation

1. Copy `flt_flight_visa_management` into your Odoo 19 addons path.
2. Update the apps list and install **Flight & Visa Management**.
3. Assign users to **FLT User**, **FLT Manager**, or **FLT Administrator**
   under Settings → Users & Companies → Groups (or via the module's own
   security groups).

## Configuration

Settings → Flight & Visa Management (also reachable from
Flight & Visa → Configuration → Settings):

- **Visa Types** — comma-separated list shown in the Visa Type dropdown.
- **Visa/Passport Reminder Days** — comma-separated day offsets before
  expiry to send a reminder (defaults: visa `90,60,30,15,7,1`, passport
  `180,90,60,30`).
- **Passport "Expiring Soon" Threshold** — days before expiry a passport is
  auto-flagged Expiring Soon.
- **Default Auto-cancel on Approval** — default for new Cancellation Policy
  records.

Cancellation policies themselves are configured under Flight & Visa →
Cancellation → Policies (three sample rules — 0–24h/100%, 24–72h/50%,
72h+/₹2,000 fixed — are installed as starting data and can be freely
edited, reordered, or scoped to a specific airline/class).

## User Roles

| Group | Can |
|---|---|
| FLT User | View/manage flights, visas, passports, documents for customers |
| FLT Manager | All of the above, plus approve/reject cancellation requests, configure policies, view reports |
| FLT Administrator | Full module configuration |
| Portal (customer) | View and act on their own records only |

## Portal Usage

Once logged in, customers see new entries on `/my` (My Travel Dashboard, My
Flights, My Visas, My Passports, My Documents, Cancellation Requests). Every
portal route re-derives the requesting partner server-side and compares it
against the record being accessed before returning any data — record IDs in
URLs are never trusted directly (see `controllers/portal.py:
_flt_get_owned_record`), and record-level `ir.rule`s provide a second,
independent layer of enforcement at the ORM level.

## Cancellation Workflow

```
Portal: Flight Details → Request Cancellation
  → Policy + charge + refund quoted live (no record written yet)
  → Customer confirms "I understand the charges and refund conditions"
  → flt.cancellation.request created (Submitted) + booking → Cancellation Requested
  → Staff: Start Review → Approve / Reject
  → Approve: refund status set, booking auto-cancelled only if the applied
    policy has "Automatically Cancel Booking" enabled; otherwise staff
    cancels manually
  → Customer notified at every status change
  → Staff: Mark Refund Processed once the actual refund has been issued
    outside the module (no payment integration is bundled)
```

## Visa / Passport Reminder Workflow

A single daily cron (`FLT: Expiry / Reminder Processor`) does everything:

1. Recomputes `status` for all passports/visas from `expiry_date` in batch.
2. For each configured day-threshold (e.g. 90/60/30/15/7/1 for visas), sends
   **one** notification per record per threshold the first time it's
   crossed — tracked via a `last_reminder_days` field so re-running the cron
   never re-sends the same threshold.

No cron is created per record, per customer, or per document type.

## Notification System

`flt.notification` is a single generic model covering every category
(flight cancellation/delay/change, visa/passport expiry, document required,
cancellation/refund updates, rebooking required, general alerts). Email
delivery goes through `mail.template` records (`data/mail_templates.xml`);
there is no hard-coded HTML in Python. The dispatch point
(`flt.notification._send_email`) is the single place a future WhatsApp/SMS
channel would hook in — the core module has no such dependency and works
standalone.

## Cron Configuration

Only one scheduled action ships with the module:
**FLT: Expiry / Reminder Processor**, daily, calling
`flt.passport._cron_process_expiry_and_reminders()`. Adjust its interval
under Settings → Technical → Scheduled Actions if a different cadence is
needed.

## Security Model

- Three groups (`FLT User` < `FLT Manager` < `FLT Administrator`), each
  implying the previous and `base.group_user`.
- `ir.model.access.csv` grants the portal group **read-only** access (and
  create-only where a self-service action needs it, e.g. document upload)
  on every customer-facing model; all state-changing actions (submit,
  approve, reject, mark processed, mark-as-read) go through server-side
  controller/model methods using `sudo()` with an explicit ownership check,
  never a direct client-side write.
- `ir.rule` record rules enforce "own records only" for portal users on
  every customer-facing model, independently of the controller checks
  above (defense in depth).
- Approving/rejecting a cancellation request additionally requires the
  `FLT Manager` group at the method level.

## Upgrade Considerations

- All models use `models.Constraint` (not the deprecated
  `_sql_constraints`) and Odoo 19 view syntax (`<list>`, no
  `attrs=`/`states=`).
- Sequences, cancellation policies and mail templates are `noupdate="1"` so
  customizations survive module upgrades; only genuinely new default data
  should be added there in future versions.
- `flt.expiry.reminder.mixin` centralizes reminder logic shared by
  passports and visas — extend it there, not by duplicating logic per
  model, if a third expiring-document type is added later.

## Known Limitations

- No payment gateway integration: refunds are tracked (status + amount)
  but not actually executed by this module.
- WhatsApp/SMS delivery is not implemented — only the extension point
  exists.
- The portal document upload accepts any file type; virus scanning, if
  required, must be added at the infrastructure level.
- Reporting is provided via native list/pivot/graph views rather than a
  dedicated BI/reporting engine.
