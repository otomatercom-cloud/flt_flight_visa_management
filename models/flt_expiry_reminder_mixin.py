# -*- coding: utf-8 -*-
from odoo import fields, models


class FltExpiryReminderMixin(models.AbstractModel):
    """Shared batch-reminder logic reused by flt.passport and flt.visa so
    the centralized cron doesn't need type-specific branches and no
    per-record cron/notification logic is duplicated."""

    _name = "flt.expiry.reminder.mixin"
    _description = "FLT Expiry Reminder Mixin"

    last_reminder_days = fields.Integer(
        help="Smallest days-before-expiry threshold already notified for, "
             "so the batch reminder cron never sends the same threshold twice.",
    )

    def _send_expiry_reminders(self, category, reminder_days, title_prefix):
        today = fields.Date.context_today(self)
        to_notify = []
        for record in self:
            if not record.expiry_date or record.expiry_date < today:
                continue
            days_left = (record.expiry_date - today).days
            due_threshold = next(
                (d for d in reminder_days if days_left <= d and d < (record.last_reminder_days or 10 ** 6)),
                None,
            )
            if due_threshold is not None:
                to_notify.append((record, due_threshold, days_left))
        for record, threshold, days_left in to_notify:
            record.env["flt.notification"].create_notification(
                partner=record.partner_id,
                category=category,
                title=f"{title_prefix} in {days_left} day(s)",
                message=(
                    f"{title_prefix} on {record.expiry_date} (in {days_left} day(s)). "
                    "Please arrange renewal in good time."
                ),
                related_record=record,
            )
            record.last_reminder_days = threshold
