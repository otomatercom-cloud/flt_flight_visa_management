# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCancellation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Jane Traveler", "email": "jane@example.com"})
        self.manager = self.env["res.users"].create({
            "name": "FLT Manager",
            "login": "flt_manager_test",
            "email": "manager@example.com",
            "group_ids": [(4, self.env.ref("flt_flight_visa_management.group_flt_manager").id)],
        })
        self.flt_user = self.env["res.users"].create({
            "name": "FLT User",
            "login": "flt_user_test",
            "email": "user@example.com",
            "group_ids": [(4, self.env.ref("flt_flight_visa_management.group_flt_user").id)],
        })
        self.airline = self.env["flt.airline"].create({"name": "Emirates", "code": "EK"})
        self.booking = self.env["flt.flight.booking"].create({
            "partner_id": self.partner.id,
            "passenger_name": "Jane Traveler",
            "ticket_amount": 25000,
            "ticket_class": "economy",
            "status": "confirmed",
        })
        self.dxb = self.env["flt.airport"].create({"name": "Dubai Intl", "code": "DXB"})
        self.cok = self.env["flt.airport"].create({"name": "Kochi Intl", "code": "COK"})
        self.env["flt.flight.segment"].create({
            "booking_id": self.booking.id,
            "airline_id": self.airline.id,
            "flight_number": "EK531",
            "departure_airport_id": self.cok.id,
            "departure_datetime": datetime.now() + timedelta(hours=10),
            "arrival_airport_id": self.dxb.id,
            "arrival_datetime": datetime.now() + timedelta(hours=14),
            "status": "confirmed",
        })

    def _make_request(self, charge=3000):
        return self.env["flt.cancellation.request"].create({
            "partner_id": self.partner.id,
            "booking_id": self.booking.id,
            "reason": "Change of plans",
            "original_amount": 25000,
            "cancellation_charge": charge,
            "customer_confirmed": True,
        })

    def test_refund_calculation(self):
        req = self._make_request(charge=3000)
        self.assertEqual(req.refund_amount, 22000)

    def test_charge_cannot_exceed_original_amount(self):
        with self.assertRaises(ValidationError):
            self._make_request(charge=30000)

    def test_submit_requires_customer_confirmation(self):
        req = self.env["flt.cancellation.request"].create({
            "partner_id": self.partner.id,
            "booking_id": self.booking.id,
            "reason": "Change of plans",
            "original_amount": 25000,
            "cancellation_charge": 3000,
            "customer_confirmed": False,
        })
        with self.assertRaises(UserError):
            req.action_submit()

    def test_customer_cancellation_request_flow(self):
        req = self._make_request()
        req.action_submit()
        self.assertEqual(req.status, "submitted")
        self.assertEqual(self.booking.status, "cancellation_requested")

    def test_approval_by_manager(self):
        req = self._make_request()
        req.action_submit()
        req.with_user(self.manager).action_approve()
        self.assertEqual(req.status, "approved")
        self.assertEqual(req.refund_status, "approved")

    def test_approval_requires_manager_group(self):
        req = self._make_request()
        req.action_submit()
        with self.assertRaises(UserError):
            req.with_user(self.flt_user).action_approve()

    def test_rejection_reverts_booking_status(self):
        req = self._make_request()
        req.action_submit()
        req.with_user(self.manager).action_reject()
        self.assertEqual(req.status, "rejected")
        self.assertEqual(self.booking.status, "confirmed")

    def test_refund_cannot_be_negative(self):
        req = self._make_request()
        with self.assertRaises(ValidationError):
            req.final_refund_amount = -100

    def test_airline_cancellation_marks_booking(self):
        self.booking.action_mark_airline_cancelled(reason="Technical issue", action="refund_requested")
        self.assertEqual(self.booking.status, "airline_cancelled")
        self.assertTrue(all(s.status == "cancelled" for s in self.booking.segment_ids))
