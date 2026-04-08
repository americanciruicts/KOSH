import sys
import os

# Add parent directory to path so we can import app.py
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

# Change working directory to parent so Flask finds templates/static
os.chdir(parent_dir)

os.environ.setdefault('SSO_SECRET_KEY', 'D4T_WY71xsF0_UB4QjIzlAjVlj-M5kEG0jsIws6isvPn5NNK4s5-_E_--WI6C6YT6jkerJ3EHncBEuG3tK5Rlg')

from app import app

# Fix template and static paths for Vercel environment
app.template_folder = os.path.join(parent_dir, 'templates')
app.static_folder = os.path.join(parent_dir, 'static')

# Pass tunnel backend URL to templates (for Vercel frontend → local backend)
app.config['KOSH_BACKEND_URL'] = os.environ.get('KOSH_BACKEND_URL', '')

# Vercel expects the WSGI app
app = app
