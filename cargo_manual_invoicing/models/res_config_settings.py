from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    shippo_api_key = fields.Char(string="Shippo API Token", config_parameter='cargo_manual_invoicing.shippo_api_key')
    shippo_test_mode = fields.Boolean(
        string="Test/Sandbox Mode",
        default=True,
        config_parameter='cargo_manual_invoicing.shippo_test_mode',
        help="When enabled, no real shipments are created. Ensure you are using a Shippo Test Token (starts with shippo_test_)."
    )
    shippo_default_carrier = fields.Char(
        string="Default Carrier Account",
        default="dhl_express",
        config_parameter='cargo_manual_invoicing.shippo_default_carrier',
        help="The default carrier object_id or carrier token (e.g. dhl_express, usps) from your Shippo dashboard."
    )
    shippo_default_servicelevel = fields.Char(
        string="Default Service Level",
        default="dhl_express_worldwide",
        config_parameter='cargo_manual_invoicing.shippo_default_servicelevel',
        help="The default service level token (e.g. dhl_express_worldwide, usps_priority)."
    )

    shippo_shipper_name = fields.Char(
        string="Shipper Company/Name",
        default="Brightness of Hope Air Cargo Est",
        config_parameter='cargo_manual_invoicing.shippo_shipper_name'
    )
    shippo_shipper_street = fields.Char(
        string="Shipper Street",
        default="Abu Saad Al-Wazir Street, Al Aziziyah",
        config_parameter='cargo_manual_invoicing.shippo_shipper_street'
    )
    shippo_shipper_city = fields.Char(
        string="Shipper City",
        default="Riyadh",
        config_parameter='cargo_manual_invoicing.shippo_shipper_city'
    )
    shippo_shipper_zip = fields.Char(
        string="Shipper Zip/Postal Code",
        default="11564",
        config_parameter='cargo_manual_invoicing.shippo_shipper_zip'
    )
    shippo_shipper_country = fields.Char(
        string="Shipper Country Code",
        default="SA",
        config_parameter='cargo_manual_invoicing.shippo_shipper_country'
    )
    shippo_shipper_phone = fields.Char(
        string="Shipper Phone",
        default="0574436896",
        config_parameter='cargo_manual_invoicing.shippo_shipper_phone'
    )
    shippo_shipper_email = fields.Char(
        string="Shipper Email",
        default="ginojames1030@gmail.com",
        config_parameter='cargo_manual_invoicing.shippo_shipper_email'
    )

    def action_test_shippo_connection(self):
        self.ensure_one()
        # Ensure we save the fields to config_parameter before testing
        self.execute()
        
        service = self.env['shippo.integration.service']
        success, message = service._test_shippo_connection()
        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            # We import UserError here to avoid circular imports if any
            # pyrefly: ignore [missing-import]
            from odoo.exceptions import UserError
            raise UserError(message)
