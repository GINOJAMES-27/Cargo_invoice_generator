from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    openai_api_key = fields.Char(
        string='OpenAI API Key', 
        config_parameter='cargo_manual_invoicing.openai_api_key', 
        help='API key for the OpenAI GPT models to power the Voice Assistant'
    )

    gemini_api_key = fields.Char(
        string='Gemini API Key', 
        config_parameter='cargo_manual_invoicing.gemini_api_key', 
        help='API key for the Google Gemini models for text requests'
    )
