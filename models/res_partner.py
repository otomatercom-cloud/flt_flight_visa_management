# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    flt_nationality_id = fields.Many2one("res.country", string="Nationality")
    flt_emergency_contact_name = fields.Char(string="Emergency Contact Name")
    flt_emergency_contact_phone = fields.Char(string="Emergency Contact Phone")

    flt_passport_ids = fields.One2many("flt.passport", "partner_id", string="Passports")
    flt_visa_ids = fields.One2many("flt.visa", "partner_id", string="Visas")
    flt_booking_ids = fields.One2many("flt.flight.booking", "partner_id", string="Flight Bookings")
    flt_document_ids = fields.One2many("flt.document", "partner_id", string="Travel Documents")
    flt_passport_count = fields.Integer(compute="_compute_flt_counts", string="Passport Count")
    flt_visa_count = fields.Integer(compute="_compute_flt_counts", string="Visa Count")
    flt_booking_count = fields.Integer(compute="_compute_flt_counts", string="Booking Count")

    @api.depends("flt_passport_ids", "flt_visa_ids", "flt_booking_ids")
    def _compute_flt_counts(self):
        # Single batched read_group per model instead of a search_count per
        # partner per model (avoids N+1 when this is shown on a partner list).
        passport_counts = {
            partner.id: count
            for partner, count in self.env["flt.passport"]._read_group(
                [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
            )
        }
        visa_counts = {
            partner.id: count
            for partner, count in self.env["flt.visa"]._read_group(
                [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
            )
        }
        booking_counts = {
            partner.id: count
            for partner, count in self.env["flt.flight.booking"]._read_group(
                [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
            )
        }
        for partner in self:
            partner.flt_passport_count = passport_counts.get(partner.id, 0)
            partner.flt_visa_count = visa_counts.get(partner.id, 0)
            partner.flt_booking_count = booking_counts.get(partner.id, 0)
