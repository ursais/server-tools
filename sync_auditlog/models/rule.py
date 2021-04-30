# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import copy
import logging
import uuid
from datetime import datetime

from odoo import api, fields, models

# from odoo.addons.auditlog.models.rule import FIELDS_BLACKLIST

_logger = logging.getLogger(__name__)


class AuditlogRule(models.Model):
    _inherit = "auditlog.rule"

    log_type = fields.Selection(selection_add=[("no_log", "No Log (Sync)")])

    sync_type = fields.Selection(
        [("transaction", "Transaction"), ("master", "Master Data")],
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
            for method in methods:
                check_attr = "sync_auditlog_ruled_" + method
                if not hasattr(model, check_attr) and hasattr(model, method):
                    model._patch_method(method, rule._make_sync(method))
                    setattr(type(model), check_attr, True)
                    _logger.debug("Watching %s.%s", model, method)
        return res

    def _make_sync(self, method):
        """Log a sync record for a watched method."""
        self.ensure_one()
        log_type = self.log_type

        def synced_call(self, *args, **kwargs):
            result = synced_call.origin(self, *args, **kwargs)
            self = self.with_context(auditlog_disabled=True)
            skip_sync = False
            context = dict(self._context)
            if self.env.context.get("auditlog_is_capturing"):
                skip_sync = True
            else:
                self.env.context = dict(self.env.context)
                self.env.context.update({"auditlog_is_capturing": True})
            rule_model = self.env["auditlog.rule"]
            if log_type != "no_log":
                additional_log_values = {
                    "log_type": log_type,
                    "uuid": uuid.uuid4(),
                    "timestamp": datetime.now(),
                }
                rule_model.sudo().create_extra_logs(
                    self.env.uid, self._name, self.ids, method, additional_log_values,
                )
            if not skip_sync:
                additional_log_values = {
                    "log_type": "no_log",
                    "uuid": uuid.uuid4(),
                    "timestamp": datetime.now(),
                    "resource_ids": self.ids,
                    "raw_args_kwargs": args,
                    "context": context,
                    "state": "captured",
                }
                rule_model.sudo().create_extra_logs(
                    self.env.uid, self._name, self.ids, method, additional_log_values,
                )
            return result

        return synced_call

    def create_extra_logs(
        self, uid, res_model, res_ids, method, additional_log_values=None,
    ):
        """Create logs. `old_values` and `new_values` are dictionaries, e.g:
        {RES_ID: {'FIELD': VALUE, ...}}
        """
        log_model = self.env["auditlog.log"]
        http_request_model = self.env["auditlog.http.request"]
        http_session_model = self.env["auditlog.http.session"]
        for res_id in res_ids:
            model_model = self.env[res_model]
            name = model_model.browse(res_id).name_get()
            res_name = name and name[0] and name[0][1]
            vals = {
                "name": res_name,
                "model_id": self.pool._auditlog_model_cache[res_model],
                "res_id": res_id,
                "method": method,
                "user_id": uid,
                "http_request_id": http_request_model.current_http_request(),
                "http_session_id": http_session_model.current_http_session(),
            }
            vals.update(additional_log_values or {})
            log_model.create(vals)

    def _make_create(self):
        """Instanciate a create method that log its calls."""
        self.ensure_one()
        log_type = self.log_type
        black_list_fields = [field.name for field in self.black_list_fields]
        white_list_fields = [field.name for field in self.white_list_fields]

        @api.model_create_multi
        @api.returns("self", lambda value: value.id)
        def create_full(self, vals_list, **kwargs):
            self = self.with_context(auditlog_disabled=True)
            rule_model = self.env["auditlog.rule"]
            new_records = create_full.origin(self, vals_list, **kwargs)
            # Take a snapshot of record values from the cache instead of using
            # 'read()'. It avoids issues with related/computed fields which
            # stored in the database only at the end of the transaction, but
            # their values exist in cache.
            new_values = {}
            fields_list = rule_model.get_auditlog_fields(self)
            for new_record in new_records.sudo():
                new_values.setdefault(new_record.id, {})
                for fname, field in new_record._fields.items():
                    if fname not in fields_list:
                        continue
                    new_values[new_record.id][fname] = field.convert_to_read(
                        new_record[fname], new_record
                    )
            additional_log_values = {
                "log_type": log_type,
                "uuid": uuid.uuid4(),
                "timestamp": datetime.now(),
            }

            rule_model.sudo().with_context(
                black_list_fields=black_list_fields, white_list_fields=white_list_fields
            ).create_logs(
                self.env.uid,
                self._name,
                new_records.ids,
                "create",
                None,
                new_values,
                additional_log_values,
            )
            context = dict(self._context)
            if self.env.context.get("auditlog_is_capturing"):
                context.update({"sync_ext_id": True})
            else:
                self.env.context = dict(self.env.context)
                self.env.context.update({"auditlog_is_capturing": True})
            additional_log_values = {
                "log_type": "no_log",
                "uuid": uuid.uuid4(),
                "timestamp": datetime.now(),
                "resource_ids": self.ids,
                "raw_args_kwargs": vals_list,
                "context": context,
                "state": "captured",
            }
            rule_model.sudo().with_context(
                black_list_fields=black_list_fields, white_list_fields=white_list_fields
            ).create_logs(
                self.env.uid,
                self._name,
                new_records.ids,
                "create",
                None,
                None,
                additional_log_values,
            )
            return new_records

        @api.model_create_multi
        @api.returns("self", lambda value: value.id)
        def create_fast(self, vals_list, **kwargs):
            self = self.with_context(auditlog_disabled=True)
            rule_model = self.env["auditlog.rule"]
            vals_list2 = copy.deepcopy(vals_list)
            new_records = create_fast.origin(self, vals_list, **kwargs)
            new_values = {}
            for vals, new_record in zip(vals_list2, new_records):
                new_values.setdefault(new_record.id, vals)
            context = dict(self._context)
            if self.env.context.get("auditlog_is_capturing"):
                context.update({"sync_ext_id": True})
            else:
                self.env.context = dict(self.env.context)
                self.env.context.update({"auditlog_is_capturing": True})
            if log_type == "fast":
                additional_log_values = {
                    "log_type": log_type,
                    "uuid": uuid.uuid4(),
                    "timestamp": datetime.now(),
                }

                rule_model.sudo().with_context(
                    black_list_fields=black_list_fields,
                    white_list_fields=white_list_fields,
                ).create_logs(
                    self.env.uid,
                    self._name,
                    new_records.ids,
                    "create",
                    None,
                    new_values,
                    additional_log_values,
                )
            additional_log_values = {
                "log_type": "no_log",
                "uuid": uuid.uuid4(),
                "timestamp": datetime.now(),
                "resource_ids": self.ids,
                "raw_args_kwargs": vals_list,
                "context": context,
                "state": "captured",
            }

            rule_model.sudo().with_context(
                black_list_fields=black_list_fields, white_list_fields=white_list_fields
            ).create_logs(
                self.env.uid,
                self._name,
                new_records.ids,
                "create",
                None,
                None,
                additional_log_values,
            )
            return new_records

        return create_full if self.log_type == "full" else create_fast

    def _make_write(self):
        """Instanciate a write method that log its calls."""
        self.ensure_one()
        log_type = self.log_type
        black_list_fields = [field.name for field in self.black_list_fields]
        white_list_fields = [field.name for field in self.white_list_fields]

        def write_fast(self, vals, **kwargs):
            self = self.with_context(auditlog_disabled=True)
            rule_model = self.env["auditlog.rule"]
            # Log the user input only, no matter if the `vals` is updated
            # afterwards as it could not represent the real state
            # of the data in the database
            vals2 = dict(vals)
            old_vals2 = dict.fromkeys(list(vals2.keys()), False)
            old_values = {id_: old_vals2 for id_ in self.ids}
            new_values = {id_: vals2 for id_ in self.ids}
            result = write_fast.origin(self, vals, **kwargs)
            skip_sync = False
            context = dict(self._context)
            if self.env.context.get("auditlog_is_capturing"):
                skip_sync = True
            else:
                self.env.context = dict(self.env.context)
                self.env.context.update({"auditlog_is_capturing": True})
            if log_type == "fast":
                additional_log_values = {
                    "log_type": log_type,
                    "uuid": uuid.uuid4(),
                    "timestamp": datetime.now(),
                }

                rule_model.sudo().with_context(
                    black_list_fields=black_list_fields,
                    white_list_fields=white_list_fields,
                ).create_logs(
                    self.env.uid,
                    self._name,
                    self.ids,
                    "write",
                    old_values,
                    new_values,
                    additional_log_values,
                )
            if not skip_sync:
                additional_log_values = {
                    "log_type": "no_log",
                    "uuid": uuid.uuid4(),
                    "timestamp": datetime.now(),
                    "resource_ids": self.ids,
                    "raw_args_kwargs": vals,
                    "context": context,
                    "state": "captured",
                }

                rule_model.sudo().with_context(
                    black_list_fields=black_list_fields,
                    white_list_fields=white_list_fields,
                ).create_logs(
                    self.env.uid,
                    self._name,
                    self.ids,
                    "write",
                    None,
                    None,
                    additional_log_values,
                )
            return result

        return write_fast


class AuditlogRuleMethodCalls(models.Model):
    _name = "auditlog.rule.method.calls"
    _description = "Method Calls Log"

    name = fields.Char("Method Name")
    arguments = fields.Char("Arguments")
    auditlog_rule_id = fields.Many2one("auditlog.rule", string="Auditlog Rule")
