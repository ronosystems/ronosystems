# ============================================
# M-PESA — shared constants
# ============================================

ENVIRONMENT_CHOICES = (
    ('sandbox',    'Sandbox'),
    ('production', 'Production'),
)

SHORTCODE_TYPES = (
    ('paybill', 'Paybill'),
    ('till',    'Buy Goods (Till)'),
)

TRANSACTION_STATUS = (
    ('pending',   'Pending'),
    ('success',   'Success'),
    ('failed',    'Failed'),
    ('cancelled', 'Cancelled'),
    ('timeout',   'Timeout'),
)

# Daraja base URLs
DARAJA_SANDBOX_BASE    = 'https://sandbox.safaricom.co.ke'
DARAJA_PRODUCTION_BASE = 'https://api.safaricom.co.ke'

# Daraja endpoint paths
DARAJA_OAUTH_PATH  = '/oauth/v1/generate?grant_type=client_credentials'
DARAJA_STK_PATH    = '/mpesa/stkpush/v1/processrequest'
DARAJA_QUERY_PATH  = '/mpesa/stkpushquery/v1/query'

# Payment method name used in Sale.payment_method
SALE_PAYMENT_METHOD = 'm-pesa'