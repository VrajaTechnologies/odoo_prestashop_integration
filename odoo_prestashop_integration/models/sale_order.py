from odoo import models, fields, _
import logging
from dateutil import parser
import pytz
import time

utc = pytz.utc
_logger = logging.getLogger("Prestashop Order: ")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    instance_id = fields.Many2one('prestashop.instance.integration', string="Instance", copy=False)
    prestashop_order_reference = fields.Char(string="Prestashop Order Reference", copy=False,
                                             help="This is the represent the reference of prestashop order")
    prestashop_order_id = fields.Char(string="Prestashop Order Number", copy=False,
                                      help="This is the represent the number of prestashop order")
    prestashop_order_status = fields.Char(string="Prestashop Order Status", copy=False,
                                          help="This is the represent the status of this order")
    prestashop_carrier_ref = fields.Char(string="Prestashop Carrier Reference", copy=False, help="This is the represent the Prestashop Carrier")
    prestashop_payment_ref = fields.Char(string="Prestashop Payment Reference", copy=False, help="This is the represent the Prestashop Payment Reference")
    # financial_status = fields.Char(string="Financial Status", copy=False)
    # fulfillment_status = fields.Char(string="Fulfillment Status", copy=False)
    # sale_auto_workflow_id = fields.Many2one("order.workflow.automation", string="Sale Auto Workflow",
    #                                         copy=False)
    # risk_ids = fields.One2many("prestashop.risk.order", 'odoo_order_id', "Risks", copy=False)
    # is_order_risky = fields.Boolean(string="Is Order Risky?", default=False, copy=False)
    prestashop_order_closed_at = fields.Datetime(string='Order Closed At')
    is_prestashop_multi_payment = fields.Boolean("Prestashop Multi Payments?", default=False, copy=False,
                                                 help="This is utilized to determine whether an order involves multiple payment gateways.")

    # prestashop_payment_transactions_ids = fields.One2many('prestashop.order.payment.transactions',
    #                                                    'sale_order_id', string="Payment Transactions")

    def convert_order_date(self, order_response):
        if order_response.get("date_add", False):
            order_date = order_response.get("date_add", False)
            date_order = parser.parse(order_date).astimezone(utc).strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_order = time.strftime("%Y-%m-%d %H:%M:%S")
            date_order = str(date_order)

        return date_order

    def get_order_currency(self, instance, prestashop_order_dictionary):
        currency = prestashop_order_dictionary.get('id_currency')
        api_operation = "http://%s@%s/api/currencies/?output_format=JSON&filter[id]=[%s]&display=full" % (
            instance.prestashop_api_key, instance.prestashop_url, currency)
        response_status, currency_response_data = instance.send_get_request_from_odoo_to_prestashop(
            api_operation)
        if response_status:
            currency_data = currency_response_data.get('currencies')[0]
            order_currency_id = self.env['res.currency'].search(
                [('name', '=', currency_data.get('iso_code')), ('active', 'in', [True, False])], limit=1)
            return order_currency_id
        else:
            _logger.info("Getting Some Error In Fetch The Currencies :: \n {}".format(currency_response_data))

    def get_price_list(self, currency_id, instance_id):
        price_list_object = self.env['product.pricelist']
        price_list_id = instance_id.price_list_id or False
        if not price_list_id:
            price_list_id = price_list_object.search([('currency_id', '=', currency_id.id)], limit=1)
        return price_list_id

    def get_carrier_list(self, prestashop_order_dict, instance):
        carrier_id = prestashop_order_dict.get('id_carrier')
        if carrier_id:
            api_operation = "http://%s@%s/api/carriers/?output_format=JSON&filter[id]=[%s]&display=full" % (
                instance.prestashop_api_key,
                instance.prestashop_url, carrier_id)
            response_status, carrier_response_data = instance.send_get_request_from_odoo_to_prestashop(
                api_operation)
            if response_status:
                carrier_list = carrier_response_data.get('carriers')
                return carrier_list
            else:
                _logger.info("Getting Some Error In Fetch The Carrier :: \n {}".format(carrier_response_data))

    def find_create_customer_in_odoo(self, instance_id, prestashop_order_dict, log_id=False):
        """
        This method was used for search or create customer in odoo if we have not found customer in odoo then
        we call the api and create that customer in odoo
        @param : instance_id : object of instance
                 prestashop_order_dict : json response of prestashop sale order response
        @return : if not found customer id in response then return false otherwise return customer id
        """
        prestashop_customer_id = prestashop_order_dict.get('id_customer')
        if not prestashop_customer_id:
            return False
        odoo_customer_id = self.env['res.partner'].search([('prestashop_customer_id', '=', prestashop_customer_id)],
                                                          limit=1)
        if odoo_customer_id:
            return odoo_customer_id
        else:
            try:
                prestashop_customer_data = self.env['customer.data.queue'].fetch_customers_from_prestashop_to_odoo(
                    instance_id, prestashop_customer_id, log_id)
            except Exception as e:
                _logger.info(e)
            so_customer_data = prestashop_customer_data
            customer_id = self.env['res.partner'].create_update_customer_prestashop_to_odoo(instance_id=instance_id,
                                                                                            so_customer_data=so_customer_data,
                                                                                            log_id=log_id)
            return customer_id

    def prepare_vals_for_sale_order_line(self, quantity, price, product_id, sale_order_id, is_delivery=False):
        """
        This method used to prepare basic vals for sale order line in odoo
        @param : quantity :order line quantity,
                 price : price of sale order line
                 product_id : product detail of sale order line
                 sale_order_id : object of created sale order
                 is_delivery : boolean object of product is delivery or not
        @return : vals for creating order line
        """
        vals = {
            'order_id': sale_order_id.id,
            'product_id': product_id.id,
            'product_uom_qty': quantity,
            'price_unit': price,
            'is_delivery': is_delivery
        }
        return vals

    def create_sale_order_line(self, sale_order_id, prestashop_order_dict, instance_id):
        """This method was used for create a sale order line in odoo
            @param : sale_order_id : object of created sale order in parent method
                     prestashop_order_dict : json response of prestashop sale order
                     instance_id : object of instance
        """
        # product_id = self.env['product.product']
        order_lines = prestashop_order_dict.get('associations', {}).get('order_rows', [])
        total_discount = float(prestashop_order_dict.get("total_discounts", 0.0))
        total_shipping = float(prestashop_order_dict.get("total_shipping", 0.0))

        if isinstance(order_lines, dict):
            order_lines = [order_lines]
        for line in order_lines:
            prestashop_product = int(line.get('product_id'))
            prestashop_product_attribute = int(line.get('product_attribute_id'))
            product_id = ''
            if prestashop_product_attribute == 0:
                product_listing_id = self.env['prestashop.product.listing'].search([
                    ('prestashop_product_id', '=', prestashop_product),
                    ('prestashop_instance_id', '=', instance_id.id)])
                if product_listing_id:
                    product_id = product_listing_id.product_tmpl_id.product_variant_id
            else:
                product_listing_item_id = self.env['prestashop.product.listing.item'].search([
                    ('prestashop_product_variant_id', '=', prestashop_product_attribute),
                    ('prestashop_instance_id', '=', instance_id.id)])
                if product_listing_item_id:
                    product_id = product_listing_item_id.product_id

            line_vals = self.prepare_vals_for_sale_order_line(line.get('product_quantity'), line.get('product_price'),
                                                              product_id,
                                                              sale_order_id)

            sale_order_line = self.env['sale.order.line'].create(line_vals)
            sale_order_line.with_context(round=False)._compute_amount()
            # previous_line = line_vals

            # below code is check for add the discount line at sale order line
            if total_discount > 0.0:
                line_vals = self.prepare_vals_for_sale_order_line(1, -total_discount,
                                                                  instance_id.prestashop_discount_product_id,
                                                                  sale_order_id)
                line_vals.update({'name': "Discount for {0}".format(product_id.name)})
                sale_order_line = self.env['sale.order.line'].create(line_vals)
                sale_order_line.with_context(round=False)._compute_amount()

            if total_shipping > 0.0:
                line_vals = self.prepare_vals_for_sale_order_line(1, total_shipping,
                                                                  instance_id.prestashop_shipping_product_id,
                                                                  sale_order_id)
                line_vals.update({'name': "Shipping for {0}".format(product_id.name)})
                sale_order_line = self.env['sale.order.line'].create(line_vals)
                sale_order_line.with_context(round=False)._compute_amount()

        return True

    def search_listing_item(self, line, instance_id):
        """This method was used for find the product in odoo
            @param : line : dictionary of specific prestashop sale order line
                    instance_id : object of instance
        """
        product_variant_id = line.get('product_attribute_id')
        product_id = line.get('product_id')
        prestashop_product_listing_item_id = self.env['prestashop.product.listing.item'].search(
            [('prestashop_product_variant_id', '=', product_variant_id),
             ('prestashop_instance_id', '=', instance_id.id)])
        prestashop_product_listing_id = self.env['prestashop.product.listing'].search(
            [('prestashop_product_id', '=', product_id), ('prestashop_instance_id', '=', instance_id.id)])
        if product_variant_id != '0':
            if not prestashop_product_listing_item_id and line.get('product_reference'):
                prestashop_product_listing_item_id = self.env['prestashop.product.listing.item'].search(
                    [('product_sku', '=', line.get('product_reference')),
                     ('prestashop_instance_id', '=', instance_id.id)])
                if prestashop_product_listing_item_id:
                    prestashop_product_listing_item_id.prestashop_product_variant_id = product_variant_id
                return False
        return prestashop_product_listing_item_id or prestashop_product_listing_id

    def check_missing_value_details(self, order_lines, instance_id, order_number, log_id):
        """This method used to check the missing details in the order lines.
            @param order_lines : response of prestashop sale order lines
                   instance_id :  object of instance
                   order_number : prestashop order number
                   log_id : object of created main log for create log line
            @return : mismatch : if found mismatch value then return true otherwise return false
        """
        mismatch = False
        log_msg = ''
        fault_or_not = False

        for order_line in order_lines:
            prestashop_product = self.search_listing_item(order_line, instance_id)
            if prestashop_product:
                continue

            if not prestashop_product:
                variant_id = order_line.get("product_attribute_id", False)
                product_id = order_line.get("product_id", False)
                if variant_id and product_id:
                    self.env['prestashop.product.listing'].prestashop_create_products(False, instance_id, log_id,
                                                                                      product_id)
                    prestashop_product_id = self.search_listing_item(order_line, instance_id)
                    if not prestashop_product_id:
                        error_msg = "Product {0} {1} not found for Order {2}".format(
                            order_line.get("product_reference"), order_line.get("product_name"), order_number)
                        return True, error_msg, True, 'failed'
                    continue
        return mismatch, log_msg, fault_or_not, 'draft'

    def process_import_order_from_prestashop(self, prestashop_order_dict, instance_id, log_id, line):
        """
        This method was used for import the order from prestashop to doo and process that order.
        If any order cancelled then do appropriate process to generate refund & return.
        @param : prestashop_order_dict : json response of specific order queue line
                 instance_id : object of instance__id
                 log_id : object of created log_id when process was start
                 line : object of specific order queue line
        return : sale order : Object of sale order which is created in odoo based on order queue line response data
        """
        # Search for existing sale order
        existing_sale_order_id = self.search(
            [('instance_id', '=', instance_id.id), ('prestashop_order_id', '=', prestashop_order_dict.get('id')),
             ('prestashop_order_reference', '=', prestashop_order_dict.get('reference', ''))])

        delivery_address_id = int(prestashop_order_dict.get('id_address_delivery'))
        invoice_address_id = int(prestashop_order_dict.get('id_address_invoice'))

        delivery_address = self.env['res.partner'].search([('prestashop_address_id', '=', delivery_address_id)],
                                                          limit=1)
        invoice_address = self.env['res.partner'].search([('prestashop_address_id', '=', invoice_address_id)], limit=1)

        order_status = self.env['prestashop.order.status'].search(
            [('order_status_id', '=', prestashop_order_dict.get('current_state'))])
        customer_id = ''
        if delivery_address and invoice_address:
            # Find customer if not exists then create new
            customer_id = self.find_create_customer_in_odoo(instance_id, prestashop_order_dict, log_id)

        if not customer_id:
            log_msg = 'Can not find customer details in sale order response {0}'.format(
                prestashop_order_dict.get('name', ''))
            _logger.info(log_msg)
            return False, log_msg, True, 'failed'

        carrier_ref = ''
        carrier_list = self.get_carrier_list(prestashop_order_dict, instance_id)
        for carrier in carrier_list:
            carrier_ref = carrier.get('name')

        date_order = self.convert_order_date(prestashop_order_dict)
        currency_id = self.get_order_currency(instance_id, prestashop_order_dict)
        price_list_id = self.get_price_list(currency_id, instance_id)

        if existing_sale_order_id:
            line.sale_order_id = existing_sale_order_id.id
            log_msg = "Order Number {0} - {1}".format(existing_sale_order_id.name, "Is Already Exist In Odoo")
            return existing_sale_order_id, log_msg, False, 'completed'
        order_lines = prestashop_order_dict.get('associations', {}).get('order_rows', [])
        order_number = prestashop_order_dict.get("id")

        # Check mismatch values for sale order line
        if not order_lines:
            log_msg = "Order Number {0} - {1}".format(existing_sale_order_id.name, "have no any order lines.")
            return False, log_msg, True, 'failed'
        else:
            product_result, log_msg, fault_or_not, line_state = self.check_missing_value_details(order_lines,
                                                                                                 instance_id,
                                                                                                 order_number, log_id)
            if product_result:
                return False, log_msg, fault_or_not, line_state

        sale_order_vals = {"partner_id": customer_id and customer_id.id,
                           "date_order": date_order,
                           'company_id': instance_id.company_id.id or '',
                           'warehouse_id': instance_id.warehouse_id.id or '',
                           'partner_invoice_id': invoice_address.id or False,
                           'partner_shipping_id': delivery_address.id or False,
                           'state': 'draft',
                           'pricelist_id': price_list_id and price_list_id.id or '',
                           'instance_id': instance_id.id,
                           'prestashop_payment_ref': prestashop_order_dict.get('payment', ''),
                           'prestashop_carrier_ref': carrier_ref or '',
                           'prestashop_order_status': order_status.name if order_status else False,
                           'prestashop_order_reference': prestashop_order_dict.get('reference', ''),
                           'prestashop_order_id': prestashop_order_dict.get('id', ''),
                           }

        sale_order_id = self.create(sale_order_vals)
        #
        if sale_order_id:
            sale_order_id.create_sale_order_line(sale_order_id, prestashop_order_dict, instance_id)
        log_msg = "Sale Order {0} - {1}".format(sale_order_id.name, "Created Successfully")
        return sale_order_id, log_msg, False, 'completed'
