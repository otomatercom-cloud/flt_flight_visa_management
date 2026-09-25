# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class FltCustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        if "flt_booking_count" in counters:
            values["flt_booking_count"] = request.env["flt.flight.booking"].search_count(
                [("partner_id", "=", partner.id)]
            )
        if "flt_visa_count" in counters:
            values["flt_visa_count"] = request.env["flt.visa"].search_count(
                [("partner_id", "=", partner.id)]
            )
        if "flt_passport_count" in counters:
            values["flt_passport_count"] = request.env["flt.passport"].search_count(
                [("partner_id", "=", partner.id)]
            )
        if "flt_document_count" in counters:
            values["flt_document_count"] = request.env["flt.document"].search_count(
                [("partner_id", "=", partner.id)]
            )
        if "flt_cancellation_count" in counters:
            values["flt_cancellation_count"] = request.env["flt.cancellation.request"].search_count(
                [("partner_id", "=", partner.id)]
            )
        return values

    # ------------------------------------------------------------------
    # Ownership helper — every route below MUST call this before returning
    # or acting on any record looked up by an id from the URL. Never trust
    # the id alone; always re-derive the owning partner server-side.
    # ------------------------------------------------------------------
    def _flt_get_owned_record(self, model_name, record_id):
        partner = request.env.user.partner_id
        record = request.env[model_name].sudo().browse(record_id).exists()
        if not record or record.partner_id.id != partner.id:
            raise MissingError("This record does not exist or you do not have access to it.")
        return record

    # ---------------------------- Dashboard ----------------------------
    @http.route(["/my/travel"], type="http", auth="user", website=True)
    def flt_dashboard(self, **kw):
        partner = request.env.user.partner_id
        Booking = request.env["flt.flight.booking"].sudo()
        Visa = request.env["flt.visa"].sudo()
        Passport = request.env["flt.passport"].sudo()
        Notification = request.env["flt.notification"].sudo()

        upcoming = Booking.search([
            ("partner_id", "=", partner.id),
            ("status", "not in", ("cancelled", "airline_cancelled", "completed")),
            ("segment_ids.departure_datetime", ">=", fields.Datetime.now()),
        ], limit=5)
        visas = Visa.search([("partner_id", "=", partner.id), ("status", "=", "active")], limit=5)
        passports = Passport.search([("partner_id", "=", partner.id)], limit=5)
        notifications = Notification.search(
            [("partner_id", "=", partner.id), ("staff_only", "=", False)], limit=5, order="date desc"
        )
        values = {
            "upcoming_bookings": upcoming,
            "visas": visas,
            "passports": passports,
            "notifications": notifications,
            "page_name": "flt_dashboard",
        }
        return request.render("flt_flight_visa_management.portal_flt_dashboard", values)

    # ----------------------------- Flights ------------------------------
    @http.route(["/my/flights", "/my/flights/page/<int:page>"], type="http", auth="user", website=True)
    def flt_flights(self, page=1, sortby=None, filterby=None, **kw):
        partner = request.env.user.partner_id
        Booking = request.env["flt.flight.booking"].sudo()
        domain = [("partner_id", "=", partner.id)]

        searchbar_filters = {
            "all": {"label": "All", "domain": []},
            "upcoming": {"label": "Upcoming", "domain": [
                ("status", "not in", ("cancelled", "airline_cancelled", "completed")),
            ]},
            "past": {"label": "Past", "domain": [("status", "=", "completed")]},
            "cancelled": {"label": "Cancelled", "domain": [("status", "in", ("cancelled", "airline_cancelled"))]},
        }
        filterby = filterby or "all"
        domain += searchbar_filters[filterby]["domain"]

        booking_count = Booking.search_count(domain)
        pager = portal_pager(
            url="/my/flights", url_args={"filterby": filterby}, total=booking_count,
            page=page, step=self._items_per_page,
        )
        bookings = Booking.search(domain, order="booking_date desc", limit=self._items_per_page, offset=pager["offset"])
        values = {
            "bookings": bookings,
            "page_name": "flt_flights",
            "pager": pager,
            "filterby": filterby,
            "searchbar_filters": searchbar_filters,
            "default_url": "/my/flights",
        }
        return request.render("flt_flight_visa_management.portal_flt_flight_list", values)

    @http.route(["/my/flights/<int:booking_id>"], type="http", auth="user", website=True)
    def flt_flight_detail(self, booking_id, **kw):
        try:
            booking = self._flt_get_owned_record("flt.flight.booking", booking_id)
        except MissingError:
            return request.redirect("/my/flights")
        quote = request.env["flt.cancellation.request"].sudo().quote_cancellation(booking)
        values = {
            "booking": booking,
            "cancellable": booking._is_portal_cancellable(),
            "quote": quote,
            "page_name": "flt_flight_detail",
        }
        return request.render("flt_flight_visa_management.portal_flt_flight_detail", values)

    @http.route(["/my/flights/<int:booking_id>/cancel"], type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def flt_flight_request_cancellation(self, booking_id, reason=None, confirm=None, **kw):
        booking = self._flt_get_owned_record("flt.flight.booking", booking_id)
        if not booking._is_portal_cancellable():
            raise UserError("This booking is no longer eligible for a self-service cancellation request.")
        if not confirm:
            raise UserError("You must confirm that you understand the cancellation charges and refund conditions.")

        quote = request.env["flt.cancellation.request"].sudo().quote_cancellation(booking)
        vals = {
            "partner_id": booking.partner_id.id,
            "booking_id": booking.id,
            "reason": reason or "Customer requested cancellation via portal.",
            "original_amount": booking.ticket_amount,
            "cancellation_charge": quote["charge"],
            "policy_id": quote["policy"].id if quote["policy"] else False,
            "customer_confirmed": True,
        }
        cancel_request = request.env["flt.cancellation.request"].sudo().create(vals)
        cancel_request.action_submit()
        return request.redirect(f"/my/flights/{booking.id}")

    # ------------------------------ Visas -------------------------------
    @http.route(["/my/visas", "/my/visas/page/<int:page>"], type="http", auth="user", website=True)
    def flt_visas(self, page=1, **kw):
        partner = request.env.user.partner_id
        Visa = request.env["flt.visa"].sudo()
        domain = [("partner_id", "=", partner.id)]
        visa_count = Visa.search_count(domain)
        pager = portal_pager(url="/my/visas", total=visa_count, page=page, step=self._items_per_page)
        visas = Visa.search(domain, order="expiry_date", limit=self._items_per_page, offset=pager["offset"])
        values = {"visas": visas, "page_name": "flt_visas", "pager": pager}
        return request.render("flt_flight_visa_management.portal_flt_visa_list", values)

    @http.route(["/my/visas/<int:visa_id>"], type="http", auth="user", website=True)
    def flt_visa_detail(self, visa_id, **kw):
        try:
            visa = self._flt_get_owned_record("flt.visa", visa_id)
        except MissingError:
            return request.redirect("/my/visas")
        return request.render(
            "flt_flight_visa_management.portal_flt_visa_detail", {"visa": visa, "page_name": "flt_visa_detail"}
        )

    # ---------------------------- Passports -----------------------------
    @http.route(["/my/passports", "/my/passports/page/<int:page>"], type="http", auth="user", website=True)
    def flt_passports(self, page=1, **kw):
        partner = request.env.user.partner_id
        Passport = request.env["flt.passport"].sudo()
        domain = [("partner_id", "=", partner.id)]
        passport_count = Passport.search_count(domain)
        pager = portal_pager(url="/my/passports", total=passport_count, page=page, step=self._items_per_page)
        passports = Passport.search(domain, order="expiry_date", limit=self._items_per_page, offset=pager["offset"])
        values = {"passports": passports, "page_name": "flt_passports", "pager": pager}
        return request.render("flt_flight_visa_management.portal_flt_passport_list", values)

    # ---------------------------- Documents -----------------------------
    @http.route(["/my/documents"], type="http", auth="user", website=True)
    def flt_documents(self, **kw):
        partner = request.env.user.partner_id
        documents = request.env["flt.document"].sudo().search([("partner_id", "=", partner.id)], order="upload_date desc")
        values = {"documents": documents, "page_name": "flt_documents"}
        return request.render("flt_flight_visa_management.portal_flt_document_list", values)

    @http.route(["/my/documents/upload"], type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def flt_document_upload(self, name=None, document_type=None, upload=None, **kw):
        import base64

        partner = request.env.user.partner_id
        if not upload:
            raise UserError("Please choose a file to upload.")
        file_content = upload.read()
        attachment = request.env["ir.attachment"].sudo().create({
            "name": upload.filename,
            "res_model": "flt.document",
            "type": "binary",
            "datas": base64.b64encode(file_content),
        })
        request.env["flt.document"].sudo().create({
            "name": name or upload.filename,
            "partner_id": partner.id,
            "document_type": document_type or "other",
            "attachment_id": attachment.id,
        })
        return request.redirect("/my/documents")

    @http.route(["/my/notifications"], type="http", auth="user", website=True)
    def flt_notifications(self, **kw):
        partner = request.env.user.partner_id
        Notification = request.env["flt.notification"].sudo()
        notifications = Notification.search(
            [("partner_id", "=", partner.id), ("staff_only", "=", False)], order="date desc"
        )
        # Mark as read via a privileged sudo() write on the customer's own
        # records only — never grant the portal group direct ORM write
        # access to this model (see ir.model.access.csv).
        notifications.filtered(lambda n: not n.is_read).write({"is_read": True})
        values = {"notifications": notifications, "page_name": "flt_notifications"}
        return request.render("flt_flight_visa_management.portal_flt_notification_list", values)
