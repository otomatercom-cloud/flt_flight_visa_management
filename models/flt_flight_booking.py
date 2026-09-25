# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class FltFlightBooking(models.Model):
    _name = "flt.flight.booking"
    _description = "Flight Booking"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "booking_date desc"

    name = fields.Char(string="Booking Reference", required=True, copy=False, readonly=True, default="New")
    pnr = fields.Char(string="PNR", tracking=True)
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, index=True, tracking=True,
        ondelete="restrict",
    )
    booking_date = fields.Datetime(default=fields.Datetime.now, required=True)
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("reserved", "Reserved"),
            ("confirmed", "Confirmed"),
            ("ticketed", "Ticketed"),
            ("checked_in", "Checked In"),
            ("completed", "Completed"),
            ("cancellation_requested", "Cancellation Requested"),
            ("cancelled", "Cancelled"),
            ("airline_cancelled", "Airline Cancelled"),
            ("no_show", "No Show"),
        ],
        default="draft", required=True, tracking=True, index=True,
    )
    payment_status = fields.Selection(
        [
            ("not_paid", "Not Paid"),
            ("partially_paid", "Partially Paid"),
            ("paid", "Paid"),
            ("refunded", "Refunded"),
        ],
        default="not_paid", required=True, tracking=True,
    )

    # Passenger — deliberately NOT a duplicate of res.partner; only the
    # travel-document-facing fields that can legitimately differ from the
    # customer record (e.g. booking for a family member) live here.
    passenger_name = fields.Char(required=True)
    passenger_passport_id = fields.Many2one(
        "flt.passport", string="Passenger Passport",
        domain="[('partner_id', '=', partner_id)]",
    )
    passenger_contact = fields.Char(string="Passenger Contact")

    ticket_number = fields.Char()
    ticket_class = fields.Selection(
        [
            ("economy", "Economy"),
            ("premium_economy", "Premium Economy"),
            ("business", "Business"),
            ("first", "First"),
        ],
        default="economy",
    )
    baggage_allowance = fields.Char()
    ticket_amount = fields.Monetary(string="Ticket Amount")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, required=True,
    )
    ticket_document_ids = fields.Many2many(
        "ir.attachment", string="Ticket Documents",
        domain=[("res_model", "=", "flt.flight.booking")],
    )

    segment_ids = fields.One2many("flt.flight.segment", "booking_id", string="Segments", copy=True)
    cancellation_request_ids = fields.One2many(
        "flt.cancellation.request", "booking_id", string="Cancellation Requests"
    )
    cancellation_request_count = fields.Integer(compute="_compute_cancellation_request_count")

    airline_cancellation_reason = fields.Text(string="Airline Cancellation Reason")
    airline_cancellation_action = fields.Selection(
        [
            ("rebooking_required", "Rebooking Required"),
            ("refund_requested", "Refund Requested"),
            ("alternative_offered", "Alternative Flight Offered"),
            ("customer_contacted", "Customer Contacted"),
        ],
        string="Airline Cancellation Action",
    )

    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    _PORTAL_CANCELLABLE_STATES = ("reserved", "confirmed", "ticketed")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("flt.flight.booking") or "New"
        return super().create(vals_list)

    @api.depends("cancellation_request_ids")
    def _compute_cancellation_request_count(self):
        counts = {
            booking.id: count
            for booking, count in self.env["flt.cancellation.request"]._read_group(
                [("booking_id", "in", self.ids)], ["booking_id"], ["__count"]
            )
        }
        for booking in self:
            booking.cancellation_request_count = counts.get(booking.id, 0)

    def action_open_cancellation_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Cancellation Requests",
            "res_model": "flt.cancellation.request",
            "view_mode": "list,form",
            "domain": [("booking_id", "=", self.id)],
            "context": {"default_booking_id": self.id, "default_partner_id": self.partner_id.id},
        }

    def _is_portal_cancellable(self):
        self.ensure_one()
        return self.status in self._PORTAL_CANCELLABLE_STATES

    def action_mark_airline_cancelled(self, reason, action=False):
        """Staff-only entry point (never called from the portal) to record
        an airline-initiated cancellation. Never silently changes the
        booking without a reason on file."""
        self.ensure_one()
        if not reason:
            raise UserError("A cancellation reason is required when marking a booking as airline-cancelled.")
        self.write({
            "status": "airline_cancelled",
            "airline_cancellation_reason": reason,
            "airline_cancellation_action": action,
        })
        self.segment_ids.write({"status": "cancelled"})
        self.env["flt.notification"].create_notification(
            partner=self.partner_id,
            category="flight_cancellation",
            title=f"Flight Update: Booking {self.name}",
            message=(
                f"Your booking {self.name} (PNR: {self.pnr or '-'}) has been cancelled by the airline. "
                "Please contact our support team regarding rebooking or refund options."
            ),
            related_record=self,
        )

    @api.constrains("segment_ids")
    def _check_segment_sequence(self):
        """Multi-segment sequence must be valid: each segment's departure
        must not be before the previous segment's arrival (chronological
        journey), when more than one segment exists."""
        for booking in self:
            segments = booking.segment_ids.sorted(lambda s: (s.sequence, s.departure_datetime or ""))
            for prev, curr in zip(segments, segments[1:]):
                if prev.arrival_datetime and curr.departure_datetime and curr.departure_datetime < prev.arrival_datetime:
                    raise ValidationError(
                        "Flight segments must be in chronological order: a later segment cannot depart "
                        "before an earlier segment has arrived."
                    )
