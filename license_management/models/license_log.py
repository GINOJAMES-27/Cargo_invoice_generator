from odoo import models, fields

class LicenseLog(models.Model):
    _name = 'license.log'
    _description = 'License Activity Log'
    _order = 'timestamp desc, id desc'

    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now, required=True, readonly=True)
    event_type = fields.Selection([
        ('activation', 'Activation'),
        ('renewal', 'Renewal'),
        ('expiry', 'Expiry'),
        ('login_blocked', 'Login Blocked'),
        ('verification', 'Verification'),
        ('tampering', 'Tampering Detected'),
        ('admin_override', 'Admin Override')
    ], string='Event Type', required=True, readonly=True)
    
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    description = fields.Text(string='Description', readonly=True)
    ip_address = fields.Char(string='IP Address', readonly=True)
    license_id = fields.Many2one('license.management', string='License', readonly=True, ondelete='cascade')
