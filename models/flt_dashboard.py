# -*- coding: utf-8 -*-
import datetime

from odoo import api, fields, models


class FltDashboard(models.TransientModel):
    """Backend KPI dashboard. A plain transient wizard form (native Odoo
    stat-button widgets only, no custom JS/OWL) whose fields are computed
    with a handful of cheap search_count() calls on open — never loads full
    record sets into memory."""

    _name = "flt.dashboard"
    _description = "FLT Dashboard"

    upcoming_flights = fields.Integer(readonly=True)
    today_flights = fields.Integer(readonly=True)
    cancelled_flights = fields.Integer(readonly=True)
    cancellation_requests_pending = fields.Integer(readonly=True)
    pending_refunds = fields.Integer(readonly=True)
    visas_expiring_30 = fields.Integer(readonly=True)
    visas_expiring_90 = fields.Integer(readonly=True)
    passports_expiring = fields.Integer(readonly=True)
    pending_documents = fields.Integer(readonly=True)
    rebooking_required = fields.Integer(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        Booking = self.env["flt.flight.booking"]
        Segment = self.env["flt.flight.segment"]
        CancelReq = self.env["flt.cancellation.request"]
        Visa = self.env["flt.visa"]
        Passport = self.env["flt.passport"]
        Document = self.env["flt.document"]

        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        today_end = datetime.datetime.combine(today, datetime.time.max)
        soon_30 = today + datetime.timedelta(days=30)
        soon_90 = today + datetime.timedelta(days=90)

        res.update({
            "upcoming_flights": Booking.search_count([
                ("status", "not in", ("cancelled", "airline_cancelled", "completed")),
                ("segment_ids.departure_datetime", ">=", now),
            ]),
            "today_flights": Segment.search_count([
                ("departure_datetime", ">=", today_start),
                ("departure_datetime", "<=", today_end),
            ]),
            "cancelled_flights": Booking.search_count([("status", "in", ("cancelled", "airline_cancelled"))]),
            "cancellation_requests_pending": CancelReq.search_count([("status", "in", ("submitted", "under_review"))]),
            "pending_refunds": CancelReq.search_count([("refund_status", "in", ("pending", "approved", "processing"))]),
            "visas_expiring_30": Visa.search_count([("status", "=", "active"), ("expiry_date", "<=", soon_30)]),
            "visas_expiring_90": Visa.search_count([("status", "=", "active"), ("expiry_date", "<=", soon_90)]),
            "passports_expiring": Passport.search_count([("status", "in", ("expiring_soon", "expired"))]),
            "pending_documents": Document.search_count([("status", "=", "pending")]),
            "rebooking_required": Booking.search_count([
                ("status", "=", "airline_cancelled"),
                ("airline_cancellation_action", "=", "rebooking_required"),
            ]),
        })
        return res

    def action_open_upcoming_flights(self):
        return self._open_bookings([
            ("status", "not in", ("cancelled", "airline_cancelled", "completed")),
            ("segment_ids.departure_datetime", ">=", fields.Datetime.now()),
        ], "Upcoming Flights")

    def action_open_cancelled_flights(self):
        return self._open_bookings([("status", "in", ("cancelled", "airline_cancelled"))], "Cancelled Flights")

    def action_open_pending_cancellations(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Pending Cancellation Requests",
            "res_model": "flt.cancellation.request",
            "view_mode": "list,form",
            "domain": [("status", "in", ("submitted", "under_review"))],
        }

    def action_open_pending_refunds(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Pending Refunds",
            "res_model": "flt.cancellation.request",
            "view_mode": "list,form",
            "domain": [("refund_status", "in", ("pending", "approved", "processing"))],
        }

    def action_open_expiring_visas(self):
        today = fields.Date.context_today(self)
        return {
            "type": "ir.actions.act_window",
            "name": "Expiring Visas",
            "res_model": "flt.visa",
            "view_mode": "list,form",
            "domain": [("status", "=", "active"), ("expiry_date", "<=", today + datetime.timedelta(days=90))],
        }

    def action_open_expiring_passports(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Expiring Passports",
            "res_model": "flt.passport",
            "view_mode": "list,form",
            "domain": [("status", "in", ("expiring_soon", "expired"))],
        }

    def action_open_pending_documents(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Pending Documents",
            "res_model": "flt.document",
            "view_mode": "list,form",
            "domain": [("status", "=", "pending")],
        }

    def _open_bookings(self, domain, name):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "flt.flight.booking",
            "view_mode": "list,form",
            "domain": domain,
        }
