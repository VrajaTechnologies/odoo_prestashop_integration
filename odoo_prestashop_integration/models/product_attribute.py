from odoo import fields, models, api
import logging

_logger = logging.getLogger("prestashop")


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    def get_attribute(self, attribute_string, attribute_type='radio', create_variant='always', auto_create=False):
        """
        Returns the attribute if it is available; otherwise, creates a new one and returns it.
        DG
        """
        attributes = self.search([('name', '=ilike', attribute_string),
                                  ('create_variant', '=', create_variant)], limit=1)
        if not attributes and auto_create:
            return self.create(({'name': attribute_string, 'create_variant': create_variant,
                                 'display_type': attribute_type}))
        return attributes

    def create_product_option_from_prestashop(self, instance, product_data=False, log_id=False):
        """
        DG
        """
        if not log_id:
            log_id = self.env['prestashop.log'].generate_prestashop_logs('product_attribute', 'import', instance,
                                                                         'Process Started')
            self._cr.commit()

        try:
            # Fetch product options (attributes) from Prestashop API
            option_api_operation = "http://%s@%s/api/product_options/?output_format=JSON" % (
                instance.prestashop_api_key, instance.prestashop_url)
            option_response_status, option_response_data = instance.send_get_request_from_odoo_to_prestashop(
                option_api_operation)
            if option_response_status:
                _logger.info("Prestashop Get Product Option Response: %s", option_response_data)
                options = option_response_data.get('product_options', [])
                options_ids = [opt.get('id') for opt in options]
                options_range = [options_ids[0], options_ids[-1]] if len(options_ids) > 1 else options_ids
                product_attributes = []

                api_operation = "http://%s@%s/api/product_options/?output_format=JSON&filter[id]=%s&display=full" % (
                    instance.prestashop_api_key, instance.prestashop_url, options_range)
                response_status, response_data = instance.send_get_request_from_odoo_to_prestashop(api_operation)
                if not response_status:
                    log_msg = f"Failed to fetch attribute details: {response_data}"
                    self.env['prestashop.log.line'].generate_prestashop_process_line('product_attribute', 'import',
                                                                                     instance, log_msg, False, log_msg,
                                                                                     log_id, True)
                    return

                product_option_values_ids = {item['id'] for item in
                                             product_data.get('associations').get('product_option_values')}
                for pro_option in response_data.get('product_options', []):
                    # Initialize dictionary for attribute with 'name' and 'values' keys
                    vals_for_attribute_and_values = {
                        'name': pro_option.get('name'),
                        'values': [],
                        'values_ids': []
                    }

                    att_opt_value_ids = {item['id'] for item in
                                         pro_option.get('associations').get('product_option_values')}
                    matching_ids = product_option_values_ids.intersection(att_opt_value_ids)
                    if matching_ids:
                        for match_value in matching_ids:
                            api_operation = "http://%s@%s/api/product_option_values/?output_format=JSON&filter[id]=[%s]&display=full" % (
                                instance.prestashop_api_key, instance.prestashop_url, match_value)
                            response_status, response_data = instance.send_get_request_from_odoo_to_prestashop(
                                api_operation)
                            if response_status:
                                # Append the value name to 'values' list
                                option_value = response_data.get('product_option_values')[0]
                                vals_for_attribute_and_values['values'].append(option_value.get('name'))
                                vals_for_attribute_and_values.setdefault('values_ids', []).append(option_value.get('id'))
                        # Add the constructed dictionary to the list
                        product_attributes.append(vals_for_attribute_and_values)
                return product_attributes
        except Exception as e:
            log_msg = f"Something went wrong.\n{e}."
            self.env['prestashop.log.line'].generate_prestashop_process_line('product_attribute', 'import', instance,
                                                                             log_msg, False, log_msg, log_id, True)
