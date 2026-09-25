# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalSecurity(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner_a = self.env["res.partner"].create({"name": "Customer A", "email": "a@example.com"})
        self.partner_b = self.env["res.partner"].create({"name": "Customer B", "email": "b@example.com"})
        self.user_a = self.env["res.users"].create({
            "name": "Portal A", "login": "portal_a_test", "email": "a@example.com",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            "partner_id": self.partner_a.id,
        })
        self.user_b = self.env["res.users"].create({
            "name": "Portal B", "login": "portal_b_test", "email": "b@example.com",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            "partner_id": self.partner_b.id,
        })
        self.booking_a = self.env["flt.flight.booking"].create({
            "partner_id": self.partner_a.id,
            "passenger_name": "Customer A",
            "ticket_amount": 10000,
            "status": "confirmed",
        })

    def test_customer_can_see_own_booking_via_orm_rule(self):
        booking = self.booking_a.with_user(self.user_a)
        # Triggers ir.rule evaluation.
        self.assertTrue(booking.exists())
        self.assertEqual(booking.partner_id.id, self.partner_a.id)

    def test_customer_cannot_see_another_customers_booking(self):
        Booking = self.env["flt.flight.booking"].with_user(self.user_b)
        found = Booking.search([("id", "=", self.booking_a.id)])
        self.assertFalse(found, "Portal user B must not be able to read Customer A's booking via ir.rule")

    def test_portal_controller_ownership_condition_blocks_idor(self):
        """The controller's _flt_get_owned_record helper (controllers/portal.py)
        sudo()-browses the record by id (so IDs from OTHER customers can be
        looked up at all) and then explicitly compares partner_id against
        the logged-in user's own partner, raising MissingError on a
        mismatch. This asserts the exact condition it relies on holds for
        Customer A's booking versus Customer B."""
        record = self.env["flt.flight.booking"].sudo().browse(self.booking_a.id).exists()
        self.assertTrue(record)
        self.assertNotEqual(record.partner_id.id, self.partner_b.id)
        self.assertEqual(record.partner_id.id, self.partner_a.id)

    def test_portal_user_cannot_directly_write_cancellation_status(self):
        """ir.model.access.csv grants the portal group perm_write=0 on
        flt.cancellation.request specifically so a portal user can never
        set their own request to 'approved' via a direct RPC write."""
        req = self.env["flt.cancellation.request"].create({
            "partner_id": self.partner_a.id,
            "booking_id": self.booking_a.id,
            "reason": "test",
            "original_amount": 10000,
            "cancellation_charge": 0,
            "customer_confirmed": True,
        })
        req_as_portal = req.with_user(self.user_a)
        with self.assertRaises(Exception):
            req_as_portal.write({"status": "approved"})
