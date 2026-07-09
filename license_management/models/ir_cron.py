from odoo import models, api, exceptions, _

class IrCron(models.Model):
    _inherit = 'ir.cron'

    def unlink(self):
        for rec in self:
            if rec.cron_name == 'License: Daily Status Check' and not self.env.su:
                raise exceptions.AccessError(_('You cannot delete the core license checking cron job.'))
        return super().unlink()
