# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FltFlightSegment(models.Model):
    _name = "flt.flight.segment"
    _description = "Flight Segment"
    _order = "sequence, departure_datetime"

    booking_id = fields.Many2one(
        "flt.flight.booking", string="Booking", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    airline_id = fields.Many2one("flt.airline", string="Airline", required=True)
    flight_number = fields.Char(required=True)

    departure_airport_id = fields.Many2one("flt.airport", string="Departure Airport", required=True)
    departure_datetime = fields.Datetime(string="Departure", required=True, index=True)
    departure_terminal = fields.Char(string="Departure Terminal")

    arrival_airport_id = fields.Many2one("flt.airport", string="Arrival Airport", required=True)
    arrival_datetime = fields.Datetime(string="Arrival", required=True)
    arrival_terminal = fields.Char(string="Arrival Terminal")

    seat_number = fields.Char()
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("checked_in", "Checked In"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("delayed", "Delayed"),
        ],
        default="draft", required=True,
    )

    @api.constrains("departure_datetime", "arrival_datetime")
    def _check_departure_before_arrival(self):
        for segment in self:
            if (
                segment.departure_datetime
                and segment.arrival_datetime
                and segment.arrival_datetime <= segment.departure_datetime
            ):
                raise ValidationError("Arrival cannot be before (or equal to) departure on a flight segment.")

    @api.constrains("departure_airport_id", "arrival_airport_id")
    def _check_different_airports(self):
        for segment in self:
            if segment.departure_airport_id and segment.departure_airport_id == segment.arrival_airport_id:
                raise ValidationError("Departure and arrival airport cannot be the same.")
