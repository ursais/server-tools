# Copyright (c) 2025 Daniel Reis
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)


class ServerQueue(models.Model):
    _name = "server.queue"
    _description = "Server Queue"
    _order = "create_date asc"

    name = fields.Char(required=True)
    group_id = fields.Many2one("server.queue.group", string="Group")
    run_at = fields.Datetime(
        default=lambda self: fields.Datetime.now(),
        index=True,
        help="Earliest time this job should run. "
        "Used for backoff/delayed execution.",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Run As User",
        default=lambda self: self.env.uid,
        required=True,
        help="The user under whose access rights this job will be executed.",
    )
    res_id = fields.Many2oneReference(string="Target Record", model_field="model_name")

    server_action_id = fields.Many2one("ir.actions.server", string="Server Action")
    model_name = fields.Char(string="Model", required=True)
    method_name = fields.Char(string="Method")
    args = fields.Text(string="Arguments (eval)")
    kwargs = fields.Text(string="Keyword Arguments (eval)")

    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("done", "Done"),
            ("failed", "Failed"),
            ("retry", "To Retry"),
        ],
        default="pending",
        required=True,
    )
    result = fields.Text()
    exception = fields.Text()
    attempt_count = fields.Integer(default=0)
    last_duration = fields.Float(string="Last Duration (sec)", digits=(16, 2))
    max_retries = fields.Integer(default=3)

    @api.model
    def enqueue(
        self,
        name,
        model_name,
        method_name=None,
        args=None,
        kwargs=None,
        res_id=None,
        server_action_id=None,
        max_retries=None,
        delay_seconds=None,
    ):
        values = {
            "name": name,
            "model_name": model_name,
            "method_name": method_name,
            "args": str(args or []),
            "kwargs": str(kwargs or {}),
            "res_id": res_id,
            "server_action_id": server_action_id,
        }
        return self.create(values)

    @api.constrains("method_name", "server_action_id")
    def _check_method_or_action(self):
        for rec in self:
            if not rec.method_name and not rec.server_action_id:
                raise ValidationError(
                    _("You must specify either a method name or a server action.")
                )

    def _run_server_action(self):
        for rec in self:
            context = self.env.context.copy()
            context.update({"active_model": rec.model_name})
            if rec.res_id:
                context.update({"active_id": rec.res_id, "active_ids": [rec.res_id]})
            extra_context = safe_eval(rec.kwargs or "{}")
            context.update(extra_context)
            rec.server_action_id.with_context(**context).run()

    def _run_model_method(self):
        for rec in self:
            model = self.env[rec.model_name]
            args = safe_eval(rec.args or "[]")
            kwargs = safe_eval(rec.kwargs or "{}")
            if rec.res_id:
                record = model.browse(rec.res_id)
                return getattr(record, rec.method_name)(*args, **kwargs)
            return getattr(model, rec.method_name)(*args, **kwargs)

    def process_job(self):
        for job in self:
            start_time = datetime.utcnow()
            if job.state not in ("pending", "retry"):
                raise ValidationError(_("Job must be in 'pending' or 'retry' state"))

            # Attempt atomic state transition from 'pending' or 'retry' to 'running'
            self.env.cr.execute(
                "UPDATE server_queue SET state = 'running' "
                "WHERE id = %s AND state IN ('pending', 'retry') RETURNING id",
                (job.id,),
            )
            if not self.env.cr.rowcount:
                continue  # Job already taken by another worker or changed state
            self.env.cr.commit()
            # NOTE: The job record may now contain outdated field values in memory.

            try:
                if job.server_action_id:
                    job._run_server_action()
                    result = "Server action executed"
                else:
                    result = job._run_model_method()
                duration = (datetime.utcnow() - start_time).total_seconds()
                job.write(
                    {
                        "state": "done",
                        "result": str(result),
                        "exception": False,
                        "attempt_count": job.attempt_count + 1,
                        "last_duration": duration,
                    }
                )
            except Exception as e:
                # Retry logic: set to 'retry' unless max retries exceeded
                delay_seconds = int(
                    job.env["ir.config_parameter"]
                    .sudo()
                    .get_param("server_queue.retry_delay_seconds", "60")
                )
                attempts = job.attempt_count + 1
                if job.attempt_count >= job.max_retries:
                    job.write({"state": "failed", "exception": str(e)})
                    _logger.exception("Failed to process job %s", job.name)
                else:
                    job.write(
                        {
                            "state": "retry"
                            if attempts < job.max_retries
                            else "failed",
                            "run_at": datetime.utcnow()
                            + timedelta(seconds=delay_seconds),
                            "exception": str(e),
                            "attempt_count": attempts,
                        }
                    )
            self.env.cr.commit()

    def action_run_now(self):
        self.process_job()

    def action_cancel(self):
        self.write({"state": "failed", "exception": "Cancelled manually by user."})

    def action_reset_pending(self):
        self.write({"state": "pending", "exception": False, "result": False})

    @api.model
    def process_pending_jobs(self, limit=10):
        pending_jobs = self.search(
            [("state", "=", "pending")], order="create_date ASC", limit=limit
        )
        pending_jobs.process_job()

    def cleanup_done_jobs(self, days=30):
        cutoff = datetime.utcnow() - timedelta(days=days)
        done_jobs = self.search(
            [
                ("state", "=", "done"),
                ("create_date", "<", cutoff.strftime("%Y-%m-%d %H:%M:%S")),
            ]
        )
        done_jobs.unlink()
