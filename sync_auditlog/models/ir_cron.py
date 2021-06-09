# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import fields, models


class ir_cron(models.Model):
    _inherit = "ir.cron"

    lastcall = fields.Datetime(
        string="Last Job Run Timestamp Date",
        default=fields.Datetime.now,
        help="Last job run timestamp date for this job.",
    )
