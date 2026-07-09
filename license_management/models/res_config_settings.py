from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    license_key = fields.Char(string='License Key', config_parameter='license.key', readonly=True)
    license_expiry = fields.Char(string='License Expiry', config_parameter='license.expiry', readonly=True)
    license_status = fields.Char(string='License Status', config_parameter='license.status', readonly=True)
    license_grace_period = fields.Integer(string='Grace Period', config_parameter='license.grace_period')
    license_server = fields.Char(string='License Server URL', config_parameter='license.server')
    license_online_validation = fields.Boolean(string='Online Validation', config_parameter='license.online_validation')
    license_mode = fields.Selection([
        ('block', 'Block Login'),
        ('readonly', 'Read-Only Mode')
    ], string='Expiration Mode', config_parameter='license.mode', default='block')
    
    license_admin_uid = fields.Many2one('res.users', string='Admin User', config_parameter='license.admin_uid')
    
    license_vendor_name = fields.Char(string='Vendor Name', config_parameter='license.vendor_name', default='Hudson Software Solutions')
    license_vendor_email = fields.Char(string='Vendor Email', config_parameter='license.vendor_email', default='support@hudsonsoftwares.com')
    license_vendor_phone = fields.Char(string='Vendor Phone', config_parameter='license.vendor_phone', default='+91 9908223334')
    
    database_uuid = fields.Char(string='Database UUID', config_parameter='database.uuid', readonly=True)
    
    def action_activate_license(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activate License',
            'res_model': 'license.activate.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_renew_license(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Renew License',
            'res_model': 'license.renew.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_verify_license(self):
        active_license = self.env['license.management'].search([('license_key', '=', self.license_key)], limit=1)
        if active_license:
            active_license.action_verify()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
