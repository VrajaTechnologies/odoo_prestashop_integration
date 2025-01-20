from odoo import models, fields, api, tools
from odoo.tools.safe_eval import safe_eval
from datetime import timedelta
import urllib.parse as urlparse
import logging
import pprint
import re

_logger = logging.getLogger("Prestashop Order Queue")


class OrderDataQueue(models.Model):
    _name = "order.data.queue"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Prestashop Order Data Queue"
    _order = 'id DESC'

    @api.depends('prestashop_order_queue_line_ids.state')
    def _compute_queue_line_state_and_count(self):
        """
        Compute method to set queue state automatically based on queue line states.
        """
        for queue in self:
            queue_line_ids = queue.prestashop_order_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(string='Name')
    instance_id = fields.Many2one('prestashop.instance.integration', string='Instance', help='Select Instance Id',
                                  copy=False, tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                              ('completed', 'Completed'), ('failed', 'Failed')], tracking=True,
                             default='draft', compute="_compute_queue_line_state_and_count", store=True)
    order_queue_line_total_record = fields.Integer(string='Total Records',
                                                   help="This Button Shows Number of Total Records")
    order_queue_line_draft_record = fields.Integer(string='Draft Records',
                                                   help="This Button Shows Number of Draft Records")
    order_queue_line_fail_record = fields.Integer(string='Fail Records',
                                                  help="This Button Shows Number of Fail Records")
    order_queue_line_done_record = fields.Integer(string='Done Records',
                                                  help="This Button Shows Number of Done Records")
    order_queue_line_cancel_record = fields.Integer(string='Cancel Records',
                                                    help="This Button Shows Number of Done Records")
    prestashop_order_queue_line_ids = fields.One2many("order.data.queue.line",
                                                   "prestashop_order_queue_id", string="Order Queue")
    prestashop_log_id = fields.Many2one('prestashop.log', string="Logs")

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to add sequence number in new record.
        """
        sequence = self.env.ref("odoo_prestashop_integration.seq_prestashop_order_queue")
        for vals in vals_list:
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super(OrderDataQueue, self).create(vals_list)

    def generate_prestashop_order_queue(self, instance):
        """
        This method is used to create new record of order queue.
        """
        return self.create({'instance_id': instance.id})

    def create_prestashop_order_queue_job(self, instance_id, prestashop_order_list):
        """
        This method used to create a order queue.
        """
        order_id_list = []
        batch_size = 50
        for prestashop_order in tools.split_every(batch_size, prestashop_order_list):
            queue_id = self.generate_prestashop_order_queue(instance_id)
            for order in prestashop_order:
                prestashop_order_dict = order.to_dict()
                self.env['order.data.queue.line'].create_prestashop_order_queue_line(prestashop_order_dict, instance_id, queue_id)
            order_id_list.append(queue_id.id)
        return order_id_list

    def process_prestashop_order_queue(self,instance_id=False):
        """
        This method is used for Create Order from prestashop To Odoo
        From order queue create order in odoo
        """
        instance_id = instance_id if instance_id else self.instance_id
        if self._context.get('from_cron'):
            order_data_queues = self.search([('instance_id', '=', instance_id.id), ('state', '!=', 'completed')],
                                               order="id asc")
        else:
            order_data_queues = self
        for order_queue in order_data_queues:
            to_process_order_queue_line_ids = order_queue.prestashop_order_queue_line_ids.filtered(
                lambda x: x.state in ['draft', 'partially_completed', 'failed'] and x.number_of_fails < 3)

            if not order_queue.prestashop_log_id:
                log_id = self.env['prestashop.log'].generate_prestashop_logs('order', 'import', instance_id, 'Process Started')
            else:
                log_id = order_queue.prestashop_log_id

            order_queue.prestashop_log_id = log_id.id
            for order_line in to_process_order_queue_line_ids:
                try:
                    url = ''.format(order_line.prestashop_order_queue_id)
                    authorization_code = 'Bearer {}'.format()
                    headers = {
                        'Authorization': authorization_code,
                    }
                    payload = {}
                    response_status, response_data = instance_id.api_calling_method("GET", url, payload, headers)
                    if response_status:
                        print('response_status......',response_status)
                        order_line.state='completed'
                    else:
                        log_msg = f"Something went wrong, not getting successful response from Prestashop\n{response_data}."
                        order_line.number_of_fails += 1
                        self.env['Prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance_id, log_msg,
                                                                                         False, log_msg, log_id, True)
                except Exception as error:
                    order_line.state = 'failed'
                    log_msg = '{0} :  {1} - Getting Some Error When Try To Process Order Queue From Prestashop To Odoo'.format(
                        order_line.name,error)
                    self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance_id, log_msg,
                                                                                     False, log_msg, log_id, True)
                    _logger.info(error)
            log_id.prestashop_operation_message = 'Process Has Been Finished'
            if not log_id.prestashop_operation_line_ids:
                log_id.unlink()


class OrderDataQueueLine(models.Model):
    _name = 'order.data.queue.line'
    _description = "Prestashop Order Data Queue Line"
    _rec_name = 'prestashop_order_queue_id'

    name = fields.Char(string='Name')
    prestashop_order_queue_id = fields.Many2one('order.data.queue', string='Order Data Queue')

    instance_id = fields.Many2one('prestashop.instance.integration', string='Instance', help='Select Instance Id')
    order_data_id = fields.Char(string="Order Data ID", help='This is the Order Id of Prestashop Order')
    state = fields.Selection(
        [('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
         ('completed', 'Completed'), ('failed', 'Failed')], tracking=True,
        default='draft')
    order_data_to_process = fields.Text(string="Order Data")
    number_of_fails = fields.Integer(string="Number of attempts",
                                     help="This field gives information regarding how many time we will try to proceed the order",
                                     copy=False)
    sale_order_id = fields.Many2one('sale.order', string="Sale Order")

    def _valid_field_parameter(self, field, name):
        return name == 'tracking' or super()._valid_field_parameter(field, name)

    def create_prestashop_order_queue_line(self, prestashop_order_dict, instance_id, queue_id):
        """
        From this method queue line will create.
        """
        pass
