import sys
import os

# Dynamically add the user's local site-packages so Odoo can find Shippo
local_packages = r'C:\Users\dell\AppData\Roaming\Python\Python312\site-packages'
if os.path.exists(local_packages) and local_packages not in sys.path:
    sys.path.append(local_packages)

from . import cargo_manual_invoice
from . import shippo_service
from . import res_config_settings
