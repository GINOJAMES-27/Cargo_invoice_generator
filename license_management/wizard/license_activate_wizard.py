from odoo import models, fields, exceptions, _
import json
import base64

class LicenseActivateWizard(models.TransientModel):
    _name = 'license.activate.wizard'
    _description = 'Activate License Wizard'

    license_key = fields.Char(string='License Key')
    license_file = fields.Binary(string='License File (.json)')

    def action_activate(self):
        self.ensure_one()
        
        license_data = None
        key = self.license_key
        
        if self.license_file:
            try:
                file_content = base64.b64decode(self.license_file).decode('utf-8')
                license_data = json.loads(file_content)
                key = license_data.get('license_key')
            except Exception as e:
                raise exceptions.UserError(_("Invalid license file. Please upload a valid JSON file."))
                
        if not key:
            raise exceptions.UserError(_("Please provide a license key or upload a license file."))
            
        license_obj = self.env['license.management'].search([('license_key', '=', key)], limit=1)
        
        if not license_obj:
            if not license_data:
                raise exceptions.UserError(_("License key not found in the system. Please upload the full license file for first-time activation."))
                
            # Create it from file
            from datetime import datetime
            license_obj = self.env['license.management'].create({
                'license_key': key,
                'customer_name': license_data.get('customer', 'Unknown'),
                'company_name': license_data.get('company', ''),
                'database_uuid': license_data.get('database_uuid', ''),
                'expiry_date': datetime.strptime(license_data.get('expiry', fields.Date.context_today(self).strftime('%Y-%m-%d')), '%Y-%m-%d').date(),
                'grace_period_days': int(license_data.get('grace_period', 15)),
                'max_activations': int(license_data.get('max_activations', 1)),
                'licensed_modules': license_data.get('modules', ''),
                'license_payload': json.dumps(license_data),
            })
            
        license_obj.action_activate()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('License Activated'),
                'message': _('The license has been successfully activated!'),
                'type': 'success',
                'sticky': False,
            }
        }
