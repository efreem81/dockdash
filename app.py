"""
DockDash - Container Management Dashboard
Main application entry point
"""
from config import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
