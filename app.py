"""
DockDash - Container Management Dashboard
Main application entry point
"""
from config import create_app

app = create_app()

if __name__ == '__main__':
    # Direct execution is development-only. Production is served by Gunicorn.
    app.run(host='127.0.0.1', port=5000, debug=False)
