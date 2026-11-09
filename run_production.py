"""
Use this instead of `python app.py` for a real exam session with more
than a handful of students. Flask's built-in dev server (what app.py
runs) prints its own warning that it isn't meant for this — waitress is
a real production WSGI server, still just as easy to run locally.

Usage:
    python run_production.py

Then give students the same LAN address you'd normally use
(http://<your-ip>:5000), nothing else changes.
"""
from waitress import serve
from app import create_app

app = create_app()

if __name__ == "__main__":
    print("Starting production server on http://0.0.0.0:5000 ...")
    print("Give students this machine's LAN IP address, port 5000.")
    serve(app, host="0.0.0.0", port=5000, threads=16)
