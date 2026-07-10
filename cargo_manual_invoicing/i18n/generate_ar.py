import re

translations = {
    'Invoice Number': 'رقم الفاتورة',
    'Shipment Info': 'معلومات الشحنة',
    'Shipping Date': 'تاريخ الشحن',
    'Shipment Type': 'نوع الشحنة',
    'Status': 'الحالة',
    'Specify Status': 'تحديد الحالة',
    'User / Payment': 'المستخدم / الدفع',
    'Payment Mode': 'طريقة الدفع',
    'Parties Info': 'معلومات الأطراف',
    'Shipper Name': 'اسم الشاحن',
    'Origin': 'المنشأ',
    'Mobile': 'الجوال',
    'Tel': 'الهاتف',
    'VAT No': 'الرقم الضريبي',
    'Company': 'الشركة',
    'Email': 'البريد الإلكتروني',
    'Address': 'العنوان',
    'Receiver Name': 'اسم المستلم',
    'Country': 'الدولة',
    'Cargo & Financials': 'الشحن والمالية',
    'Weight (kg)': 'الوزن (كجم)',
    'Pieces': 'القطع',
    'Delivery Partner': 'شريك التوصيل',
    'Specify Partner': 'تحديد الشريك',
    'Airway Bill': 'بوليصة الشحن',
    'Product Info': 'معلومات المنتج',
    'Special Info': 'معلومات خاصة',
    'Net Amount (SAR)': 'المبلغ الصافي (ريال)',
    'VAT 15%': 'ضريبة القيمة المضافة 15%',
    'Extra Charge': 'رسوم إضافية',
    'Gross Total (SAR)': 'الإجمالي (ريال)',
    'Domestic': 'محلي',
    'International': 'دولي',
    'Cash': 'نقداً',
    'Card': 'بطاقة',
    'Order Placed': 'تم الطلب',
    'In Transit': 'في الطريق',
    'Out for Delivery': 'في الطريق للتوصيل',
    'Delivered': 'تم التوصيل',
    'Cancelled': 'ملغي',
    'Agent Name': 'اسم الوكيل',
    'Cargo Invoicing': 'فواتير الشحن',
    'Operations': 'العمليات',
    'Reporting': 'التقارير',
    'Cargo Invoices': 'فواتير الشحن',
    'Cargo Invoice': 'فاتورة الشحن',
    'Print Invoice': 'طباعة الفاتورة',
    'Send Email': 'إرسال بريد',
    'Send via WhatsApp': 'إرسال عبر واتس اب'
}

with open(r'd:\odoo-custom-addons\cargo_manual_invoicing\i18n\template.pot', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace header Language
content = content.replace('Language-Team: \\n', 'Language-Team: Arabic\\nLanguage: ar\\n')
content = content.replace('Content-Transfer-Encoding: \\n', 'Content-Transfer-Encoding: 8bit\\n')
content = content.replace('Plural-Forms: \\n', 'Plural-Forms: nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 && n%100<=99 ? 4 : 5;\\n')

# Iterate and replace
for eng, ar in translations.items():
    pattern = r'(msgid "' + re.escape(eng) + r'"\nmsgstr )""'
    content = re.sub(pattern, r'\g<1>"' + ar + '"', content)

with open(r'd:\odoo-custom-addons\cargo_manual_invoicing\i18n\ar.po', 'w', encoding='utf-8') as f:
    f.write(content)

print('Translated ar.po generated!')
