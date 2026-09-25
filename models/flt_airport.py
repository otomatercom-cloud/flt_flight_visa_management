# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FltAirport(models.Model):
    _name = "flt.airport"
    _description = "Airport"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(string="IATA Code", size=3, index=True)
    city = fields.Char()
    country_id = fields.Many2one("res.country", string="Country")
    active = fields.Boolean(default=True)

    _sql_unique_code = models.Constraint(
        "unique(code)", "Airport IATA code must be unique."
    )

    @api.depends("name", "code")
    def _compute_display_name(self):
        for airport in self:
            airport.display_name = (
                f"{airport.name} ({airport.code})" if airport.code else airport.name
            )
