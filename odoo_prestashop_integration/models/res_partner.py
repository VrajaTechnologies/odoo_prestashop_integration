from odoo import models, fields
from datetime import datetime
import logging
_logger = logging.getLogger("Prestashop Customer: ")



class ResPartner(models.Model):
    _inherit = 'res.partner'

    prestashop_customer_id = fields.Char(string="Prestashop Customer ID",
                                      help="This is just a reference of prestashop customer identifier", tracking=True)
    prestashop_instance_id = fields.Many2one('prestashop.instance.integration', string="prestashop Instance",
                                          help="This field show the instance details of Prestashop", tracking=True)
    prestashop_address_id = fields.Char(string="Prestashop Address ID", copy=False,
                                 help="This ID consider as a Prestashop Customer Address ID", tracking=True)
    prestashop_customer_birthdate = fields.Date(string="Customer BirthDate", copy=False)

    def create_child_customer(self, instance_id, customer_id, address, prestashop_country, prestashop_state):
        """This method was used if in customer response there are multiple address then we will create child customer
        address using this method
        @param : instance_id : Object of instance
                 customer_datas : json response of customer data
                 customer_id : object of main customer which is created in previous method
        """
        country_id = ''
        state_id = ''
        for country in prestashop_country:
            country_id = self.env['res.country'].search([('code', '=', country.get('iso_code'))],limit=1)
        for state in prestashop_state:
            state_id = self.env['res.country.state'].search(
                [('code', '=', state.get('iso_code')), ('country_id', '=', country_id.id)],limit=1)

        phone_num = address.get('phone', '')
        mobile_num = address.get('mobile', '')
        phone = phone_num if phone_num.isdigit() else ''
        mobile = mobile_num if mobile_num.isdigit() else ''

        # Prepare address values
        address_vals = {
            'name': address.get('firstname') + ' ' + address.get('lastname') or '',
            'street': address.get('address1', ''),
            'street2': address.get('address2', ''),
            'city': address.get('city', ''),
            'zip': address.get('postcode', ''),
            'phone': phone or '',
            'mobile': mobile or '',
            'country_id': country_id.id if country_id else False,
            'state_id': state_id.id if state_id else False,
            'parent_id': customer_id.id,
            'prestashop_instance_id': instance_id.id,
            'prestashop_address_id': address.get('id'),
            'type': 'other'

        }
        existing_address = self.env['res.partner'].search([('prestashop_address_id', '=', address.get('id',''))], limit=1)

        if existing_address:
            # Update the existing address
            existing_address.write(address_vals)
        else:
            # Create a new child address
            self.env['res.partner'].create(address_vals)

        return customer_id

    def create_update_customer_prestashop_to_odoo(self, instance_id, customer_line=False,
                                               log_id=False):
        """
        This method used for create and update customer from prestashop to odoo
        @param instance_id : object of instance,
            customer_line : object of customer queue line
            customer_data : json response of specific customer data
            so_customer_data : json response of customer data from sale order level
            log_id : object of log_id for create log line
        @Return : Updated or Created Customer ID / Customer Object
        """
        partner_obj = self.env["res.partner"]
        customer_data = customer_line and eval(customer_line.customer_data_to_process)
        prestashop_customer_id = customer_data.get('id')
        full_name = "{0} {1}".format(customer_data.get('firstname', '') or '',
                                     customer_data.get('lastname', '') or '')
        date_str = customer_data.get('birthday')
        birthdate = ''
        if date_str != '0000-00-00':
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            birthdate = date_obj.strftime('%Y-%m-%d')

        customer_vals = {'name': full_name,
                         'prestashop_customer_id': prestashop_customer_id,
                         'email': customer_data.get('email') or '',
                         'website': customer_data.get('website') or '',
                         'prestashop_customer_birthdate': birthdate if birthdate else False,
                         'prestashop_instance_id': instance_id.id}
        existing_customer = self.env['res.partner'].search(['|', ('prestashop_customer_id', '=', prestashop_customer_id),('email','=',customer_data.get('email'))],
                                                           limit=1)
        if existing_customer:
            existing_customer.write(customer_vals)
            customer_id = existing_customer
            if customer_line:
                customer_line.state = 'completed'
            msg = "Customer {0} Updated Successfully".format(full_name)
        else:
            customer_id = partner_obj.create(customer_vals)
            if customer_line:
                customer_line.state = 'completed'
            msg = "Customer {0} Created Successfully".format(full_name)
        self.env['prestashop.log.line'].generate_prestashop_process_line('customer', 'import', instance_id, msg, False,
                                                                   customer_data, log_id, False)

        if customer_line:
            customer_line.res_partner_id = customer_id.id
        self._cr.commit()
        return customer_id

    def update_customer_addresses(self, customer_id, address, prestashop_country, prestashop_state):
        """
        Update the addresses for the processed customers.
        """

        country_id = ''
        state_id = ''
        for country in prestashop_country:
            country_id = self.env['res.country'].search([('code', '=', country.get('iso_code'))])
        for state in prestashop_state:
            state_id = self.env['res.country.state'].search(
                [('code', '=', state.get('iso_code')), ('country_id', '=', country_id.id)])


        phone_num = address.get('phone', '')
        mobile_num = address.get('mobile', '')
        phone = phone_num if phone_num.isdigit() else ''
        mobile = mobile_num if mobile_num.isdigit() else ''

        # Prepare address values
        address_vals = {
            'street': address.get('address1', ''),
            'street2': address.get('address2', ''),
            'city': address.get('city', ''),
            'zip': address.get('postcode', ''),
            'country_id': country_id.id if country_id else False,
            'state_id': state_id.id if state_id else False,
            'phone': phone or '',
            'mobile': mobile or '',
            'prestashop_address_id': address.get('id'),
        }

        # Check if the address exists
        existing_address = self.env['res.partner'].search([
            ('prestashop_customer_id', '=', address.get('id_customer'))
        ], limit=1)
        if existing_address:
            customer_id.write(address_vals)



