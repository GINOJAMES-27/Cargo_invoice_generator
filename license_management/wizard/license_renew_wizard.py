from odoo import models, fields, exceptions, _
import json
import base64
from datetime import datetime

class LicenseRenewWizard(models.TransientModel):
    _name = 'license.renew.wizard'
    _description = 'Renew License Wizard'

    renewal_key = fields.Char(string='Renewal Key')
    renewal_file = fields.Binary(string='Renewal File (.json)')

    def action_renew(self):
        self.ensure_one()
        
        license_data = None
        key = self.renewal_key
        
        if self.renewal_file:
            try:
                file_content = base64.b64decode(self.renewal_file).decode('utf-8')
                license_data = json.loads(file_content)
                key = license_data.get('license_key')
            except Exception as e:
                raise exceptions.UserError(_("Invalid renewal file. Please upload a valid JSON file."))
                
        if not key:
            raise exceptions.UserError(_("Please provide a renewal key or upload a renewal file."))
            
        license_obj = self.env['license.management'].search([('license_key', '=', key)], limit=1)
        
        if not license_obj:
            raise exceptions.UserError(_("License key not found in the system. Cannot renew an unknown license."))
            
        if license_data and 'expiry' in license_data:
            new_expiry = datetime.strptime(license_data['expiry'], '%Y-%m-%d').date()
            license_obj.action_renew(new_expiry)
        else:
            raise exceptions.UserError(_("Renewal file does not contain a new expiry date."))
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('License Renewed'),
                'message': _('The license has been successfully renewed!'),
                'type': 'success',
                'sticky': False,
            }
        }
