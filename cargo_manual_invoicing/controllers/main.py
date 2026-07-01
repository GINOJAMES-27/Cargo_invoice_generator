from odoo import http
# pyrefly: ignore [missing-import]
from odoo.http import request

class CargoInvoiceController(http.Controller):
    
    @http.route(['/cargo/invoice/pdf/<int:invoice_id>/<string:token>'], type='http', auth="public", website=True)
    def download_invoice_pdf(self, invoice_id, token, **kwargs):
        # Find the invoice with sudo to bypass access rules for public users
        invoice = request.env['cargo.manual.invoice'].sudo().browse(invoice_id)
        
        # Verify existence and token matching
        if not invoice.exists() or invoice.access_token != token:
            return request.not_found()
            
        # Generate the PDF report
        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'cargo_manual_invoicing.report_cargo_manual_invoice', [invoice.id]
        )
        
        # Prepare response headers for file download
        filename = f"Invoice_{invoice.invoice_number}.pdf"
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', f'attachment; filename="{filename}"')
        ]
        
        return request.make_response(pdf, headers=pdfhttpheaders)
