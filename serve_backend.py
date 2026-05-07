import os, sys
os.chdir("/Users/gregpolinger/sauvage-site/backend")
sys.path.insert(0, "/Users/gregpolinger/sauvage-site/backend")
os.environ.setdefault("PORT", "5001")

from app import app
app.run(port=int(os.environ.get("PORT", 5001)))
