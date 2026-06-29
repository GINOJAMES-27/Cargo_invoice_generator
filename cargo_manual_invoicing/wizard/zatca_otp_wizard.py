from odoo import models, fields, api

class ZatcaOtpWizard(models.TransientModel):
    _name = 'zatca.otp.wizard'
    _description = 'ZATCA OTP Entry Wizard'

    otp = fields.Char(string='One-Time Password (OTP)', required=True, help="Enter the OTP from the Fatoora portal.")

    def action_submit_otp(self):
        self.ensure_one()
        config = self.env['res.config.settings'].create({})
        return config.with_context(zatca_otp=self.otp).action_zatca_get_compliance_csid_with_otp()
