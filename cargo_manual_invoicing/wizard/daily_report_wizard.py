from odoo import api, fields, models
from datetime import date, timedelta

class CargoDailyReportWizard(models.TransientModel):
    _name = 'cargo.daily.report.wizard'
    _description = 'Daily Collection Report Wizard'

    date_from = fields.Date(string='Date From', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.context_today)
    agent_filter = fields.Many2many('res.users', string='Filter by Agent')
    paymode_filter = fields.Selection([
        ('all', 'All Payment Modes'),
        ('cash', 'Cash Only'),
        ('card', 'Card Only'),
        ('company', 'Company Only')
    ], string='Payment Mode', default='all')
    report_type = fields.Selection([
        ('summary', 'Summary Report'),
        ('detailed', 'Detailed Report')
    ], string='Report Type', default='summary')

    def action_generate_report(self):
        self.ensure_one()
        
        # Build domain
        domain = [
            ('shipping_date', '>=', self.date_from),
            ('shipping_date', '<=', self.date_to),
            ('status', '!=', 'CANCELLED')
        ]
        
        if self.agent_filter:
            agent_names = self.agent_filter.mapped('name')
            domain.append(('agent_name', 'in', agent_names))
            
        if self.paymode_filter != 'all':
            domain.append(('paymode', '=', self.paymode_filter))
            
        data = {
            'form': self.read()[0],
            'domain': domain
        }
        
        return self.env.ref('cargo_manual_invoicing.action_report_daily_collection').report_action(self, data=data)

    def _reopen_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_set_today(self):
        self.date_from = fields.Date.context_today(self)
        self.date_to = fields.Date.context_today(self)
        return self._reopen_wizard()

    def action_set_yesterday(self):
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        self.date_from = yesterday
        self.date_to = yesterday
        return self._reopen_wizard()

    def action_set_this_week(self):
        today = fields.Date.context_today(self)
        start_of_week = today - timedelta(days=today.weekday())
        self.date_from = start_of_week
        self.date_to = today
        return self._reopen_wizard()

    def action_set_this_month(self):
        today = fields.Date.context_today(self)
        self.date_from = today.replace(day=1)
        self.date_to = today
        return self._reopen_wizard()
