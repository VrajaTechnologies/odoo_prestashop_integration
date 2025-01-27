from odoo import models, fields, api, tools
from odoo.tools.safe_eval import safe_eval
from datetime import timedelta
from urllib.parse import quote
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
                prestashop_order_dict = order
                self.env['order.data.queue.line'].create_prestashop_order_queue_line(prestashop_order_dict, instance_id, queue_id)
            order_id_list.append(queue_id.id)
        return order_id_list

    def import_orders_from_prestashop_to_odoo(self, instance, from_date=False, to_date=False, prestashop_order_ids=False):
        """
        - From operation wizard's button & from import order cron this method will call.
        - Remote IDs wise import order process
        - From and to date wise import order process
        """

        last_synced_date = fields.Datetime.now()
        queue_id_list = []
        from_date = from_date or (fields.Datetime.now() - timedelta(days=1))
        to_date = to_date or fields.Datetime.now()

        if prestashop_order_ids:
            prestashop_order_list = self.fetch_orders_from_prestashop_to_odoo(instance,prestashop_order_id=prestashop_order_ids)
        else:
            prestashop_order_list = self.fetch_orders_from_prestashop_to_odoo(instance,from_date=from_date, to_date=to_date)

        if prestashop_order_list:
            queue_id_list = self.create_prestashop_order_queue_job(instance, prestashop_order_list)
            if prestashop_order_ids and queue_id_list:
                self.browse(queue_id_list).process_prestashop_order_queue()
            if queue_id_list:
                instance.last_order_synced_date = last_synced_date
        return queue_id_list

    def fetch_orders_from_prestashop_to_odoo(self, instance, from_date=False, to_date=False, prestashop_order_ids=False):
        prestashop_order_list = []
        formated_from_date = from_date.strftime('%Y-%m-%d %H:%M:%S')
        formated_to_date = to_date.strftime('%Y-%m-%d %H:%M:%S')
        encoded_start_date = quote(formated_from_date, safe=":")
        encoded_end_date = quote(formated_to_date, safe=":")
        order_status_ids = instance.order_status_ids

        # Convert order_status_ids to a comma-separated string
        order_status_filter = ",".join(str(order_status.id) for order_status in order_status_ids)

        if prestashop_order_ids:
            order_ids = list(set(re.findall(re.compile(r"(\d+)"), prestashop_order_ids)))
            for order_id in order_ids:
                api_operation = "http://%s@%s/api/orders/?output_format=JSON&filter[id]=[%s]&display=full" % (
                    instance.prestashop_api_key, instance.prestashop_url, order_id)
                response_status, order_response_data = instance.send_get_request_from_odoo_to_prestashop(
                    api_operation)
                if response_status:
                    order_dicts = order_response_data.get('orders')
                    prestashop_order_list.extend(order_dicts)
                else:
                    _logger.info("Getting Some Error In Fetch The order :: \n {}".format(order_response_data))

        else:
            try:
                api_operation = (
                        "http://%s@%s/api/orders/?output_format=JSON&display=full&date=1"
                        "&filter[date_add]=[%s,%s]&filter[current_state]=[%s]"
                        % (
                            instance.prestashop_api_key,
                            instance.prestashop_url,
                            encoded_start_date,
                            encoded_end_date,
                            order_status_filter,
                        ))
                response_status, order_response_data = instance.send_get_request_from_odoo_to_prestashop(api_operation)
                if response_status and order_response_data:
                    order_dicts = order_response_data.get('orders')
                    prestashop_order_list.extend(order_dicts)
                else:
                    _logger.info("Getting Some Error In Fetch The order :: \n {}".format(order_response_data))


            except Exception as e:
                _logger.info("Getting Some Error In Fetch The product :: \n {}".format(e))
        return prestashop_order_list


    def process_prestashop_order_queue(self, instance_id=False):
        """
        This method is used for process the order queue line from order queue.
        """
        sale_order_object, instance_id = self.env['sale.order'], instance_id if instance_id else self.instance_id
        if self._context.get('from_cron'):
            order_data_queues = self.search([('instance_id', '=', instance_id.id), ('state', '!=', 'completed')],
                                            order="id asc")
        else:
            order_data_queues = self
        for order_data_queue in order_data_queues:
            if order_data_queue.prestashop_log_id:
                log_id = order_data_queue.prestashop_log_id
            else:
                log_id = self.env['prestashop.log'].generate_prestashop_logs('order', 'import', instance_id,
                                                                       'Process Started')
                self._cr.commit()
            if self._context.get('from_cron'):
                order_data_queue_lines = order_data_queue.prestashop_order_queue_line_ids.filtered(
                    lambda x: x.state in ['draft', 'partially_completed'])
            else:
                order_data_queue_lines = order_data_queue.prestashop_order_queue_line_ids.filtered(
                    lambda x: x.state in ['draft', 'partially_completed', 'failed'] and x.number_of_fails < 3)
            for line in order_data_queue_lines:
                try:
                    prestashop_order_dictionary = safe_eval(line.order_data_to_process)
                    order_id, log_msg, fault_or_not, line_state = sale_order_object.process_import_order_from_prestashop(
                        prestashop_order_dictionary,
                        instance_id, log_id, line)

                    if not order_id:
                        line.number_of_fails += 1
                        if not line.sale_order_id:
                            order_id = self.env['sale.order'].search([('name','=',line.name)])
                            line.sale_order_id = order_id and order_id.id
                    else:
                        line.sale_order_id = order_id.id
                    self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance_id, log_msg,
                                                                               False, log_msg, log_id, fault_or_not)
                    line.state = line_state
                except Exception as error:
                    _logger.info(error)
                    self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance_id, error,
                                                                               False, error, log_id, True)

                    if line:
                        line.state = 'failed'
                        line.number_of_fails += 1
            order_data_queue.prestashop_log_id = log_id.id
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
        order_queue_line_id = self.create({
            'order_data_id': prestashop_order_dict.get('id', ''),
            'state': 'draft',
            'name': prestashop_order_dict.get('reference', '').strip(),
            'order_data_to_process': pprint.pformat(prestashop_order_dict),
            'instance_id': instance_id and instance_id.id or False,
            'prestashop_order_queue_id': queue_id and queue_id.id or False,
        })
        return order_queue_line_id
