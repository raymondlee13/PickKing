"""
PickKing -- Local Web App
-----------------------------------------
Double-click launch.bat to start this and open it in your browser.
No installs beyond Python itself -- everything here is standard library
(openpyxl is optional, only needed for spreadsheet logging).

First-time setup: put your PropLine API key in config.json (same folder).

The app is split across a few small modules, this file just starts it:
  config.py          -- config.json load/create
  scoring.py          -- edge-grading math (pure, no network/IO)
  propline_api.py     -- PropLine API client + whole-slate scanning
  excel_logging.py    -- parlay logging to the tracking workbook
  views.py            -- HTML template rendering
  server.py           -- HTTP routing (the actual web server)
  templates/, static/ -- the frontend (HTML/CSS/JS)
"""

from server import main

if __name__ == "__main__":
    main()
