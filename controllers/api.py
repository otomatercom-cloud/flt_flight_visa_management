# -*- coding: utf-8 -*-
"""JSON REST API for the FLT Next.js customer SaaS frontend.

Design rules (see README's "Next.js API" section):
- Plain REST over HTTP, not JSON-RPC: every route is type="http" so a
  non-Odoo client (Next.js server) gets ordinary status codes and a bare
  JSON body, not the JSON-RPC 2.0 envelope.
- auth="user" everywhere except /auth/login: the caller (the Next.js
  server, never the browser directly) must present a valid Odoo session
  cookie. Next.js is a server-to-server client of this API; it stores the
  Odoo session_id itself and forwards it as a Cookie header on each call.
- Every route re-derives request.env.user.partner_id and compares it
  against the record being accessed before returning anything — the same
  ownership discipline as controllers/portal.py. No id from the URL is
  ever trusted on its own.
- No business calculation happens here: charge/refund/status values are
  read straight off the ORM (which is what already enforces the real
  business rules in flt_cancellation_request.py etc.).
"""
import json
import logging

from odoo import http
from odoo.exceptions import AccessDenied, MissingError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json_error(message, status=400, code="error"):
    return request.make_json_response({"error": {"code": code, "message": message}}, status=status)


def _require_json_body():
    try:
        return request.get_json_data() or {}
    except Exception:
        try:
            return json.loads(request.httprequest.data or b"{}")
        except Exception:
            return {}


