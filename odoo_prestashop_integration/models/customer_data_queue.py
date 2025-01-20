import logging
import pprint
from odoo import models, api, fields, tools
from datetime import timedelta

_logger = logging.getLogger("Customer Queue Line")


class CustomerDataQueue(models.Model):
    _name = 'customer.data.queue'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Prestashop Customer Data'
    _order = 'id DESC'

    @api.depends('customer_queue_line_ids.state')
    def _compute_customer_queue_line_state_and_count(self):
        for queue in self:
            queue_line_ids = queue.customer_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(size=120, readonly=True, )
    instance_id = fields.Many2one("prestashop.instance.integration", string="Instance")
    state = fields.Selection([("draft", "Draft"), ("partially_completed", "Partially Completed"),
                              ("completed", "Completed"), ("failed", "Failed")],
                             default="draft", store=True, compute="_compute_customer_queue_line_state_and_count")
    customer_queue_line_ids = fields.One2many("customer.data.queue.line",
                                              "customer_queue_id", "Customers")
    queue_process_count = fields.Integer(help="It is used for know, how many time queue is processed.")
    prestashop_log_id = fields.Many2one('prestashop.log', string="Logs")

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to add sequence number in new record.
        """
        sequence = self.env.ref("odoo_prestashop_integration.seq_prestashop_customer_queue")
        for vals in vals_list:
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super(CustomerDataQueue, self).create(vals_list)

    def generate_prestashop_customer_queue(self, instance):
        return self.create({'instance_id': instance.id})

    def create_prestashop_customer_queue_job(self, instance_id, prestashop_customer_list):
        """
        This method used to create a customer queue.
        """
        res_id_list = []
        batch_size = 50
        for prestashop_customer in tools.split_every(batch_size, prestashop_customer_list):
            queue_id = self.generate_prestashop_customer_queue(instance_id)
            for customer in prestashop_customer:
                prestashop_customer_dict = customer
                self.env['customer.data.queue.line'].create_prestashop_customer_queue_line(prestashop_customer_dict,
                                                                                        instance_id, queue_id)
            res_id_list.append(queue_id.id)
        return res_id_list

    def fetch_countries_from_prestashop_to_odoo(self, instance, country_id):
        """
        This method used to fetch a prestashop Countries
        """
        log_id = self.env['prestashop.log'].generate_prestashop_logs('customer', 'import', instance, 'Process Started')
        self._cr.commit()
        prestashop_country_list = []
        try:
            if country_id:
                api_operation = "http://%s@%s/api/countries/?output_format=JSON&resource=countries&filter[id]=[%s]&display=full" % (
                    instance and instance.prestashop_api_key,
                    instance and instance.prestashop_url, country_id)
                country_details_response_status, country_details_response_data = instance.send_get_request_from_odoo_to_prestashop(
                    api_operation)
                if country_details_response_status:
                    country_dicts = country_details_response_data.get('countries')
                    prestashop_country_list.extend(country_dicts)
                else:
                    log_msg = f"Something went wrong, not getting successful response from Prestashop\n{country_details_response_data}."
                    self.env['prestashop.log.line'].generate_prestashop_process_line('customer',
                                                                                     'import', instance,
                                                                                     log_msg,
                                                                                     False, log_msg, log_id,
                                                                                     True)
            _logger.info(prestashop_country_list)
        except Exception as error:
            _logger.info("Getting Some Error In Fetch The countries :: {0}".format(error))
        return prestashop_country_list

    def fetch_state_from_prestashop_to_odoo(self, instance, state_id):
        """
        This method used to fetch a prestashop states
        """
        log_id = self.env['prestashop.log'].generate_prestashop_logs('customer', 'import', instance, 'Process Started')
        self._cr.commit()
        prestashop_states_list = []
        try:
            if state_id:
                api_operation = "http://%s@%s/api/states/?output_format=JSON&resource=states&filter[id]=[%s]&display=full" % (
                    instance and instance.prestashop_api_key,
                    instance and instance.prestashop_url, state_id)
                states_details_response_status, states_details_response_data = instance.send_get_request_from_odoo_to_prestashop(
                    api_operation)
                if states_details_response_status:
                    customer_dicts = states_details_response_data.get('states')
                    prestashop_states_list.extend(customer_dicts)
                else:
                    log_msg = f"Something went wrong, not getting successful response from Prestashop\n{states_details_response_data}."
                    self.env['prestashop.log.line'].generate_prestashop_process_line('customer',
                                                                                     'import', instance,
                                                                                     log_msg,
                                                                                     False, log_msg, log_id,
                                                                                     True)
            _logger.info(prestashop_states_list)
        except Exception as error:
            _logger.info("Getting Some Error In Fetch The countries :: {0}".format(error))
        return prestashop_states_list

    def fetch_customers_from_prestashop_to_odoo(self, instance):
        """
        This method used to fetch a prestashop customer
        """
        log_id = self.env['prestashop.log'].generate_prestashop_logs('customer', 'import', instance, 'Process Started')
        self._cr.commit()
        prestashop_customer_list = []
        try:
            api_operation = "http://%s@%s/api/customers/?output_format=JSON" % (
                instance and instance.prestashop_api_key,
                instance and instance.prestashop_url)
            customer_response_status, customer_response_data = instance.send_get_request_from_odoo_to_prestashop(api_operation)
            if customer_response_status:
                _logger.info("prestashop Get Customer Response : {0}".format(customer_response_data))
                customers = customer_response_data.get('customers')
                for customer in customers:
                    customer_id = customer.get('id')
                    if customer_id:
                        api_operation = "http://%s@%s/api/customers/?output_format=JSON&resource=customers&filter[id]=[%s]&display=full" % (
                            instance and instance.prestashop_api_key,
                            instance and instance.prestashop_url, customer_id)
                        customer_details_response_status, customer_details_response_data = instance.send_get_request_from_odoo_to_prestashop(
                            api_operation)
                        if customer_details_response_status:
                            customer_dicts = customer_details_response_data.get('customers')
                            prestashop_customer_list.extend(customer_dicts)
                        else:
                            log_msg = f"Something went wrong, not getting successful response from Prestashop\n{customer_response_data or customer_details_response_data}."
                            self.env['prestashop.log.line'].generate_prestashop_process_line('customer',
                                                                                             'import', instance,
                                                                                             log_msg,
                                                                                             False, log_msg, log_id,
                                                                                             True)
            _logger.info(prestashop_customer_list)
        except Exception as error:
            _logger.info("Getting Some Error In Fetch The customer :: {0}".format(error))
        return prestashop_customer_list

    def fetch_customers_addresses_from_prestashop_to_odoo(self, instance, customer_id):
        """
        This method used to fetch a prestashop customer address
        """
        log_id = self.env['prestashop.log'].generate_prestashop_logs('customer', 'import', instance, 'Process Started')
        self._cr.commit()
        prestashop_customer_address_list = []
        try:
            if customer_id:
                api_operation = "http://%s@%s/api/addresses/?output_format=JSON&resource=addresses&filter[id_customer]=[%s]&display=full" % (
                    instance and instance.prestashop_api_key,
                    instance and instance.prestashop_url, customer_id.prestashop_customer_id)
                customer_address_details_response_status, customer_address_details_response_data = instance.send_get_request_from_odoo_to_prestashop(
                    api_operation)
                if customer_address_details_response_status:
                    customer_address_dicts = customer_address_details_response_data.get('addresses')
                    prestashop_customer_address_list.extend(customer_address_dicts)
                else:
                    log_msg = f"Something went wrong, not getting successful response from Prestashop\n{customer_address_details_response_data}."
                    self.env['prestashop.log.line'].generate_prestashop_process_line('customer',
                                                                                     'import', instance,
                                                                                     log_msg,
                                                                                     False, log_msg, log_id,
                                                                                     True)
        except Exception as error:
            _logger.info("Getting Some Error In Fetch The customer :: {0}".format(error))
        return prestashop_customer_address_list

    def import_customers_from_prestashop_to_odoo(self, instance):
        """
        This method use for import customer prestashop to odoo
        """
        to_date = fields.Datetime.now()
        prestashop_customer_list = self.fetch_customers_from_prestashop_to_odoo(instance)
        if prestashop_customer_list:
            res_id_list = self.create_prestashop_customer_queue_job(instance, prestashop_customer_list)
            instance.last_synced_customer_date = to_date
            return res_id_list

    def process_prestashop_customer_queue(self):
        """
        This method is used for Create Customer from prestashop To Odoo
        From customer queue create customer in odoo
        """
        instance_id = self.instance_id
        to_process_customer_queue_line_ids = self.customer_queue_line_ids.filtered(
            lambda x: x.state in ['draft', 'partially_completed', 'failed'] and x.number_of_fails < 3)

        if not self.prestashop_log_id:
            log_id = self.env['prestashop.log'].generate_prestashop_logs('customer', 'import', instance_id, 'Process Started')
        else:
            log_id = self.prestashop_log_id
        self.prestashop_log_id = log_id.id
        for customer_line in to_process_customer_queue_line_ids:
            try:
                # Create or update the main customer in Odoo
                customer_id = self.env['res.partner'].create_update_customer_prestashop_to_odoo(
                    instance_id, customer_line, log_id=log_id)

                if not customer_id:
                    customer_line.number_of_fails += 1
                    continue

                # Fetch all addresses for the customer from PrestaShop
                prestashop_customer_address_list = self.fetch_customers_addresses_from_prestashop_to_odoo(
                    instance_id, customer_id)

                for idx, address in enumerate(prestashop_customer_address_list):
                    # Fetch country and state for each address dynamically
                    country_id = int(address.get('id_country'))
                    prestashop_country = self.fetch_countries_from_prestashop_to_odoo(instance_id, country_id)

                    state_id = int(address.get('id_state'))
                    prestashop_state = self.fetch_state_from_prestashop_to_odoo(instance_id, state_id)


                    # First address is set as the main address
                    if idx == 0:
                        self.env['res.partner'].update_customer_addresses(customer_id, address, prestashop_country, prestashop_state)
                    else:
                        # Subsequent addresses are added as child records
                        self.env['res.partner'].create_child_customer(
                            instance_id, customer_id, address, prestashop_country, prestashop_state)

                customer_line.state = 'completed'

            except Exception as error:
                customer_line.state = 'failed'
                error_msg = '{0} - Error processing customer queue from PrestaShop to Odoo'.format(
                    customer_line.name)
                self.env['prestashop.log.line'].generate_prestashop_process_line(
                    'customer', 'import', instance_id, error_msg, False, error, log_id, True)
                _logger.error(error)

        log_id.prestashop_operation_message = 'Process has been finished'
        if not log_id.prestashop_operation_line_ids:
            log_id.unlink()

class CustomerDataQueueLine(models.Model):
    _name = 'customer.data.queue.line'
    _description = 'Customer Data Line'

    name = fields.Char(string='Customer')
    instance_id = fields.Many2one('prestashop.instance.integration', string='Instance', help='Select Instance Id',
                                  copy=False)
    customer_id = fields.Char(string="Customer ID", help='This is the Customer Id of prestashop customer',
                              copy=False)
    state = fields.Selection([('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                              ('completed', 'Completed'), ('failed', 'Failed')], tracking=True,
                             default='draft', copy=False)
    customer_data_to_process = fields.Text(string="customer Data", copy=False)
    customer_queue_id = fields.Many2one('customer.data.queue', string='Customer Queue')
    res_partner_id = fields.Many2one("res.partner")
    number_of_fails = fields.Integer(string="Number of attempts",
                                     help="This field gives information regarding how many time we will try to proceed the order",
                                     copy=False)

    def _valid_field_parameter(self, field, name):
        return name == 'tracking' or super()._valid_field_parameter(field, name)

    def create_prestashop_customer_queue_line(self, prestashop_customer_dict, instance_id, queue_id):
        """This method used to create a prestashop customer queue  line """
        name = "%s %s" % (prestashop_customer_dict.get('firstname') or "", (prestashop_customer_dict.get('lastname') or ""))
        customer_queue_line_id = self.create({
            'customer_id': prestashop_customer_dict.get('id'),
            'state': 'draft',
            'name': name.strip(),
            'customer_data_to_process': pprint.pformat(prestashop_customer_dict),
            'instance_id': instance_id and instance_id.id or False,
            'customer_queue_id': queue_id and queue_id.id or False,
        })
        return customer_queue_line_id
