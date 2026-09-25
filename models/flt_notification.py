# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FltNotification(models.Model):
    _name = "flt.notification"
    _description = "Travel Notification"
    _order = "create_date desc"
    _rec_name = "title"

    partner_id = fields.Many2one(
        "res.partner", string="Customer", index=True,
        ondelete="cascade",
        help="Empty for an internal/staff-only notification.",
    )
    category = fields.Selection(
        [
            ("flight_cancellation", "Flight Cancellation"),
            ("flight_delay", "Flight Delay"),
            ("flight_change", "Flight Change"),
            ("visa_expiry", "Visa Expiry"),
            ("passport_expiry", "Passport Expiry"),
            ("document_required", "Document Required"),
            ("cancellation_request_update", "Cancellation Request Update"),
            ("refund_update", "Refund Update"),
            ("rebooking_required", "Rebooking Required"),
            ("general_alert", "General Travel Alert"),
        ],
        required=True, index=True,
    )
    title = fields.Char(required=True)
    message = fields.Text(required=True)

    related_model = fields.Selection(
        [
            ("flt.flight.booking", "Flight Booking"),
            ("flt.visa", "Visa"),
            ("flt.passport", "Passport"),
            ("flt.cancellation.request", "Cancellation Request"),
        ],
    )
    related_res_id = fields.Many2oneReference(model_field="related_model", string="Related Record Id")

    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    is_read = fields.Boolean(string="Read", default=False, index=True)
    staff_only = fields.Boolean(default=False, index=True)
    delivery_status = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
        default="pending", required=True,
    )

    @api.model
    def create_notification(self, partner, category, title, message, related_record=False, staff_only=False):
        """Single generic entry point used by every workflow (booking,
        cancellation, visa/passport expiry, documents) instead of a
        model-specific notification table per category."""
        vals = {
            "partner_id": partner.id if partner else False,
            "category": category,
            "title": title,
            "message": message,
            "staff_only": staff_only,
        }
        if related_record:
            vals["related_model"] = related_record._name
            vals["related_res_id"] = related_record.id
        notification = self.create(vals)
        notification._send_email()
        return notification

    def _send_email(self):
        """Dispatch via mail.template when one is registered for this
        category (data/mail_templates.xml). Kept provider-agnostic: this is
        the single extension point a future WhatsApp/SMS module would
        override or extend, so the core module has no such dependency."""
        template_xmlid_map = {
            "flight_cancellation": "flt_flight_visa_management.mail_template_flight_cancellation",
            "flight_delay": "flt_flight_visa_management.mail_template_flight_change",
            "flight_change": "flt_flight_visa_management.mail_template_flight_change",
            "visa_expiry": "flt_flight_visa_management.mail_template_visa_expiry",
            "passport_expiry": "flt_flight_visa_management.mail_template_passport_expiry",
            "document_required": "flt_flight_visa_management.mail_template_document_required",
            "cancellation_request_update": "flt_flight_visa_management.mail_template_cancellation_update",
            "refund_update": "flt_flight_visa_management.mail_template_refund_processed",
        }
        for notification in self:
            if notification.staff_only or not notification.partner_id or not notification.partner_id.email:
                continue
            xmlid = template_xmlid_map.get(notification.category)
            template = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else False
            try:
                if template:
                    template.send_mail(notification.id, force_send=False)
                notification.delivery_status = "sent"
            except Exception:
                notification.delivery_status = "failed"
