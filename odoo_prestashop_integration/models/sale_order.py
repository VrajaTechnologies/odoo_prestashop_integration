from odoo import models, fields, _
import logging

_logger = logging.getLogger("Prestashop Order: ")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    instance_id = fields.Many2one('prestashop.instance.integration', string="Instance", copy=False)

    is_already_sync = fields.Boolean(
        string="Is Already Sync?",
        copy=False
    )


    def prestashop_import_orders(self, instance):
        """
        This method is used to import all chart of accounts from prestashop to odoo.
        """
        instance = self.env['prestashop.instance.integration'].browse(instance)
        log_id = self.env['prestashop.log'].generate_prestashop_logs('order', 'import', instance, 'Process Started')
        try:
            url = ''.format()
            authorization_code = 'Bearer {}'.format()
            headers = {
                'Authorization': authorization_code,
            }
            request_data = {}
            response_status, response_data = instance.api_calling_method("GET", url, request_data, headers)

            if response_status:
                for page in range(response_data.get('page_context').get('page')):
                    try:
                        url = ''.format(page)
                        response_status, response_data = instance.api_calling_method("GET", url, request_data, headers)
                        if response_status:
                            print('response_status.....',response_status)
                        else:
                            log_msg = f"Something went wrong, not getting successful response from Prestashop\n{response_data}."
                            self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance,
                                                                                             log_msg,
                                                                                             False, log_msg, log_id, True)
                    except Exception as e:
                        log_msg = f"Something went wrong.\n{e}."
                        self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance, log_msg,
                                                                                         False, log_msg, log_id, True)
            else:
                log_msg = f"Something went wrong, not getting successful response from Prestashop\n{response_data}."
                self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance, log_msg,
                                                                                 False, log_msg, log_id, True)

        except Exception as e:
            log_msg = f"Something went wrong.\n{e}."
            self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'import', instance, log_msg,
                                                                             False, log_msg, log_id, True)
        finally:
            log_id.prestashop_operation_message = 'Process Has Been Finished'
            if not log_id.prestashop_operation_line_ids:
                log_id.unlink()


    def create_update_order_prestashop_to_odoo(self, instance_id, log_id=False):
        pass