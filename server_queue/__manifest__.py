# Copyright (c) 2025 Daniel Reis
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

{
    "name": "Server Queue",
    "summary": "Generic server-side task queueing mechanism",
    "version": "18.0.1.0.0",
    "author": "OCA",
    "license": "AGPL-3",
    "category": "Tools",
    "website": "https://github.com/OCA/server-tools",
    "depends": ["base"],
    "data": [
        "security/server_queue_security.xml",
        "security/server_queue_groups.xml",
        "security/ir.model.access.csv",
        "security/ir.model.access.csv",
        "data/server_queue_data.xml",
        "data/mail_template_server_queue_failed.xml",
        "data/ir_cron_notify.xml",
        "data/ir_cron_cleanup.xml",
        "views/server_queue_job_views.xml"
        "views/server_queue_search.xml",
        "views/server_queue_dashboard.xml",
        "views/server_queue_menu.xml",
    ],
    "installable": True,
    "application": True
}