# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class FltCancellationRequest(models.Model):
    _name = "flt.cancellation.request"
    _description = "Flight Cancellation Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc"

    name = fields.Char(string="Request Number", required=True, copy=False, readonly=True, default="New")
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, index=True,
        ondelete="restrict",
    )
    booking_id = fields.Many2one(
        "flt.flight.booking", string="Flight Booking", required=True, index=True,
        ondelete="restrict",
    )
    request_date = fields.Datetime(default=fields.Datetime.now, required=True)
    reason = fields.Text(required=True)

    original_amount = fields.Monetary(string="Original Amount", required=True)
    cancellation_charge = fields.Monetary(string="Cancellation Charge")
    additional_charges = fields.Monetary(string="Additional Charges")
    refund_amount = fields.Monetary(string="Refund Amount", compute="_compute_refund_amount", store=True)
    final_refund_amount = fields.Monetary(
        string="Final Refund Amount",
        help="Editable by staff during review; defaults to the computed refund amount.",
    )
    currency_id = fields.Many2one(related="booking_id.currency_id", store=True)

    policy_id = fields.Many2one("flt.cancellation.policy", string="Applied Cancellation Policy")

    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("processed", "Processed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft", required=True, tracking=True, index=True,
    )
    refund_status = fields.Selection(
        [
            ("not_applicable", "Not Applicable"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("processing", "Processing"),
            ("refunded", "Refunded"),
            ("failed", "Failed"),
        ],
        default="not_applicable", required=True, tracking=True,
    )

    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True)
    approval_date = fields.Datetime(readonly=True)
    remarks = fields.Text(string="Staff Remarks")
    customer_confirmed = fields.Boolean(
        string="Customer Confirmed Charges",
        help="Set when the customer explicitly confirmed they understand the "
             "cancellation charges and refund conditions before submitting.",
    )

    company_id = fields.Many2one(related="booking_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("flt.cancellation.request") or "New"
        return super().create(vals_list)

    @api.depends("original_amount", "cancellation_charge", "additional_charges")
    def _compute_refund_amount(self):
        for req in self:
            amount = (req.original_amount or 0.0) - (req.cancellation_charge or 0.0) - (req.additional_charges or 0.0)
            req.refund_amount = max(amount, 0.0)

    @api.constrains("cancellation_charge", "original_amount")
    def _check_charge_not_excessive(self):
        for req in self:
            if req.cancellation_charge and req.cancellation_charge > req.original_amount:
                raise ValidationError(
                    "Cancellation charge cannot exceed the original ticket amount unless explicitly "
                    "configured with additional charges."
                )

    @api.constrains("final_refund_amount")
    def _check_refund_not_negative(self):
        for req in self:
            if req.final_refund_amount < 0:
                raise ValidationError("Refund amount cannot be negative.")

    # ---- Portal-facing helper: quote charges without creating a record ----
    @api.model
    def quote_cancellation(self, booking):
        """Return {policy, charge, refund} for a booking's current segments,
        using the earliest upcoming segment's departure as the reference
        time. Does not write anything."""
        Policy = self.env["flt.cancellation.policy"]
        segment = booking.segment_ids.filtered(
            lambda s: s.departure_datetime and s.status not in ("cancelled", "completed")
        ).sorted("departure_datetime")[:1]
        if not segment:
            return {"policy": False, "charge": 0.0, "refund": booking.ticket_amount}
        now = fields.Datetime.now()
        hours_before = max((segment.departure_datetime - now).total_seconds() / 3600.0, 0)
        policy = Policy._find_applicable_policy(segment.airline_id, booking.ticket_class, hours_before)
        charge = policy.compute_charge(booking.ticket_amount) if policy else 0.0
        charge = min(charge, booking.ticket_amount)
        return {
            "policy": policy,
            "charge": charge,
            "refund": max(booking.ticket_amount - charge, 0.0),
        }

    def action_submit(self):
        for req in self:
            if not req.customer_confirmed:
                raise UserError("The customer must confirm the cancellation charges and refund conditions first.")
            req.write({"status": "submitted", "refund_status": "pending"})
            req.booking_id.write({"status": "cancellation_requested"})
            req.env["flt.notification"].create_notification(
                partner=False,  # internal/staff notification, not customer-facing
                category="cancellation_request_update",
                title=f"New Cancellation Request {req.name}",
                message=f"Customer {req.partner_id.name} requested cancellation of booking {req.booking_id.name}.",
                related_record=req,
                staff_only=True,
            )

    def action_start_review(self):
        self.write({"status": "under_review"})

    def action_approve(self):
        if not self.env.user.has_group("flt_flight_visa_management.group_flt_manager"):
            raise UserError("Only an FLT Manager can approve a cancellation request.")
        for req in self:
            if req.status not in ("submitted", "under_review"):
                raise UserError("Only a submitted or under-review request can be approved.")
            if not req.final_refund_amount and req.refund_amount:
                req.final_refund_amount = req.refund_amount
            req.write({
                "status": "approved",
                "refund_status": "approved",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            })
            if req.policy_id and req.policy_id.auto_cancel_booking:
                req.booking_id.write({"status": "cancelled"})
                req.booking_id.segment_ids.write({"status": "cancelled"})
            req.env["flt.notification"].create_notification(
                partner=req.partner_id,
                category="cancellation_request_update",
                title=f"Cancellation Approved: {req.booking_id.name}",
                message=(
                    f"Your cancellation request {req.name} has been approved. "
                    f"Refund amount: {req.final_refund_amount} {req.currency_id.name}."
                ),
                related_record=req,
            )

    def action_reject(self):
        if not self.env.user.has_group("flt_flight_visa_management.group_flt_manager"):
            raise UserError("Only an FLT Manager can reject a cancellation request.")
        for req in self:
            if req.status not in ("submitted", "under_review"):
                raise UserError("Only a submitted or under-review request can be rejected.")
            req.write({
                "status": "rejected",
                "refund_status": "not_applicable",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            })
            req.booking_id.write({"status": "confirmed"})
            req.env["flt.notification"].create_notification(
                partner=req.partner_id,
                category="cancellation_request_update",
                title=f"Cancellation Rejected: {req.booking_id.name}",
                message=f"Your cancellation request {req.name} has been rejected. See remarks: {req.remarks or '-'}",
                related_record=req,
            )

    def action_mark_processed(self):
        for req in self:
            if req.status != "approved":
                raise UserError("Only an approved request can be marked as processed.")
            req.write({"status": "processed", "refund_status": "refunded"})
            req.env["flt.notification"].create_notification(
                partner=req.partner_id,
                category="refund_update",
                title=f"Refund Processed: {req.booking_id.name}",
                message=f"Your refund of {req.final_refund_amount} {req.currency_id.name} has been processed.",
                related_record=req,
            )
