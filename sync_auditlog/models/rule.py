# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import uuid
from datetime import datetime

from odoo import api, fields, models

# from odoo.addons.auditlog.models.rule import FIELDS_BLACKLIST

_logger = logging.getLogger(__name__)


def _set_external_id(model_name, record, xmlid):
    """
    Create an External ID.
    If it already exists, update to ensure it is pointing to this record.
    """
    ModelData = record.env["ir.model.data"]
    res_id = ModelData.xmlid_to_res_id(xmlid)
    if not res_id:
        module, name = xmlid.split(".", 1)
        ModelData.create(
            {"model": model_name, "res_id": record, "module": module, "name": name}
        )
    elif res_id != record.id:
        data_id = ModelData.xmlid_lookup(xmlid)[0]
        data = ModelData.browse(data_id)
        data.res_id = record.id


class AuditlogRule(models.Model):
    _inherit = "auditlog.rule"

    log_type = fields.Selection(selection_add=[("no_log", "No Log (Sync)")])

    sync_type = fields.Selection(
        [("transaction", "Transaction"), ("master", "Master Data")]
    )
    domain_filter = fields.Char()
    black_list_fields = fields.Many2many(
        "ir.model.fields",
        "auditlog_blacklist_fields_rel",
        "auditlog_id",
        "field_id",
        string="Column black list",
        domain="[('model_id','=',model_id)]",
    )
    white_list_fields = fields.Many2many(
        "ir.model.fields",
        "auditlog_whitelist_fields_rel",
        "auditlog_id",
        "field_id",
        string="Column white list",
        domain="[('model_id','=',model_id)]",
    )

    method_call_ids = fields.One2many(
        "auditlog.rule.method.calls", "auditlog_rule_id", string="Log Method Calls"
    )

    def _patch_methods(self):
        """Patch ORM methods of models defined in rules to log their calls."""
        res = super(AuditlogRule, self)._patch_methods()
        for rule in self.filtered("sync_type"):
            model = self.env[rule.model_id.model]
            methods = rule.method_call_ids.mapped("name")
            if rule.log_create:
                methods.append("create")
            if rule.log_write:
                methods.append("write")
            if rule.log_unlink:
                methods.append("unlink")
            for method_name in methods:
                check_attr = "sync_auditlog_ruled_" + method_name
                if not hasattr(model, check_attr) and hasattr(model, method_name):
                    patched_method = (
                        rule._make_sync_create()
                        if method_name == "create"
                        else rule._make_sync_call(method_name)
                    )
                    model._patch_method(method_name, patched_method)
                    setattr(type(model), check_attr, True)
                    _logger.debug("Watching %s.%s", model, method_name)
        return res

    def _make_sync_create(self):
        """
        Log a sync record for an @api.model create call.
        A top level create call will store a regular sync log record.
        A subsequent create call will store a simplified sync log record,
        only with the record ID.
        """
        self.ensure_one()
        sync_type = self.sync_type

        @api.model_create_multi
        @api.returns("self", lambda value: value.id)
        def logged_create_call(self, vals_list, **kwargs):
            if sync_type:
                doing_sync = self.env.context.get("sync_auditlog_working")
                update_ext_id = self.env.context.get("sync_apply_parent")
                uuid_num = uuid.uuid4()
                additional_log_values = {
                    "log_type": "no_log",
                    "uuid": uuid_num,
                    "timestamp": datetime.now(),
                    "resource_ids": self.ids,
                    "state": "captured",
                    "parent_uuid": doing_sync,
                }
                if not doing_sync:
                    # Top create call stores a regular sync record
                    additional_log_values.update(
                        {
                            "raw_args_kwargs": vals_list,  # FIXME missing store kwargs
                            "context": self.env.context,
                        }
                    )
                    self = self.with_context(sync_auditlog_working=uuid_num)
                elif update_ext_id:

                    child_logs = self.env["auditlog.log"].search(
                        [
                            ("parent_uuid", "=", update_ext_id),
                            ("state", "in", ("Pulled", "Processed")),
                            ("model_name", "=", self._name),
                        ],
                        order="timestamp, model_id, res_id",
                    )
                    if child_logs:
                        child_count = self.env.context.get("sync_child_count")

                new_records = logged_create_call.origin(self, vals_list, **kwargs)
                # Hotfix: Pass correct UUID to First record to identify Child Logs
                new_uuid = False
                is_client = self.env.context.get("is_client")
                for new_record in new_records:
                    if new_uuid:
                        additional_log_values.update({"uuid": uuid.uuid4()})
                    else:
                        new_uuid = True
                    if update_ext_id and doing_sync:
                        # ToDo clean up logic for assigning ext ids to child records
                        if child_logs:
                            if child_count:
                                child_count += 1
                            else:
                                child_count = 1
                            child_log = child_logs[child_count - 1]
                            additional_log_values.update(
                                {"external_id": child_log.external_id}
                            )
                            external_id = child_log.external_id
                            child_log.state = "Processed"
                            _set_external_id(self._name, new_record, external_id)
                    # Note that the Log is created after the call is done
                    # (and depending calls are processed)
                    if not is_client:
                        self.env["auditlog.rule"].sudo().create_logs(
                            self.env.uid,
                            self._name,
                            new_record.ids,
                            "create",
                            additional_log_values=additional_log_values,
                        )
                if update_ext_id and doing_sync:
                    if child_logs:
                        if child_count >= len(child_logs):
                            child_count = 0
                        self = self.with_context(sync_child_count=child_count)
            else:
                new_records = logged_create_call.origin(self, vals_list, **kwargs)
            return new_records

        return logged_create_call

    def _make_sync_call(self, method):
        """
        Log a sync record for a watched method.
        Only @api.multi methods are supported.
        """
        self.ensure_one()
        sync_type = self.sync_type

        def logged_method_call(self, *args, **kwargs):
            doing_sync = self.env.context.get("sync_auditlog_working")
            is_client = self.env.context.get("is_client")
            if sync_type and not doing_sync:
                uuid_num = uuid.uuid4()
                self = self.with_context(sync_auditlog_working=uuid_num)
                additional_log_values = {
                    "log_type": "no_log",
                    "uuid": uuid_num,
                    "timestamp": datetime.now(),
                    "resource_ids": self.ids,
                    "raw_args_kwargs": args,  # FIXME: missing storing kwargs
                    "context": self.env.context,
                    "state": "captured",
                }
                if not is_client:
                    self.env["auditlog.rule"].sudo().create_logs(
                        self.env.uid,
                        self._name,
                        self.ids,
                        method,
                        additional_log_values=additional_log_values,
                    )
            result = logged_method_call.origin(self, *args, **kwargs)
            return result

        return logged_method_call


class AuditlogRuleMethodCalls(models.Model):
    _name = "auditlog.rule.method.calls"
    _description = "Method Calls Log"

    name = fields.Char("Method Name")
    arguments = fields.Char("Arguments")
    auditlog_rule_id = fields.Many2one("auditlog.rule", string="Auditlog Rule")
