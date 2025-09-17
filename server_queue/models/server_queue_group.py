# Copyright (c) 2025 Daniel Reis
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from odoo import fields, models


class ServerQueueGroup(models.Model):
    _name = "server.queue.group"
    _description = "Server Queue Group"

    name = fields.Char(required=True)
    description = fields.Text()
    color = fields.Integer(string="Color Index")
    active = fields.Boolean(default=True)
    job_ids = fields.One2many("server.queue", "group_id", string="Jobs")

    default_max_retries = fields.Integer(default=0)
    default_delay_seconds = fields.Integer(default=60)
