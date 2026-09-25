{
    "name": "Flight & Visa Management",
    "version": "19.0.1.0.0",
    "category": "Services/Travel",
    "summary": "Flight bookings, visas, passports, cancellations and refunds with a customer portal",
    "description": """
Flight & Visa Management (FLT)
===============================
Production-grade flight, visa, passport and travel document management
for internal staff, with a secure customer portal.

Key features:
- Multi-segment flight bookings with full status lifecycle
- Configurable cancellation policies and refund calculation
- Visa and passport expiry tracking with batched reminders
- Generic document management on top of ir.attachment
- Generic notification center with mail.template based emails
- Secure customer portal (own-records-only access)
- Centralized cron-based expiry/reminder processing
""",
    "author": "Automater",
    "website": "https://otomater.com",
    "license": "OPL-1",
    "depends": ["base", "base_setup", "mail", "portal", "web"],
    "data": [
        "security/flt_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/flt_cancellation_policy_data.xml",
        "data/mail_templates.xml",
        "data/ir_cron.xml",
        "views/flt_airline_views.xml",
        "views/flt_airport_views.xml",
        "views/flt_passport_views.xml",
        "views/flt_visa_views.xml",
        "views/flt_flight_segment_views.xml",
        "views/flt_flight_booking_views.xml",
        "views/flt_cancellation_policy_views.xml",
        "views/flt_cancellation_request_views.xml",
        "views/flt_document_views.xml",
        "views/flt_notification_views.xml",
        "views/res_partner_views.xml",
        "views/flt_dashboard_views.xml",
        "views/flt_res_config_settings_views.xml",
        "views/flt_menus.xml",
        "portal/portal_templates.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
