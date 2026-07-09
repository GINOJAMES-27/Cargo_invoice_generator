from odoo import models, api, exceptions, _

class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def set_param(self, key, value):
        # We allow superuser/system to change it (which is what the python code uses due to .sudo())
        # But if it's a regular user trying to write to license.* keys manually through UI or RPC, block it
        if key.startswith('license.') and not self.env.su:
            raise exceptions.AccessError(_('You cannot modify license parameters manually.'))
        return super().set_param(key, value)

    def write(self, vals):
        if not self.env.su:
            for rec in self:
                if rec.key and rec.key.startswith('license.'):
                    raise exceptions.AccessError(_('You cannot modify license parameters manually.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            for rec in self:
                if rec.key and rec.key.startswith('license.'):
                    raise exceptions.AccessError(_('You cannot delete license parameters manually.'))
        return super().unlink()
