# Quickstart: 001 Settings Tab

1. `python app.py` → open `http://<device>:8050`.
2. Click the **Settings** tab → create the admin password (first time only).
3. Change e.g. the serial port → **Save** → measurements resume within one poll cycle.
4. Set **Protection** to "Whole app" → log out → dashboard now asks for the password.
5. Forgot the password: on the device run `python settings.py reset-password`.

Verification: `python test_app.py` (also run by CI).
