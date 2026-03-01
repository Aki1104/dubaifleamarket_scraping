""" 
=============================================================================
🚀 PRODUCTION SERVER — Waitress (pure Python, no worker timeouts)
=============================================================================
Simple entry point that starts waitress FIRST, then kicks off background
work.  Waitress binds the port immediately — Render sees it alive.
=============================================================================
"""

import os
import sys


def main():
    port = int(os.environ.get('PORT', 10000))
    print(f"[SERVER] Starting on 0.0.0.0:{port} ...")
    sys.stdout.flush()

    # Import app AFTER printing — so if import hangs, we at least see the log
    from app import app

    print(f"[SERVER] App imported — serving on http://0.0.0.0:{port}")
    sys.stdout.flush()

    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=4)
    except ImportError:
        print("[SERVER] waitress not installed — using Flask dev server")
        sys.stdout.flush()
        app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
