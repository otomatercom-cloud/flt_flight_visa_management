# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFlightBooking(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "John Traveler", "email": "john@example.com"})
        self.airline = self.env["flt.airline"].create({"name": "Emirates", "code": "EK"})
        self.dxb = self.env["flt.airport"].create({"name": "Dubai Intl", "code": "DXB"})
        self.cok = self.env["flt.airport"].create({"name": "Kochi Intl", "code": "COK"})

    def _make_booking(self, **extra):
        vals = {
            "partner_id": self.partner.id,
            "passenger_name": "John Traveler",
            "ticket_amount": 25000,
        }
        vals.update(extra)
        return self.env["flt.flight.booking"].create(vals)

    def test_create_booking_gets_sequence_name(self):
        booking = self._make_booking()
        self.assertTrue(booking.name.startswith("FLT/BOOK/"))

    def test_add_segments(self):
        booking = self._make_booking()
        now = datetime.now() + timedelta(days=10)
        self.env["flt.flight.segment"].create({
            "booking_id": booking.id,
            "airline_id": self.airline.id,
            "flight_number": "EK531",
            "departure_airport_id": self.cok.id,
            "departure_datetime": now,
            "arrival_airport_id": self.dxb.id,
            "arrival_datetime": now + timedelta(hours=4),
        })
        self.assertEqual(len(booking.segment_ids), 1)

    def test_segment_arrival_before_departure_raises(self):
        booking = self._make_booking()
        now = datetime.now() + timedelta(days=10)
        with self.assertRaises(ValidationError):
            self.env["flt.flight.segment"].create({
                "booking_id": booking.id,
                "airline_id": self.airline.id,
                "flight_number": "EK531",
                "departure_airport_id": self.cok.id,
                "departure_datetime": now,
                "arrival_airport_id": self.dxb.id,
                "arrival_datetime": now - timedelta(hours=1),
            })

    def test_change_status(self):
        booking = self._make_booking()
        booking.write({"status": "confirmed"})
        self.assertEqual(booking.status, "confirmed")

    def test_multi_segment_booking_chronological_order_enforced(self):
        booking = self._make_booking()
        now = datetime.now() + timedelta(days=10)
        self.env["flt.flight.segment"].create({
            "booking_id": booking.id,
            "sequence": 10,
            "airline_id": self.airline.id,
            "flight_number": "EK531",
            "departure_airport_id": self.cok.id,
            "departure_datetime": now,
            "arrival_airport_id": self.dxb.id,
            "arrival_datetime": now + timedelta(hours=4),
        })
        with self.assertRaises(ValidationError):
            self.env["flt.flight.segment"].create({
                "booking_id": booking.id,
                "sequence": 20,
                "airline_id": self.airline.id,
                "flight_number": "EK532",
                "departure_airport_id": self.dxb.id,
                # Departs BEFORE the first segment arrives -> invalid order.
                "departure_datetime": now + timedelta(hours=1),
                "arrival_airport_id": self.cok.id,
                "arrival_datetime": now + timedelta(hours=8),
            })

    def test_airline_cancellation_requires_reason(self):
        booking = self._make_booking()
        with self.assertRaises(Exception):
            booking.action_mark_airline_cancelled(reason=False)

    def test_airline_cancellation_creates_notification(self):
        booking = self._make_booking()
        booking.action_mark_airline_cancelled(reason="Weather", action="rebooking_required")
        self.assertEqual(booking.status, "airline_cancelled")
        notif = self.env["flt.notification"].search([
            ("partner_id", "=", self.partner.id), ("category", "=", "flight_cancellation"),
        ])
        self.assertTrue(notif)
