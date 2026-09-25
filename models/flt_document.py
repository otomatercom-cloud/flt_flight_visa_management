# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FltDocument(models.Model):
    _name = "flt.document"
    _description = "Travel Document"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(string="Document Name", required=True)
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, index=True,
        ondelete="cascade",
    )
    document_type = fields.Selection(
        [
            ("passport", "Passport"),
            ("visa", "Visa"),
            ("flight_ticket", "Flight Ticket"),
            ("boarding_pass", "Boarding Pass"),
            ("national_id", "Emirates ID / National ID"),
            ("insurance", "Insurance"),
            ("other", "Other"),
        ],
        required=True, index=True,
    )
    # Generic polymorphic link to the related business record, avoiding a
    # separate M2O per possible related model.
    related_model = fields.Selection(
        [
            ("flt.passport", "Passport"),
            ("flt.visa", "Visa"),
            ("flt.flight.booking", "Flight Booking"),
        ],
    )
    related_res_id = fields.Many2oneReference(model_field="related_model", string="Related Record Id")

    upload_date = fields.Datetime(default=fields.Datetime.now, required=True)
    expiry_date = fields.Date()
    status = fields.Selection(
        [("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected"), ("expired", "Expired")],
        default="pending", required=True, tracking=True,
    )
    notes = fields.Text()
    attachment_id = fields.Many2one(
        "ir.attachment", string="File", required=True,
        domain=[("res_model", "=", "flt.document")], ondelete="restrict",
    )

    def action_verify(self):
        self.write({"status": "verified"})

    def action_reject(self):
        self.write({"status": "rejected"})
