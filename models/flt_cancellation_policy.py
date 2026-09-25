# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FltCancellationPolicy(models.Model):
    _name = "flt.cancellation.policy"
    _description = "Cancellation Policy Rule"
    _order = "sequence, min_hours_before_departure"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    airline_id = fields.Many2one(
        "flt.airline", string="Airline (leave empty for all airlines)",
    )
    ticket_class = fields.Selection(
        [
            ("economy", "Economy"),
            ("premium_economy", "Premium Economy"),
            ("business", "Business"),
            ("first", "First"),
        ],
        string="Ticket Class (leave empty for all classes)",
    )

    # A rule applies when hours-before-departure falls in
    # [min_hours_before_departure, max_hours_before_departure).
    # Leave max empty to mean "no upper bound" (i.e. 72+ hours).
    min_hours_before_departure = fields.Integer(
        required=True, default=0,
        help="Rule applies from this many hours before departure onwards.",
    )
    max_hours_before_departure = fields.Integer(
        help="Rule applies up to (not including) this many hours before departure. "
             "Leave empty for no upper bound.",
    )

    charge_type = fields.Selection(
        [("percentage", "Percentage of Ticket Amount"), ("fixed", "Fixed Amount")],
        required=True, default="percentage",
    )
    charge_percentage = fields.Float(string="Charge %", help="Used when Charge Type is Percentage.")
    charge_fixed_amount = fields.Monetary(string="Fixed Charge", help="Used when Charge Type is Fixed Amount.")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, required=True,
    )

    auto_cancel_booking = fields.Boolean(
        string="Automatically Cancel Booking on Approval",
        help="If enabled, approving a cancellation request under this policy "
             "automatically moves the booking to Cancelled. Otherwise staff "
             "must cancel the booking manually.",
    )

    @api.constrains("charge_type", "charge_percentage", "charge_fixed_amount")
    def _check_charge_values(self):
        for policy in self:
            if policy.charge_type == "percentage" and not (0 <= policy.charge_percentage <= 100):
                raise ValidationError("Charge percentage must be between 0 and 100.")
            if policy.charge_type == "fixed" and policy.charge_fixed_amount < 0:
                raise ValidationError("Fixed charge cannot be negative.")

    @api.constrains("min_hours_before_departure", "max_hours_before_departure")
    def _check_hour_range(self):
        for policy in self:
            if policy.min_hours_before_departure < 0:
                raise ValidationError("Minimum hours before departure cannot be negative.")
            if policy.max_hours_before_departure and policy.max_hours_before_departure <= policy.min_hours_before_departure:
                raise ValidationError("Maximum hours before departure must be greater than the minimum.")

    @api.model
    def _find_applicable_policy(self, airline, ticket_class, hours_before_departure):
        """Return the best-matching active policy for the given context, or
        an empty recordset if none applies. Specific (airline/class) rules
        win over generic ones via search ordering (specific first)."""
        domain = [
            ("min_hours_before_departure", "<=", hours_before_departure),
            "|", ("max_hours_before_departure", "=", False),
            ("max_hours_before_departure", ">", hours_before_departure),
        ]
        candidates = self.search(domain, order="sequence, min_hours_before_departure")
        for candidate in candidates:
            if candidate.airline_id and candidate.airline_id != airline:
                continue
            if candidate.ticket_class and candidate.ticket_class != ticket_class:
                continue
            return candidate
        return self.browse()

    def compute_charge(self, ticket_amount):
        self.ensure_one()
        if self.charge_type == "percentage":
            return round(ticket_amount * (self.charge_percentage / 100.0), 2)
        return self.charge_fixed_amount
