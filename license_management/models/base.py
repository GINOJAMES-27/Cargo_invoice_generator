from odoo import models, api, exceptions, _

class BaseModel(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        res = super().check_access_rights(operation, raise_exception=raise_exception)
        
        # We only care about blocking writes, creates, and unlinks
        if operation in ['read', 'export']:
            return res
            
        # Do not block superuser or admin (UID 2 usually, check config)
        if self.env.su:
            return res
            
        # Get the license status and mode directly from config parameters (cache hit)
        ICP = self.env['ir.config_parameter'].sudo()
        status = ICP.get_param('license.status', 'draft')
        mode = ICP.get_param('license.mode', 'block')
        admin_uid_str = ICP.get_param('license.admin_uid', '2')
        try:
            admin_uid = int(admin_uid_str)
        except ValueError:
            admin_uid = 2
            
        if self.env.user.id == admin_uid:
            return res
            
        # Allow specific models always
        if self._name in ['license.management', 'license.log', 'res.config.settings', 'ir.config_parameter', 'ir.cron', 'res.users', 'ir.module.module']:
            return res

        # If readonly mode is enabled and license is expired/suspended/invalid
        if mode == 'readonly' and status in ['expired', 'suspended', 'invalid']:
            if raise_exception:
                raise exceptions.AccessError(_('License expired. System is operating in read-only mode.'))
            return False
            
        return res
