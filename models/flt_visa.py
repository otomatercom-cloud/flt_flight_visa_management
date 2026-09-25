# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FltVisa(models.Model):
    _name = "flt.visa"
    _description = "Visa"
    _inherit = ["mail.thread", "flt.expiry.reminder.mixin"]
    _order = "expiry_date"

    name = fields.Char(string="Application Number", required=True, copy=False, readonly=True, default="New")
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, index=True, tracking=True,
        ondelete="restrict",
    )
    passport_id = fields.Many2one(
        "flt.passport", string="Passport", required=True,
        domain="[('partner_id', '=', partner_id)]",
    )
    country_id = fields.Many2one("res.country", string="Country", required=True)
    visa_number = fields.Char(tracking=True)
    visa_type = fields.Selection(
        selection="_selection_visa_type", string="Visa Type", required=True,
    )
    issue_date = fields.Date()
    expiry_date = fields.Date(index=True, tracking=True)
    renewal_date = fields.Date()
    entry_type = fields.Selection(
        [("single", "Single Entry"), ("double", "Double Entry"), ("multiple", "Multiple Entry")],
        default="single",
    )
    number_of_entries = fields.Integer(default=1)
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Application Submitted"),
            ("processing", "Processing"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        default="draft", required=True, tracking=True, index=True,
    )
    notes = fields.Text()
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Visa Documents",
        domain=[("res_model", "=", "flt.visa")],
    )
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("flt.visa") or "New"
        return super().create(vals_list)

    @api.model
    def _selection_visa_type(self):
        """Configurable visa types, sourced from ir.config_parameter so
        admins can extend the list without a code change."""
        param = self.env["ir.config_parameter"].sudo().get_param(
            "flt_flight_visa_management.visa_types",
            "tourist,business,student,work,transit,resident",
        )
        return [(v.strip(), v.strip().title()) for v in param.split(",") if v.strip()]

    @api.constrains("issue_date", "expiry_date")
    def _check_dates(self):
        for visa in self:
            if visa.issue_date and visa.expiry_date and visa.expiry_date <= visa.issue_date:
                raise ValidationError("Visa expiry date must be after the issue date.")

    @api.constrains("passport_id", "partner_id")
    def _check_passport_owner(self):
        for visa in self:
            if visa.passport_id and visa.passport_id.partner_id != visa.partner_id:
                raise ValidationError("The selected passport does not belong to this customer.")

    def _compute_status_from_expiry(self, soon_days=90):
        """Only 'active' visas transition automatically to 'expired'; other
        workflow states (draft/submitted/processing/approved/rejected/
        cancelled) are staff/process-driven and untouched here."""
        today = fields.Date.context_today(self)
        for visa in self.filtered(lambda v: v.status == "active" and v.expiry_date):
            if visa.expiry_date < today:
                visa.status = "expired"
