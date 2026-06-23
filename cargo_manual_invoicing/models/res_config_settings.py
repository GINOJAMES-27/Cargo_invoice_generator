from odoo import models, fields, api
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dhl_api_key = fields.Char(string="DHL API Key", config_parameter='cargo_manual_invoicing.dhl_api_key')
    dhl_api_secret = fields.Char(string="DHL API Secret", config_parameter='cargo_manual_invoicing.dhl_api_secret')
    dhl_account_number = fields.Char(string="DHL Account Number", config_parameter='cargo_manual_invoicing.dhl_account_number')
    
    dhl_sandbox_mode = fields.Boolean(
        string="Enable Sandbox Mode",
        default=True,
        config_parameter='cargo_manual_invoicing.dhl_sandbox_mode',
        help="Enable sandbox mode for testing (no real shipments created)."
    )
    dhl_sandbox_url = fields.Char(
        string="Sandbox URL",
        default="https://express.api.dhl.com/mydhlapi/test",
        config_parameter='cargo_manual_invoicing.dhl_sandbox_url'
    )
    dhl_production_url = fields.Char(
        string="Production URL",
        default="https://express.api.dhl.com/mydhlapi",
        config_parameter='cargo_manual_invoicing.dhl_production_url'
    )
    
    dhl_shipper_country_code = fields.Char(
        string="Shipper Country Code",
        default="SA",
        config_parameter='cargo_manual_invoicing.dhl_shipper_country_code'
    )
    dhl_shipper_city = fields.Char(
        string="Shipper City",
        default="Riyadh",
        config_parameter='cargo_manual_invoicing.dhl_shipper_city'
    )
    dhl_shipper_postal_code = fields.Char(
        string="Shipper Postal Code",
        default="11564",
        config_parameter='cargo_manual_invoicing.dhl_shipper_postal_code'
    )

    def action_test_dhl_connection(self):
        try:
            success, message = self.env['dhl.integration.service']._test_dhl_connection()
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
                raise UserError(message)
        except Exception as e:
            raise UserError(str(e))
