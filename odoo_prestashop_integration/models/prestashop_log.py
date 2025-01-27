from odoo import models, fields, api
import pprint


class ProcessDetail(models.Model):
    _name = 'prestashop.log'
    _inherit = ['mail.thread']
    _description = 'Process Detail'
    _order = 'id DESC'

    name = fields.Char(string='Name')
    prestashop_operation_name = fields.Selection(selection=[('gateway', 'Gateway'),
                                                         ('product', 'Product'),
                                                         ('customer', 'Customer'),
                                                         ('location', 'location'),
                                                         ('product_attribute', 'Product Attribute'),
                                                         ('product_variant', 'Product Variant'),
                                                         ('order', 'Order'),
                                                         ('inventory', 'Inventory'),
                                                         ('order_status', 'Order Status'),
                                                            ('product_category','Product Category')],
                                              string="Process Name")
    prestashop_operation_type = fields.Selection(selection=[('export', 'Export'),
                                                         ('import', 'Import'),
                                                         ('update', 'Update'),
                                                         ('delete', 'Cancel / Delete')], string="Process Type")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)
    instance_id = fields.Many2one('prestashop.instance.integration', string='Instance',
                                  help='Select Instance Id')
    prestashop_operation_line_ids = fields.One2many("prestashop.log.line", "prestashop_operation_id",
                                                 string="Operation")
    prestashop_operation_message = fields.Char(string="Message")
    create_date = fields.Datetime(string='Created on')

    @api.model_create_multi
    def create(self, vals_list):
        """
        In this method auto generated sequence added in log name.
        """
        for vals in vals_list:
            sequence = self.env.ref("odoo_prestashop_integration.seq_prestashop_log")
            name = sequence and sequence.next_by_id() or '/'
            company_id = self._context.get('company_id', self.env.user.company_id.id)
            if type(vals) == dict:
                vals.update({'name': name, 'company_id': company_id})
        return super(ProcessDetail, self).create(vals_list)

    def unlink(self):
        """
        This method is used for unlink appropriate log and logline both from both log model
        """
        for selected_main_log in self:
            if selected_main_log.prestashop_operation_line_ids:
                selected_main_log.prestashop_operation_line_ids.unlink()
        return super(ProcessDetail, self).unlink()

    def generate_prestashop_logs(self, prestashop_operation_name, prestashop_operation_type, instance,
                              prestashop_operation_message):
        """
        From this method prestashop log's record will create.
        """
        log_id = self.create({
            'prestashop_operation_name': prestashop_operation_name,
            'prestashop_operation_type': prestashop_operation_type,
            'instance_id': instance.id,
            'prestashop_operation_message': prestashop_operation_message
        })
        return log_id


class ProcessDetailsLine(models.Model):
    _name = 'prestashop.log.line'
    _rec_name = 'prestashop_operation_id'
    _description = 'Process Details Line'

    _order = 'id DESC'

    prestashop_operation_id = fields.Many2one('prestashop.log', string='Process')
    prestashop_operation_name = fields.Selection(selection=[('gateway', 'Gateway'),
                                                         ('product', 'Product'),
                                                         ('location', 'location'),
                                                         ('customer', 'Customer'),
                                                         ('product_attribute', 'Product Attribute'),
                                                         ('product_variant', 'Product Variant'),
                                                         ('order', 'Order'),
                                                         ('inventory', 'Inventory'),
                                                         ('product_category', 'Product Category')],
                                              string="Process Name")
    prestashop_operation_type = fields.Selection([('export', 'Export'),
                                               ('import', 'Import'),
                                               ('update', 'Update'),
                                               ('delete', 'Cancel / Delete')], string="Process Type")
    company_id = fields.Many2one("res.company", "Company", default=lambda self: self.env.user.company_id)
    instance_id = fields.Many2one('prestashop.instance.integration', string='Instance',
                                  help='Select Instance Id')
    process_request_message = fields.Char("Request Message")
    process_response_message = fields.Text("Response Message")
    fault_operation = fields.Boolean("Fault Process", default=False)
    prestashop_operation_message = fields.Char("Message")
    create_date = fields.Datetime(string='Created on')
    product_queue_line = fields.Many2one('prestashop.product.data.queue.line')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if type(vals) == dict:
                prestashop_operation_id = vals.get('prestashop_operation_id')
                operation = prestashop_operation_id and self.env['prestashop.log'].browse(prestashop_operation_id) or False
                company_id = operation and operation.company_id.id or self.env.user.company_id.id
                vals.update({'company_id': company_id})
        return super(ProcessDetailsLine, self).create(vals_list)

    def generate_prestashop_process_line(self, prestashop_operation_name, prestashop_operation_type, instance,
                                         prestashop_operation_message, process_request_message, process_response_message,
                                      log_id, fault_operation=False):
        """
        From this method prestashop log line's record will create.
        """
        vals = {}
        log_line_id = vals.update({
            'prestashop_operation_name': prestashop_operation_name,
            'prestashop_operation_type': prestashop_operation_type,
            'instance_id': instance.id,
            'prestashop_operation_message': prestashop_operation_message,
            'process_request_message': pprint.pformat(process_request_message) if process_request_message else False,
            'process_response_message': pprint.pformat(process_response_message) if process_response_message else False,
            'prestashop_operation_id': log_id and log_id.id,
            'fault_operation': fault_operation
        })
        if self._context.get('for_variant_line'):
            vals.update({
                'product_queue_line': self._context.get('for_variant_line').id
            })

        self.create(vals)
        return log_line_id