def flt_api_route(**route_kwargs):
    """Wraps http.route with the JSON error-handling convention used by
    every endpoint below: business/auth errors become a clean JSON error
    response with an appropriate status code instead of an Odoo traceback
    ever reaching the customer (never expose raw tracebacks to portal
    users)."""
    def decorator(fn):
        @http.route(**route_kwargs)
        def wrapped(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except MissingError:
                return _json_error("Not found.", status=404, code="not_found")
            except AccessDenied:
                return _json_error("Access denied.", status=403, code="access_denied")
            except UserError as e:
                return _json_error(str(e), status=400, code="user_error")
            except Exception:
                # Always log the real traceback server-side before returning
                # the generic message — swallowing it silently (as this did
                # before) makes production errors undiagnosable from the log.
                _logger.exception("Unhandled error in FLT API route %s", fn.__name__)
                request.env.cr.rollback()
                return _json_error("Something went wrong. Please try again.", status=500, code="server_error")
        wrapped.__name__ = fn.__name__
        return wrapped
    return decorator


class FltApiController(http.Controller):

    # ------------------------------------------------------------------
    # Serializers — single place mapping ORM records to the JSON shapes
    # the Next.js TypeScript types (lib/types.ts) mirror exactly.
    # ------------------------------------------------------------------
    @staticmethod
    def _serialize_partner(partner):
        return {
            "id": partner.id,
            "name": partner.name,
            "email": partner.email,
            "phone": partner.phone,
            "nationality": partner.flt_nationality_id.name or None,
            "emergency_contact_name": partner.flt_emergency_contact_name or None,
            "emergency_contact_phone": partner.flt_emergency_contact_phone or None,
            "street": partner.street or None,
            "city": partner.city or None,
            "country": partner.country_id.name or None,
        }

    @staticmethod
    def _serialize_segment(segment):
        return {
            "id": segment.id,
            "sequence": segment.sequence,
            "airline": segment.airline_id.name,
            "flight_number": segment.flight_number,
            "departure_airport": {
                "code": segment.departure_airport_id.code,
                "name": segment.departure_airport_id.name,
                "city": segment.departure_airport_id.city,
            },
            "departure_datetime": segment.departure_datetime and segment.departure_datetime.isoformat(),
            "departure_terminal": segment.departure_terminal or None,
            "arrival_airport": {
                "code": segment.arrival_airport_id.code,
                "name": segment.arrival_airport_id.name,
                "city": segment.arrival_airport_id.city,
            },
            "arrival_datetime": segment.arrival_datetime and segment.arrival_datetime.isoformat(),
            "arrival_terminal": segment.arrival_terminal or None,
            "seat_number": segment.seat_number or None,
            "status": segment.status,
        }

    @classmethod
    def _serialize_booking(cls, booking, detail=False):
        data = {
            "id": booking.id,
            "name": booking.name,
            "pnr": booking.pnr or None,
            "booking_date": booking.booking_date and booking.booking_date.isoformat(),
            "status": booking.status,
            "payment_status": booking.payment_status,
            "ticket_class": booking.ticket_class,
            "ticket_amount": booking.ticket_amount,
            "currency": booking.currency_id.name,
            "currency_symbol": booking.currency_id.symbol,
            "passenger_name": booking.passenger_name,
            "first_segment": cls._serialize_segment(booking.segment_ids.sorted("sequence")[:1]) if booking.segment_ids else None,
            "segment_count": len(booking.segment_ids),
        }
        if detail:
            data.update({
                "passenger_passport_number": booking.passenger_passport_id.passport_number or None,
                "passenger_contact": booking.passenger_contact or None,
                "ticket_number": booking.ticket_number or None,
                "baggage_allowance": booking.baggage_allowance or None,
                "segments": [cls._serialize_segment(s) for s in booking.segment_ids.sorted("sequence")],
                "cancellable": booking._is_portal_cancellable(),
                "airline_cancellation_reason": booking.airline_cancellation_reason or None,
                "airline_cancellation_action": booking.airline_cancellation_action or None,
            })
        return data

    @staticmethod
    def _serialize_visa(visa, detail=False):
        data = {
            "id": visa.id,
            "name": visa.name,
            "country": visa.country_id.name,
            "country_code": visa.country_id.code,
            "visa_type": visa.visa_type,
            "expiry_date": visa.expiry_date and visa.expiry_date.isoformat(),
            "status": visa.status,
        }
        if detail:
            data.update({
                "visa_number": visa.visa_number or None,
                "issue_date": visa.issue_date and visa.issue_date.isoformat(),
                "renewal_date": visa.renewal_date and visa.renewal_date.isoformat(),
                "entry_type": visa.entry_type,
                "number_of_entries": visa.number_of_entries,
                "passport_number": visa.passport_id.passport_number or None,
            })
        return data

    @staticmethod
    def _serialize_passport(passport):
        return {
            "id": passport.id,
            "passport_number": passport.passport_number,
            "full_name": passport.full_name,
            "nationality": passport.nationality_id.name or None,
            "issue_date": passport.issue_date and passport.issue_date.isoformat(),
            "expiry_date": passport.expiry_date and passport.expiry_date.isoformat(),
            "status": passport.status,
        }

    @staticmethod
    def _serialize_document(document):
        return {
            "id": document.id,
            "name": document.name,
            "document_type": document.document_type,
            "upload_date": document.upload_date and document.upload_date.isoformat(),
            "expiry_date": document.expiry_date and document.expiry_date.isoformat(),
            "status": document.status,
            "download_url": f"/api/flt/documents/{document.id}/file",
        }

    @staticmethod
    def _serialize_notification(notification):
        return {
            "id": notification.id,
            "category": notification.category,
            "title": notification.title,
            "message": notification.message,
            "date": notification.date and notification.date.isoformat(),
            "is_read": notification.is_read,
            "related_model": notification.related_model or None,
            "related_id": notification.related_res_id or None,
        }

    @staticmethod
    def _serialize_cancellation_request(req):
        return {
            "id": req.id,
            "name": req.name,
            "booking_name": req.booking_id.name,
            "booking_id": req.booking_id.id,
            "status": req.status,
            "refund_status": req.refund_status,
            "request_date": req.request_date and req.request_date.isoformat(),
            "original_amount": req.original_amount,
            "cancellation_charge": req.cancellation_charge,
            "refund_amount": req.refund_amount,
            "final_refund_amount": req.final_refund_amount,
            "currency_symbol": req.currency_id.symbol,
            "remarks": req.remarks or None,
        }

    # ------------------------------------------------------------------
    # Ownership helper (same contract as portal.py's _flt_get_owned_record)
    # ------------------------------------------------------------------
    def _get_owned(self, model_name, record_id):
        partner = request.env.user.partner_id
        record = request.env[model_name].sudo().browse(int(record_id)).exists()
        if not record or record.partner_id.id != partner.id:
            raise MissingError("Record not found.")
        return record

    # ============================== AUTH ==============================
    @flt_api_route(route="/api/flt/auth/signup", type="http", auth="none", methods=["POST"], csrf=False)
    def auth_signup(self, **kw):
        body = _require_json_body()
        name = (body.get("name") or "").strip()
        login = (body.get("login") or "").strip().lower()
        password = body.get("password") or ""
        phone = (body.get("phone") or "").strip() or False

        if not name or not login or not password:
            return _json_error("Name, email and password are required.", status=400, code="invalid_input")
        if len(password) < 8:
            return _json_error("Password must be at least 8 characters.", status=400, code="weak_password")

        Users = request.env["res.users"].sudo()
        Partner = request.env["res.partner"].sudo()

        if Users.search_count([("login", "=", login)]):
            return _json_error("An account with this email already exists.", status=409, code="already_exists")

        # Reuse an existing contact record (e.g. one staff already created
        # from a booking) if the email matches one with no login yet;
        # otherwise create a fresh customer contact.
        partner = Partner.search([("email", "=", login), ("user_ids", "=", False)], limit=1)
        if not partner:
            partner = Partner.create({"name": name, "email": login, "phone": phone, "company_type": "person"})
        else:
            partner.write({"name": name, "phone": phone or partner.phone})

        portal_group = request.env.ref("base.group_portal")
        try:
            # no_reset_password=True: without it, res.users.create() with
            # both 'email' and 'password' set silently fires auth_signup's
            # invite-email flow and leaves the password we just set unusable
            # until an invite link is clicked — no error, just a broken
            # login. group_ids (not groups_id) is the Odoo 19 field name.
            user = Users.with_context(no_reset_password=True).create({
                "name": name,
                "login": login,
                "email": login,
                "password": password,
                "partner_id": partner.id,
                "group_ids": [(6, 0, [portal_group.id])],
            })
        except Exception:
            _logger.exception("Signup failed creating portal user for %s", login)
            request.env.cr.rollback()
            return _json_error("Couldn't create this account. Please try again.", status=500, code="server_error")

        db = request.db or http.db_monodb()
        uid = request.session.authenticate(db, login, password)
        if not uid:
            # Account was created but the immediate sign-in failed for some
            # environment reason — ask them to log in explicitly instead.
            return request.make_json_response({"created": True, "session_id": None})

        return request.make_json_response({
            "session_id": request.session.sid,
            "partner": self._serialize_partner(user.partner_id),
        }, status=201)

    @flt_api_route(route="/api/flt/auth/login", type="http", auth="none", methods=["POST"], csrf=False)
    def auth_login(self, **kw):
        body = _require_json_body()
        login = (body.get("login") or "").strip()
        password = body.get("password") or ""
        if not login or not password:
            return _json_error("Email and password are required.", status=400, code="invalid_input")

        db = request.db or http.db_monodb()
        try:
            uid = request.session.authenticate(db, login, password)
        except AccessDenied:
            uid = False
        if not uid:
            return _json_error("Invalid email or password.", status=401, code="invalid_credentials")

        user = request.env["res.users"].sudo().browse(uid)
        if not user.has_group("base.group_portal") and not user.has_group("flt_flight_visa_management.group_flt_user"):
            request.session.logout(keep_db=True)
            return _json_error("This account does not have portal access.", status=403, code="not_portal_user")

        return request.make_json_response({
            "session_id": request.session.sid,
            "partner": self._serialize_partner(user.partner_id),
        })

    @flt_api_route(route="/api/flt/auth/logout", type="http", auth="user", methods=["POST"], csrf=False)
    def auth_logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.make_json_response({"ok": True})

    @flt_api_route(route="/api/flt/auth/me", type="http", auth="user", methods=["GET"], csrf=False)
    def auth_me(self, **kw):
        return request.make_json_response(self._serialize_partner(request.env.user.partner_id))

    # ============================ DASHBOARD ============================
    @flt_api_route(route="/api/flt/dashboard", type="http", auth="user", methods=["GET"], csrf=False)
    def dashboard(self, **kw):
        partner = request.env.user.partner_id
        Booking = request.env["flt.flight.booking"].sudo()
        Visa = request.env["flt.visa"].sudo()
        Passport = request.env["flt.passport"].sudo()
        Notification = request.env["flt.notification"].sudo()

        upcoming = Booking.search([
            ("partner_id", "=", partner.id),
            ("status", "not in", ("cancelled", "airline_cancelled", "completed")),
        ], order="booking_date desc")
        next_flight = upcoming[:1]
        alerts = Booking.search([
            ("partner_id", "=", partner.id),
            ("status", "=", "airline_cancelled"),
        ], limit=5)
        active_visas = Visa.search([("partner_id", "=", partner.id), ("status", "=", "active")], limit=5)
        passports = Passport.search([("partner_id", "=", partner.id)], limit=5)
        notifications = Notification.search(
            [("partner_id", "=", partner.id), ("staff_only", "=", False)], order="date desc", limit=5
        )
        pending_actions = request.env["flt.cancellation.request"].sudo().search_count([
            ("partner_id", "=", partner.id), ("status", "in", ("submitted", "under_review")),
        ])

        return request.make_json_response({
            "kpis": {
                "upcoming_flights": len(upcoming),
                "active_visas": Visa.search_count([("partner_id", "=", partner.id), ("status", "=", "active")]),
                "pending_actions": pending_actions,
                "unread_notifications": Notification.search_count(
                    [("partner_id", "=", partner.id), ("staff_only", "=", False), ("is_read", "=", False)]
                ),
            },
            "alerts": [self._serialize_booking(b) for b in alerts],
            "next_flight": self._serialize_booking(next_flight, detail=True) if next_flight else None,
            "visas": [self._serialize_visa(v) for v in active_visas],
            "passports": [self._serialize_passport(p) for p in passports],
            "notifications": [self._serialize_notification(n) for n in notifications],
        })

    # ============================= FLIGHTS =============================
    @flt_api_route(route="/api/flt/flights", type="http", auth="user", methods=["GET"], csrf=False)
    def flights_list(self, filter="all", page="1", **kw):
        partner = request.env.user.partner_id
        Booking = request.env["flt.flight.booking"].sudo()
        domain = [("partner_id", "=", partner.id)]
        if filter == "upcoming":
            domain += [("status", "not in", ("cancelled", "airline_cancelled", "completed"))]
        elif filter == "completed":
            domain += [("status", "=", "completed")]
        elif filter == "cancelled":
            domain += [("status", "in", ("cancelled", "airline_cancelled"))]

        page = max(int(page or 1), 1)
        page_size = 20
        total = Booking.search_count(domain)
        bookings = Booking.search(domain, order="booking_date desc", limit=page_size, offset=(page - 1) * page_size)
        return request.make_json_response({
            "items": [self._serialize_booking(b) for b in bookings],
            "page": page,
            "page_size": page_size,
            "total": total,
        })

    @flt_api_route(route="/api/flt/flights/<int:booking_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def flight_detail(self, booking_id, **kw):
        booking = self._get_owned("flt.flight.booking", booking_id)
        quote = request.env["flt.cancellation.request"].sudo().quote_cancellation(booking)
        data = self._serialize_booking(booking, detail=True)
        data["cancellation_quote"] = {
            "charge": quote["charge"],
            "refund": quote["refund"],
            "policy_name": quote["policy"].name if quote["policy"] else None,
        }
        return request.make_json_response(data)

    @flt_api_route(
        route="/api/flt/flights/<int:booking_id>/cancel", type="http", auth="user", methods=["POST"], csrf=False,
    )
    def flight_cancel(self, booking_id, **kw):
        booking = self._get_owned("flt.flight.booking", booking_id)
        body = _require_json_body()
        if not booking._is_portal_cancellable():
            return _json_error("This booking is no longer eligible for self-service cancellation.", status=400)
        if not body.get("confirm"):
            return _json_error("You must confirm you understand the cancellation policy.", status=400)

        quote = request.env["flt.cancellation.request"].sudo().quote_cancellation(booking)
        cancel_request = request.env["flt.cancellation.request"].sudo().create({
            "partner_id": booking.partner_id.id,
            "booking_id": booking.id,
            "reason": body.get("reason") or "Customer requested cancellation via SaaS portal.",
            "original_amount": booking.ticket_amount,
            "cancellation_charge": quote["charge"],
            "policy_id": quote["policy"].id if quote["policy"] else False,
            "customer_confirmed": True,
        })
        cancel_request.action_submit()
        return request.make_json_response(self._serialize_cancellation_request(cancel_request), status=201)

    @flt_api_route(route="/api/flt/cancellation-requests", type="http", auth="user", methods=["GET"], csrf=False)
    def cancellation_requests_list(self, **kw):
        partner = request.env.user.partner_id
        requests = request.env["flt.cancellation.request"].sudo().search(
            [("partner_id", "=", partner.id)], order="request_date desc"
        )
        return request.make_json_response({"items": [self._serialize_cancellation_request(r) for r in requests]})

    @flt_api_route(
        route="/api/flt/cancellation-requests/<int:request_id>", type="http", auth="user", methods=["GET"], csrf=False,
    )
    def cancellation_request_detail(self, request_id, **kw):
        req = self._get_owned("flt.cancellation.request", request_id)
        return request.make_json_response(self._serialize_cancellation_request(req))

    # =============================== VISA ===============================
    @flt_api_route(route="/api/flt/visas", type="http", auth="user", methods=["GET"], csrf=False)
    def visas_list(self, **kw):
        partner = request.env.user.partner_id
        visas = request.env["flt.visa"].sudo().search([("partner_id", "=", partner.id)], order="expiry_date")
        return request.make_json_response({"items": [self._serialize_visa(v) for v in visas]})

    @flt_api_route(route="/api/flt/visas/<int:visa_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def visa_detail(self, visa_id, **kw):
        visa = self._get_owned("flt.visa", visa_id)
        return request.make_json_response(self._serialize_visa(visa, detail=True))

    # ============================= PASSPORT =============================
    @flt_api_route(route="/api/flt/passports", type="http", auth="user", methods=["GET"], csrf=False)
    def passports_list(self, **kw):
        partner = request.env.user.partner_id
        passports = request.env["flt.passport"].sudo().search([("partner_id", "=", partner.id)], order="expiry_date")
        return request.make_json_response({"items": [self._serialize_passport(p) for p in passports]})

    # ============================ DOCUMENTS =============================
    @flt_api_route(route="/api/flt/documents", type="http", auth="user", methods=["GET"], csrf=False)
    def documents_list(self, **kw):
        partner = request.env.user.partner_id
        documents = request.env["flt.document"].sudo().search(
            [("partner_id", "=", partner.id)], order="upload_date desc"
        )
        return request.make_json_response({"items": [self._serialize_document(d) for d in documents]})

    @flt_api_route(route="/api/flt/documents/upload", type="http", auth="user", methods=["POST"], csrf=False)
    def documents_upload(self, name=None, document_type=None, upload=None, **kw):
        import base64

        partner = request.env.user.partner_id
        if not upload:
            return _json_error("No file provided.", status=400, code="missing_file")
        file_content = upload.read()
        if len(file_content) > 15 * 1024 * 1024:
            return _json_error("File is too large (max 15MB).", status=400, code="file_too_large")

        attachment = request.env["ir.attachment"].sudo().create({
            "name": upload.filename,
            "res_model": "flt.document",
            "type": "binary",
            "datas": base64.b64encode(file_content),
        })
        document = request.env["flt.document"].sudo().create({
            "name": name or upload.filename,
            "partner_id": partner.id,
            "document_type": document_type or "other",
            "attachment_id": attachment.id,
        })
        return request.make_json_response(self._serialize_document(document), status=201)

    @flt_api_route(
        route="/api/flt/documents/<int:document_id>/file", type="http", auth="user", methods=["GET"], csrf=False,
    )
    def document_file(self, document_id, **kw):
        document = self._get_owned("flt.document", document_id)
        attachment = document.attachment_id.sudo()
        if not attachment:
            return _json_error("File not found.", status=404)
        headers = [
            ("Content-Type", attachment.mimetype or "application/octet-stream"),
            ("Content-Disposition", http.content_disposition(attachment.name)),
        ]
        return request.make_response(attachment.raw, headers=headers)

    # =========================== NOTIFICATIONS ===========================
    @flt_api_route(route="/api/flt/notifications", type="http", auth="user", methods=["GET"], csrf=False)
    def notifications_list(self, **kw):
        partner = request.env.user.partner_id
        notifications = request.env["flt.notification"].sudo().search(
            [("partner_id", "=", partner.id), ("staff_only", "=", False)], order="date desc"
        )
        return request.make_json_response({"items": [self._serialize_notification(n) for n in notifications]})

    @flt_api_route(
        route="/api/flt/notifications/<int:notification_id>/read", type="http", auth="user", methods=["POST"], csrf=False,
    )
    def notification_mark_read(self, notification_id, **kw):
        notification = self._get_owned("flt.notification", notification_id)
        notification.write({"is_read": True})
        return request.make_json_response(self._serialize_notification(notification))

    # ============================== PROFILE ==============================
    @flt_api_route(route="/api/flt/profile", type="http", auth="user", methods=["GET"], csrf=False)
    def profile_get(self, **kw):
        return request.make_json_response(self._serialize_partner(request.env.user.partner_id))

    @flt_api_route(route="/api/flt/profile", type="http", auth="user", methods=["PATCH"], csrf=False)
    def profile_update(self, **kw):
        body = _require_json_body()
        partner = request.env.user.partner_id
        # Only fields a customer may self-edit; everything business-critical
        # (bookings, visas, passports, statuses) stays staff/backend-only.
        # Keys here match the API contract's (unprefixed) field names, as
        # returned by _serialize_partner, and are mapped to the actual
        # model fields below.
        field_map = {
            "phone": "phone",
            "street": "street",
            "city": "city",
            "emergency_contact_name": "flt_emergency_contact_name",
            "emergency_contact_phone": "flt_emergency_contact_phone",
        }
        vals = {field_map[k]: v for k, v in body.items() if k in field_map}
        if vals:
            partner.sudo().write(vals)
        return request.make_json_response(self._serialize_partner(partner))
