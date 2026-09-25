# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FltPassport(models.Model):
    _name = "flt.passport"
    _description = "Passport"
    _inherit = ["mail.thread", "flt.expiry.reminder.mixin"]
    _order = "expiry_date"

    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, index=True, tracking=True,
        ondelete="restrict",
    )
    passport_number = fields.Char(required=True, tracking=True)
    full_name = fields.Char(string="Full Name (as on Passport)", required=True)
    date_of_birth = fields.Date(string="Date of Birth")
    nationality_id = fields.Many2one("res.country", string="Nationality")
    issue_date = fields.Date(required=True)
    expiry_date = fields.Date(required=True, index=True, tracking=True)
    place_of_issue = fields.Char()
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("valid", "Valid"),
            ("expiring_soon", "Expiring Soon"),
            ("expired", "Expired"),
        ],
        default="draft", required=True, tracking=True, index=True,
    )
    notes = fields.Text()
    attachment_ids = fields.Many2many(
        "ir.attachment", string="Passport Copies",
        domain=[("res_model", "=", "flt.passport")],
    )
    active = fields.Boolean(default=True)

    _sql_unique_passport_per_partner = models.Constraint(
        "unique(partner_id, passport_number)",
        "This passport number is already registered for this customer.",
    )

    @api.constrains("issue_date", "expiry_date")
    def _check_dates(self):
        for passport in self:
            if passport.issue_date and passport.expiry_date and passport.expiry_date <= passport.issue_date:
                raise ValidationError("Passport expiry date must be after the issue date.")

    def action_validate(self):
        """Staff action: move a Draft passport to Valid (or Expired/Expiring
        Soon immediately if the expiry date already warrants it)."""
        self.filtered(lambda p: p.status == "draft").write({"status": "valid"})
        self._compute_status_from_expiry()

    def _compute_status_from_expiry(self, soon_days=90):
        """Recompute status purely from expiry_date. Never touches Draft
        records (those need explicit staff validation first) or Cancelled-
        style terminal states that don't exist here. Called by the
        centralized expiry cron in batch."""
        today = fields.Date.context_today(self)
        soon_cutoff = today + timedelta(days=soon_days)
        for passport in self.filtered(lambda p: p.status != "draft" and p.expiry_date):
            if passport.expiry_date < today:
                new_status = "expired"
            elif passport.expiry_date <= soon_cutoff:
                new_status = "expiring_soon"
            else:
                new_status = "valid"
            if new_status != passport.status:
                passport.status = new_status

    @api.model
    def _get_reminder_days(self, param_key, default_csv):
        param = self.env["ir.config_parameter"].sudo().get_param(param_key, default_csv)
        days = sorted({int(d.strip()) for d in param.split(",") if d.strip().isdigit()}, reverse=True)
        return days or [int(d) for d in default_csv.split(",")]

    @api.model
    def _cron_process_expiry_and_reminders(self):
        """Single centralized scheduled job (data/ir_cron.xml) covering
        both passports and visas: recompute statuses in batch, then send
        batched, duplicate-safe reminder notifications. Deliberately not
        one cron per document type or per record."""
        soon_days = int(self.env["ir.config_parameter"].sudo().get_param(
            "flt_flight_visa_management.passport_expiring_soon_days", 90
        ))

        passports = self.search([("expiry_date", "!=", False)])
        passports._compute_status_from_expiry(soon_days=soon_days)
        passport_reminder_days = self._get_reminder_days(
            "flt_flight_visa_management.passport_reminder_days", "180,90,60,30"
        )
        passports._send_expiry_reminders("passport_expiry", passport_reminder_days, "Your passport expires")

        Visa = self.env["flt.visa"]
        visas = Visa.search([("expiry_date", "!=", False), ("status", "=", "active")])
        visas._compute_status_from_expiry()
        active_visas = Visa.search([("expiry_date", "!=", False), ("status", "in", ("active", "approved"))])
        visa_reminder_days = self._get_reminder_days(
            "flt_flight_visa_management.visa_reminder_days", "90,60,30,15,7,1"
        )
        active_visas._send_expiry_reminders("visa_expiry", visa_reminder_days, "Your visa expires")
