# Copyright (c) 2025 Daniel Reis
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    enqueue_server_action = fields.Boolean(
        string="Enqueue Instead of Execute",
        help="If enabled, this server action will be queued"
        " instead of executed directly.",
    )

    def run(self):
        if self._context.get("_from_queue_processor"):
            # Called from server.queue processor — allow real execution
            return super().run()

        for action in self:
            if action.enqueue_server_action:
                env = self.env
                active_model = env.context.get("active_model")
                active_id = env.context.get("active_id")
                active_ids = env.context.get("active_ids") or (
                    [active_id] if active_id else []
                )

                for res_id in active_ids:
                    env["server.queue"].create(
                        {
                            "name": f"Deferred: {action.name}",
                            "model_name": active_model,
                            "res_id": res_id,
                            "server_action_id": action.id,
                            "kwargs": str(
                                {
                                    k: v
                                    for k, v in env.context.items()
                                    if not k.startswith("active_")
                                }
                            ),
                        }
                    )
                    _logger.info(
                        "Action %s deferred and enqueued for record %s",
                        action.name,
                        res_id,
                    )
                return True

        # Default behavior
        return super().run()
