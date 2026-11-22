"""Lokalny start/stop aplikacji. START_AED.cmd uruchamia ten plik w .venv."""
import argparse
import json
import hashlib
import ipaddress
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8000/"
LOG_DIR = ROOT / "backend" / "logs"
PID_FILE = LOG_DIR / "aed_server.pid"
WORKSPACE_ID = hashlib.sha256(os.path.normcase(str(ROOT)).encode("utf-8")).hexdigest()[:16]


def health():
    try:
        with urllib.request.urlopen(URL + "api/health", timeout=2) as response:
            data = json.load(response)
        return data if data.get("service") == "otwarte-aed" and data.get("ready") is True else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def port_occupied():
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", 8000)) == 0


def lan_address():
    """Adres interfejsu domyslnej trasy; UDP connect wybiera trase bez wysylania danych."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 80))
            address = connection.getsockname()[0]
            if not ipaddress.ip_address(address).is_loopback:
                return address
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = ipaddress.ip_address(info[4][0])
            if not address.is_loopback and not address.is_link_local:
                return str(address)
    except OSError:
        pass
    return None


def start(open_browser=True, lan=False):
    listen_host = "0.0.0.0" if lan else "127.0.0.1"
    current = health()
    if current:
        workspace_id = current.get("workspace_id")
        legacy_owned = (workspace_id is None and PID_FILE.exists() and
                        PID_FILE.read_text(encoding="ascii").strip() == str(current["pid"]))
        if workspace_id != WORKSPACE_ID and not legacy_owned:
            raise RuntimeError("Port 8000 obsluguje Otwarte AED z innego folderu. Zatrzymaj tamten serwer jego plikiem STOP_AED.cmd i uruchom ten starter ponownie.")
        if current.get("listen_host", "127.0.0.1") != listen_host:
            print("Przelaczanie trybu sieciowego serwera...", flush=True)
            stop()
            deadline = time.monotonic() + 10
            while port_occupied() and time.monotonic() < deadline:
                time.sleep(0.2)
            current = None
    if current is None:
        if port_occupied():
            raise RuntimeError("Port 8000 jest zajety przez inna usluge lub serwer jeszcze startuje. Sprobuj ponownie za chwile.")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.setdefault("AED_OFFLINE", "true")
        env["AED_LISTEN_HOST"] = listen_host
        options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        with (LOG_DIR / "server.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", listen_host, "--port", "8000"],
                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **options,
            )
        print("Uruchamianie Otwarte AED...", flush=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            current = health()
            if current:
                PID_FILE.write_text(str(current["pid"]), encoding="ascii")
                break
            if process.poll() is not None:
                raise RuntimeError("Serwer nie wystartowal. Szczegoly: backend/logs/server.log")
            time.sleep(0.4)
        else:
            raise RuntimeError("Przekroczono czas startu. Sprawdz backend/logs/server.log i sprobuj ponownie.")
    print(f"Gotowe: {URL} ({current['records']} rekordow).", flush=True)
    print(f"Folder projektu: {ROOT}", flush=True)
    if lan:
        address = lan_address()
        if address:
            phone_url = f"http://{address}:8000/"
            print(f"ADRES NA TELEFON: {phone_url}", flush=True)
            print("Telefon i komputer musza byc w tej samej sieci. Komputer musi pozostac wlaczony.", flush=True)
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            (LOG_DIR / "telefon_url.txt").write_text(phone_url + "\n", encoding="utf-8")
        else:
            print("Nie wykryto adresu sieci. Sprawdz IPv4 poleceniem ipconfig.", flush=True)
    if open_browser:
        webbrowser.open(URL)
    return current


def stop():
    current = health()
    if not current:
        print("Otwarte AED nie dziala pod adresem " + URL)
        return
    if current.get("workspace_id") not in (None, WORKSPACE_ID):
        raise RuntimeError("Nie zatrzymano serwera: dziala on z innego folderu projektu. Uzyj jego pliku STOP_AED.cmd.")
    pid_matches = PID_FILE.exists() and PID_FILE.read_text(encoding="ascii").strip() == str(current["pid"])
    if not pid_matches and current.get("workspace_id") != WORKSPACE_ID:
        raise RuntimeError("Nie zatrzymano serwera: nie zostal uruchomiony tym launcherem. Zamknij jego oryginalny terminal.")
    os.kill(current["pid"], signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print("Zatrzymano Otwarte AED.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Nie otwieraj przegladarki.")
    parser.add_argument("--stop", action="store_true", help="Zatrzymaj serwer uruchomiony launcherem.")
    parser.add_argument("--lan", action="store_true", help="Udostepnij aplikacje w lokalnej sieci do testu telefonu.")
    args = parser.parse_args()
    try:
        stop() if args.stop else start(open_browser=not args.no_browser, lan=args.lan)
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f"BLAD: {exc}\n")


if __name__ == "__main__":
    main()
