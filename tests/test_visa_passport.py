# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVisaPassport(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Amir Traveler", "email": "amir@example.com"})
        self.country = self.env.ref("base.ae")
        self.today = date.today()

    def _make_passport(self, **extra):
        vals = {
            "partner_id": self.partner.id,
            "passport_number": "P1234567",
            "full_name": "Amir Traveler",
            "issue_date": self.today - timedelta(days=365),
            "expiry_date": self.today + timedelta(days=365 * 5),
            "status": "valid",
        }
        vals.update(extra)
        return self.env["flt.passport"].create(vals)

    def test_visa_creation_gets_sequence_name(self):
        passport = self._make_passport()
        visa = self.env["flt.visa"].create({
            "partner_id": self.partner.id,
            "passport_id": passport.id,
            "country_id": self.country.id,
            "visa_type": "tourist",
            "issue_date": self.today,
            "expiry_date": self.today + timedelta(days=90),
            "status": "active",
        })
        self.assertTrue(visa.name.startswith("FLT/VISA/"))

    def test_visa_expiry_date_before_issue_date_raises(self):
        passport = self._make_passport()
        with self.assertRaises(ValidationError):
            self.env["flt.visa"].create({
                "partner_id": self.partner.id,
                "passport_id": passport.id,
                "country_id": self.country.id,
                "visa_type": "tourist",
                "issue_date": self.today,
                "expiry_date": self.today - timedelta(days=1),
            })

    def test_visa_expiry_detection(self):
        passport = self._make_passport()
        visa = self.env["flt.visa"].create({
            "partner_id": self.partner.id,
            "passport_id": passport.id,
            "country_id": self.country.id,
            "visa_type": "tourist",
            "issue_date": self.today - timedelta(days=400),
            "expiry_date": self.today - timedelta(days=1),
            "status": "active",
        })
        visa._compute_status_from_expiry()
        self.assertEqual(visa.status, "expired")

    def test_visa_reminder_generation_and_duplicate_prevention(self):
        passport = self._make_passport()
        visa = self.env["flt.visa"].create({
            "partner_id": self.partner.id,
            "passport_id": passport.id,
            "country_id": self.country.id,
            "visa_type": "tourist",
            "issue_date": self.today - timedelta(days=60),
            "expiry_date": self.today + timedelta(days=25),
            "status": "active",
        })
        visa._send_expiry_reminders("visa_expiry", [90, 60, 30, 15, 7, 1], "Your visa expires")
        count_after_first = self.env["flt.notification"].search_count([
            ("partner_id", "=", self.partner.id), ("category", "=", "visa_expiry"),
        ])
        self.assertEqual(count_after_first, 1)
        # Running it again immediately must NOT create a duplicate for the
        # same threshold.
        visa._send_expiry_reminders("visa_expiry", [90, 60, 30, 15, 7, 1], "Your visa expires")
        count_after_second = self.env["flt.notification"].search_count([
            ("partner_id", "=", self.partner.id), ("category", "=", "visa_expiry"),
        ])
        self.assertEqual(count_after_second, 1)

    def test_passport_expiry_detection(self):
        passport = self._make_passport(expiry_date=self.today - timedelta(days=1))
        passport._compute_status_from_expiry()
        self.assertEqual(passport.status, "expired")

    def test_passport_expiring_soon_detection(self):
        passport = self._make_passport(expiry_date=self.today + timedelta(days=30))
        passport._compute_status_from_expiry(soon_days=90)
        self.assertEqual(passport.status, "expiring_soon")

    def test_draft_passport_expiry_not_touched(self):
        passport = self._make_passport(status="draft", expiry_date=self.today - timedelta(days=1))
        passport._compute_status_from_expiry()
        self.assertEqual(passport.status, "draft")
