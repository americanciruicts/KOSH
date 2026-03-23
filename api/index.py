import sys
import os

# Add parent directory to path so we can import app.py
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

# Change working directory to parent so Flask finds templates/static
os.chdir(parent_dir)

# Set environment variables for Vercel (Neon cloud database)
os.environ.setdefault('NEON_DATABASE_URL', 'postgresql://neondb_owner:npg_rDiAmTp5bv9J@ep-late-wildflower-ad4p3dpq.c-2.us-east-1.aws.neon.tech/kosh?sslmode=require')
os.environ.setdefault('SSO_SECRET_KEY', 'D4T_WY71xsF0_UB4QjIzlAjVlj-M5kEG0jsIws6isvPn5NNK4s5-_E_--WI6C6YT6jkerJ3EHncBEuG3tK5Rlg')

from app import app

# Fix template and static paths for Vercel environment
app.template_folder = os.path.join(parent_dir, 'templates')
app.static_folder = os.path.join(parent_dir, 'static')

# Vercel expects the WSGI app
app = app
