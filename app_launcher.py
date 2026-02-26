# -*- coding: utf-8 -*-
import os
import socket
import threading
import time
import webbrowser

from main import app


def open_browser_when_ready(host: str, port: int):
    if os.environ.get('BAVA_NO_OPEN_BROWSER', '').lower() in ('1', 'true', 'yes'):
        return
    for _ in range(120):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                webbrowser.open(f'http://{host}:{port}/')
                return
        time.sleep(0.25)


def main():
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5252'))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    threading.Thread(target=open_browser_when_ready, args=(host, port), daemon=True).start()
    app.run(debug=debug, host=host, port=port)


if __name__ == '__main__':
    main()
