import sys
import os

# Ensure the root project directory is in Python's search path on Vercel
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from run import app

# Vercel Serverless Function entry point
if __name__ == "__main__":
    app.run()
