# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    flt_visa_types = fields.Char(
        string="Visa Types",
        config_parameter="flt_flight_visa_management.visa_types",
        default="tourist,business,student,work,transit,resident",
        help="Comma-separated list of visa types offered in the Visa Type dropdown.",
    )
    flt_visa_reminder_days = fields.Char(
        string="Visa Reminder Days Before Expiry",
        config_parameter="flt_flight_visa_management.visa_reminder_days",
        default="90,60,30,15,7,1",
        help="Comma-separated list of day offsets before visa expiry to send a reminder.",
    )
    flt_passport_reminder_days = fields.Char(
        string="Passport Reminder Days Before Expiry",
        config_parameter="flt_flight_visa_management.passport_reminder_days",
        default="180,90,60,30",
        help="Comma-separated list of day offsets before passport expiry to send a reminder.",
    )
    flt_passport_expiring_soon_days = fields.Integer(
        string="Passport 'Expiring Soon' Threshold (days)",
        config_parameter="flt_flight_visa_management.passport_expiring_soon_days",
        default=90,
    )
    flt_default_auto_cancel_on_approval = fields.Boolean(
        string="Default: Auto-cancel Booking on Cancellation Approval",
        config_parameter="flt_flight_visa_management.default_auto_cancel_on_approval",
        help="Default value used for new Cancellation Policy records.",
    )
