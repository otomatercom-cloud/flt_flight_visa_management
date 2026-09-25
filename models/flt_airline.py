# -*- coding: utf-8 -*-
from odoo import fields, models


class FltAirline(models.Model):
    _name = "flt.airline"
    _description = "Airline"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(string="IATA Code", size=3, index=True)
    active = fields.Boolean(default=True)

    _sql_unique_code = models.Constraint(
        "unique(code)", "Airline IATA code must be unique."
    )
