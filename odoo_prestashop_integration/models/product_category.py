from odoo import fields, models
import logging

_logger = logging.getLogger("Prestashop: Product category")


class ProductCategory(models.Model):
    _inherit = "product.category"

    prestashop_category_url = fields.Char(
        string="Custom Url",
        copy=False
    )
    prestashop_parent_category_id = fields.Char(
        string="Prestashop Parent Category ID",
        copy=False
    )
    prestashop_category_id = fields.Char(
        string="Prestashop Category ID",
        copy=False
    )
    instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string="Instance",
        copy=False
    )
    is_already_sync = fields.Boolean(
        string="Is Already Sync?",
        copy=False
    )

    def prestashop_to_odoo_import_product_categories(self, instance, log_id=False):
        """
        DG
        """
        instance = self.env['prestashop.instance.integration'].browse(instance)
        if not log_id:
            log_id = self.env['prestashop.log'].generate_prestashop_logs('product_category', 'import', instance,
                                                                         'Process Started')
            self._cr.commit()

        try:
            api_url = "http://%s@%s/api/categories/?output_format=JSON" % (
                instance.prestashop_api_key, instance.prestashop_url)
            response_status, response_data = instance.send_get_request_from_odoo_to_prestashop(api_url)

            if not response_status:
                log_msg = f"Error in Product Category Response: {response_data.content}"
                _logger.info(log_msg)
                self.env['prestashop.log.line'].generate_prestashop_process_line('product_category', 'import', instance,
                                                                                 log_msg, False, log_msg, log_id, True)
                return

            categories = response_data.get('categories', [])
            if not categories:
                _logger.info("No categories found in Prestashop response.")
                return

            category_ids = [categ.get('id') for categ in categories]
            category_range = [category_ids[0], category_ids[-1]] if len(category_ids) > 1 else category_ids

            api_url = "http://%s@%s/api/categories/?output_format=JSON&filter[id]=%s&display=full" % (
                instance.prestashop_api_key, instance.prestashop_url, category_range)
            response_status, response_data = instance.send_get_request_from_odoo_to_prestashop(api_url)

            if not response_status:
                log_msg = f"Failed to fetch category details: {response_data}"
                self.env['prestashop.log.line'].generate_prestashop_process_line('product_category', 'import', instance,
                                                                                 log_msg, False, log_msg, log_id, True)
                return

            for category in response_data.get('categories', []):
                prestashop_id = category.get('id')
                parent_id_res = category.get('id_parent')

                existing_category = self.env['product.category'].search(
                    [('prestashop_category_id', '=', prestashop_id)], limit=1)
                if existing_category:
                    continue

                parent_category = self.env['product.category']
                if parent_id_res != '0':
                    parent_category = self.env['product.category'].search(
                        [('prestashop_category_id', '=', parent_id_res)], limit=1)

                vals = {
                    'name': category.get('name'),
                    'prestashop_category_url': category.get('link_rewrite'),
                    'prestashop_parent_category_id': parent_id_res,
                    'property_cost_method': 'standard',
                    'property_valuation': 'manual_periodic',
                    'prestashop_category_id': prestashop_id,
                    'parent_id': parent_category.id,
                    'is_already_sync': True
                }
                new_category = self.env['product.category'].create(vals)
                process_msg = f"Product Category Created: {new_category.name}"
                _logger.info(process_msg)

                self.env['prestashop.log.line'].generate_prestashop_process_line('product_category', 'import', instance,
                                                                                 process_msg, False, process_msg,
                                                                                 log_id, False)
                self._cr.commit()

        except Exception as e:
            log_msg = f"Exception during import: {e}"
            _logger.error(log_msg)
            self.env['prestashop.log.line'].generate_prestashop_process_line('product_category', 'import', instance,
                                                                             log_msg, False, log_msg, log_id, True)

        finally:
            log_id.prestashop_operation_message = 'Process Has Been Finished'
            if not log_id.prestashop_operation_line_ids:
                log_id.unlink()
