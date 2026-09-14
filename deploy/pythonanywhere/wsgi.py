"""
WSGI entrypoint for PythonAnywhere.

After creating the web app, paste this into the WSGI configuration file
(pythonanywhere.com → Web → your app → WSGI configuration).
Replace 'yourusername' with your PythonAnywhere username.
"""
import sys

path = "/home/yourusername/ai-model-router/src"
if path not in sys.path:
    sys.path.insert(0, path)

from ai_model_router.server import create_app  # noqa: E402

application = create_app()
