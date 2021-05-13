# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import ast
import logging
import uuid
import datetime
import copy

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib


# TODO: implement these methods in ir.model.data object
def _get_external_id(record):
    # code reference from from odoo BaseModel.__ensure_xml_id()
    # for generating the external_id
    """Create missing external ids for records, and return an
        dict of pairs ``(record, xmlid)`` for the records.

    :rtype: {'record': [Model, str | None]}
    """
    record and record.ensure_one()

    res = record._get_external_ids()
    if res[record.id]:
        return res

    modname = "__sync_process__"
    # create missing xml id
    rec_name = "{}_{}_{}".format(record._table, record.id, uuid.uuid4().hex[:8])
    vals = {
        "module": modname,
        "model": record._name,
        "name": rec_name,
        "res_id": record.id,
    }
    record.env["ir.model.data"].create(vals)
    return record._get_external_ids()


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


class AuditlogLog(models.Model):
    _inherit = "auditlog.log"

    state = fields.Selection(
        [
            # FIXME: Either all stages are low caps or Capitalized
            ("logged", "Logged"),
            ("captured", "Captured"),
            ("Prepared", "Prepared"),
            ("Pushed", "Pushed"),
            ("Pulled", "Pulled"),
            ("Processed", "Processed"),
            ("Error", "Error"),
            ("Failed", "Failed"),
            ("Cancelled", "Cancelled"),
        ],
        string="State",
        default="logged",
    )
    log_type = fields.Selection(selection_add=[("no_log", "No Log (Sync)")])
    model_name = fields.Char("Model Name")
    uuid = fields.Char("UUID", default=lambda self: uuid.uuid4())
    timestamp = fields.Char("Timestamp", default=lambda self: fields.Datetime.now())
    resource_ids = fields.Char("Resource IDs")
    raw_args_kwargs = fields.Char("Raw Args and kwargs")
    prepared_args_kwargs = fields.Char("Prepared Args and kwargs")
    context = fields.Char("Context")
    external_id = fields.Char("External ID")
    parent_uuid = fields.Char("Parent UUID")
    result = fields.Text("Result")
    remote = fields.Char("Remote")
    _sql_constraints = [
        (
            "uuid_uniq",
            "unique(uuid)",
            (
                "This UUID already exists\n"
                "Record will be skipped to avoid duplication"
            ),
        )
    ]

    def _prepare_args_kwargs(self, args, relational_model):
        # prepare args kwargs and with IDs replaed with ref(<XMLId>)
        ir_model_obj = self.env["ir.model"]
        if not args and not relational_model:
            return {}
        if isinstance(args, str):
            args = eval(args) and eval(args)[0]
        if not isinstance(args, dict):
            return {}
        model_rule = self.env["auditlog.rule"].search([("model_id", "=", self.model_id.id)])
        args_temp = copy.deepcopy(args)
        for k, v in args_temp.items():
            if model_rule.white_list_fields:
                white_list_field = model_rule.white_list_fields.filtered(
                    lambda l: l.name == k
                )
                if not white_list_field:
                    args.pop(k)
                    continue
            elif model_rule.white_list_fields:
                black_list_field = model_rule.black_list_fields.filtered(
                    lambda l: l.name == k
                )
                if black_list_field:
                    args.pop(k)
                    continue
        for k, v in args.items():
            if not v:
                continue
            res_model = ir_model_obj.search([("model", "=", relational_model)], limit=1)
            field = res_model.field_id.filtered(
                lambda l: l.name == k
                and l.ttype in ("many2one", "one2many", "many2many")
            )
            if not field:
                continue
            if field.ttype == "many2one":
                relation_model = field.relation
                rec = self.env[relation_model].browse(v)
                res = _get_external_id(rec)
                xml_id = res[rec.id] and res[rec.id][0] or False
                if not xml_id:
                    continue
                env_ref = "self.env.ref('" + xml_id + "')"
                args.update({k: env_ref})
            elif field.ttype == "one2many":
                for line in v:
                    self._prepare_args_kwargs(line[2], field.relation)
            elif field.ttype == "many2many":
                for line in v:
                    relation_model = field.relation
                    recs = self.env[relation_model].browse(line[2])
                    m2m_list = []
                    for rec in recs:
                        res = _get_external_id(rec)
                        xml_id = res[rec.id] and res[rec.id][0] or False
                        if not xml_id:
                            continue
                        env_ref = "self.env.ref('" + xml_id + "')"
                        m2m_list.append(env_ref)
                    args.update({k: [(6, 0, m2m_list)]})
        return args

    def _cron_prepare_auditlog_events(self):
        logs = self.search([("state", "=", "captured")])
        logs.prepare_auditlog_events()

    def prepare_auditlog_events(self):
        logs = self.filtered(lambda x: x.state in ["captured", "Pulled"])
        for log in logs:
            # ToDo - prepared_args_kwargs and external_id
            if not log.model_id and log.res_id:
                continue
            rec = self.env[log.model_id.model].browse(log.res_id)
            # define the global method
            if log.external_id:
                ext_id = log.external_id
                modname, rec_name = ext_id.split(".", 1)
                ext_id_vals = {
                    "module": modname,
                    "model": log.model_name,
                    "name": rec_name,
                    "res_id": log.res_id,
                }
                ext_id_exists = self.env["ir.model.data"].search(
                    [("model", "=", log.model_name), ("res_id", "=", log.res_id)]
                )
                if not ext_id_exists:
                    self.env["ir.model.data"].create(ext_id_vals)
            res = _get_external_id(rec)
            xml_id = res[rec.id] and res[rec.id][0] or False
            args = log._prepare_args_kwargs(log.raw_args_kwargs, log.model_id.model)
            log.update(
                {
                    "external_id": xml_id,
                    "prepared_args_kwargs": args,
                    "state": "Prepared",
                }
            )

    def _push_event_data(self, addr, uid, password, dbname):

        log_dict = {
            "name": self.name,
            "model_name": self.model_name,
            "method": self.method,
            "uuid": self.uuid,
            "user_id": uid,
            "res_id": self.res_id,
            "log_type": self.log_type,
            "state": "Pulled",
            "timestamp": self.timestamp,
            "resource_ids": self.resource_ids,
            "prepared_args_kwargs": self.prepared_args_kwargs,
            "context": self.context,
            "external_id": self.external_id,
            "parent_uuid": self.parent_uuid,
            "remote": self.remote,
        }
        try:
            xmlrpclib.ServerProxy("%s/xmlrpc/object" % (addr)).execute(
                dbname, uid, password, "auditlog.log", "create", log_dict
            )
            self.state = "Pushed"
        except Exception as e:
            self.state = "Cancelled"
            self.result = e

    @staticmethod
    def _pull_event_data(self, addr, uid, password, dbname):
        try:
            events = xmlrpclib.ServerProxy("%s/xmlrpc/object" % (addr)).execute(
                dbname,
                uid,
                password,
                "auditlog.log",
                "search_read",
                [("state", "in", ["Prepared", "Processed"]), ("user_id", "!=", uid)],
            )
        except Exception:
            raise ValidationError(
                _("Could not retrieve events to Pull from remote server")
            )
        for event in events:
            model_id = self.env["ir.model"].search(
                [("name", "=", event["model_id"][1])], limit=1
            )
            uuid = self.env["auditlog.log"].search(
                [("uuid", "=", event["uuid"])], limit=1
            )
            if model_id and not uuid:
                log_dict = {
                    "name": event["name"],
                    "model_id": model_id.id,
                    "method": event["method"],
                    "uuid": event["uuid"],
                    "res_id": event["res_id"],
                    "log_type": event["log_type"],
                    "state": "Pulled",
                    "timestamp": event["timestamp"],
                    "resource_ids": event["resource_ids"],
                    "prepared_args_kwargs": event["prepared_args_kwargs"],
                    "context": event["context"],
                    "external_id": event["external_id"],
                    "parent_uuid": event["parent_uuid"],
                    "remote": event["remote"],
                }
                try:
                    self.create(log_dict)
                    # commit the record before moving to next one
                    # self.env.cr.commit()
                except Exception:
                    continue
        return

    def _cron_push_pull_event_data(self):

        server = self.env["auditlog.remote.server"].search([], limit=1)
        if server:
            addr = server.url
            userid = server.user
            password = server.password
            dbname = server.dbname
            try:
                xmlrpclib.ServerProxy("%s/xmlrpc/common" % (addr))
            except Exception:
                raise ValidationError(_("Could not connect to the remote server"))
            try:
                uid = xmlrpclib.ServerProxy("%s/xmlrpc/common" % (addr)).authenticate(
                    dbname, userid, password, {}
                )
            except Exception:
                raise ValidationError(
                    _("Could not authenticate user on the remote server")
                )
            if uid:
                # Push event data that is in prepared state
                events = self.search([("state", "=", "Prepared")])
                for event in events:
                    event._push_event_data(addr, uid, password, dbname)

                # Pull event data from remote server
                # that is in Prepared or Processed state
                self._pull_event_data(self, addr, uid, password, dbname)
        return

    def _fetch_master_data(self, model_name):
        server = self.env["auditlog.remote.server"].search([], limit=1)
        if server:
            addr = server.url
            userid = server.user
            password = server.password
            dbname = server.dbname
        try:
            uid = xmlrpclib.ServerProxy("%s/xmlrpc/common" % (addr)).authenticate(
                dbname, userid, password, {}
            )
        except Exception:
            raise ValidationError(_("Could not authenticate user on the remote server"))

        comodel = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
        export_fields_names = []
        for ir_field in comodel.field_id:  # .filtered(lambda l: l.name not in ('id')):
            if ir_field.ttype in ("many2one", "many2many", "one2many"):
                field_name = "/".join((ir_field.name, "id"))
                export_fields_names.append(field_name)
                continue
            export_fields_names.append(ir_field.name)
        master_datas_list = []
        master_datas = False
        try:
            master_datas_list = xmlrpclib.ServerProxy(
                "%s/xmlrpc/object" % (addr)
            ).execute(dbname, uid, password, model_name, "search", [])
        except Exception:
            raise ValidationError(_("Could not retrieve master from remote server"))
        try:
            master_datas = xmlrpclib.ServerProxy("%s/xmlrpc/object" % (addr)).execute(
                dbname,
                uid,
                password,
                model_name,
                "export_data",
                master_datas_list,
                export_fields_names,
            )
        except Exception:
            raise ValidationError(_("Could not export master from remote server"))
        return export_fields_names, master_datas

    def _cron_initialize_master_data(self):
        """Connect to remote server, and fetch all datas of the selected
        Audit Rule of type master data
        """

        log_rules = self.env["auditlog.rule"].search(
            [("sync_type", "=", "master"), ("state", "=", "subscribed")]
        )
        server = self.env["auditlog.remote.server"].search([], limit=1)
        if log_rules and server:
            addr = server.url
            userid = server.user
            password = server.password
            dbname = server.dbname
            try:
                xmlrpclib.ServerProxy("%s/xmlrpc/common" % (addr))
            except Exception:
                raise ValidationError(_("Could not connect to the remote server"))
            try:
                uid = xmlrpclib.ServerProxy("%s/xmlrpc/common" % (addr)).authenticate(
                    dbname, userid, password, {}
                )
            except Exception:
                raise ValidationError(
                    _("Could not authenticate user on the remote server")
                )
            if uid:
                for log_rule in log_rules:
                    model_name = log_rule.model_id.model
                    mapping_fields_names, master_datas = self._fetch_master_data(
                        model_name
                    )
                    master_data_list = []
                    for data in master_datas.get("datas"):
                        for i in range(len(data)):
                            if isinstance(data[i], bool):
                                data[i] = str(data[i])
                        master_data_list.append(data)
                    # load the export data.
                    self.env[model_name].load(mapping_fields_names, master_data_list)
        return True

    @staticmethod
    def _populate_model_id(self, model_name):
        model_id = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
        return model_id.id

    @staticmethod
    def _populate_model(self, model_id):
        model = self.env["ir.model"].search([("id", "=", model_id)], limit=1)
        model_name = model.model
        return model_name

    @api.model
    def create(self, vals):
        if vals.get("model_name") and not vals.get("model_id"):
            model = vals.get("model_name")
            vals["model_id"] = self._populate_model_id(self, model)
        if vals.get("model_id") and not vals.get("model_name"):
            model_id = vals.get("model_id")
            vals["model_name"] = self._populate_model(self, model_id)
        return super(AuditlogLog, self).create(vals)

    def write(self, vals):
        if vals.get("model") and not vals.get("model_id"):
            model = vals.get("model")
            vals["model_id"] = self._populate_model_id(self, model)
        if vals.get("model_id") and not vals.get("model"):
            model_id = vals.get("model_id")
            vals["model_name"] = self._populate_model(self, model_id)
        return super(AuditlogLog, self).write(vals)

    @staticmethod
    def _prepare_args_kwargs_to_apply(self, args_kwargs, relation_model):
        # Convert external IDs to db Ids from local system
        ir_model_obj = self.env["ir.model"]
        res_model = ir_model_obj.search([("model", "=", relation_model)], limit=1)

        if not isinstance(args_kwargs, dict):
            return args_kwargs
        for key, val in args_kwargs.items():
            if not val:
                continue
            field = res_model.field_id.filtered(
                lambda l: l.name == key
                and l.ttype in ("many2one", "one2many", "many2many")
            )
            if not field:
                continue
            if field.ttype == "many2one":
                args_kwargs.update({key: eval(val).id})
            elif field.ttype == "one2many":
                for line in val:
                    self._prepare_args_kwargs_to_apply(self, line[2], field.relation)
            elif field.ttype == "many2many":
                m2m_list = []
                for lines in val:
                    m2m_ids = []
                    for line in lines[2]:
                        m2m_ids.append(eval(line).id)
                    m2m_list.append((6, 0, m2m_ids))
                args_kwargs.update({key: m2m_list})
        return args_kwargs

    def _cron_apply_event_data(self):
        events = self.search(
            [("state", "=", "Pulled"), ("parent_uuid", "=", False)], order="timestamp"
        )
        events.apply_event_data()

    def apply_event_data(self):
        # TODO: support case where event applies to a list of IDs
        events = self.filtered_domain(
            [("state", "=", "Pulled"), ("parent_uuid", "=", False)]
        )
        for event in events:
            if not event.parent_uuid:
                self = self.with_context(sync_apply_parent=event.uuid)
            pulled_args_kwargs = eval(event.prepared_args_kwargs)
            args_kwargs = self._prepare_args_kwargs_to_apply(
                event, pulled_args_kwargs, event.model_id.model
            )
            event_user = event.user_id.active and event.user_id or SUPERUSER_ID
            target_record = None
            try:
                target_record = self.env.ref(event.external_id)
            except Exception:
                pass
            if event.method == "create":
                if target_record:
                    _logger.warn("Can't create, %s already exists", event.external_id)
                    event.state = "Cancelled"
                else:
                    try:
                        new_record = (
                            self.env[event.model_name]
                            .with_user(event_user)
                            .create(args_kwargs)
                        )
                        event.state = "Processed"
                        _set_external_id(
                            event.model_name, new_record, event.external_id
                        )
                    except Exception as e:
                        event.result = str(e)
                        event.state = "Failed" if event.state == "Error" else "Error"
            elif target_record:
                method = getattr(target_record.with_user(event_user), event.method)
                try:
                    method(args_kwargs)
                    event.state = "Processed"
                except Exception as e:
                    event.result = str(e)
                    event.state = "Failed" if event.state == "Error" else "Error"
            else:
                _logger.warn(
                    "Can't apply %s on %d, record %s does not exist",
                    event.method,
                    event.id,
                    event.external_id,
                )
                event.state = "Error"
                event.result = "Record does not exist"
            # TODO self.env.cr.commit()
        return

    def reprocess_error_events(self):
        events = self.filtered(lambda event: event.state == "Error")
        events.apply_event_data()
