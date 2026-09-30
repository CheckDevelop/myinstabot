import json
import os
import time
import traceback
import random
from datetime import datetime, timezone



# ============================================================
# SERVER / DEPENDENCY BOOTSTRAP
# ============================================================

import sys
import platform
import subprocess
import urllib.request
import urllib.parse
import zipfile
import tarfile
import tempfile
import shutil
import socket
import stat
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _ensure_python_package(import_name, pip_name):
    """Install a missing Python package before importing it."""
    try:
        __import__(import_name)
        return
    except ImportError:
        pass

    print(f"Python package '{pip_name}' is missing. Installing...")

    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        pip_name
    ])

    __import__(import_name)


_ensure_python_package("instagrapi", "instagrapi")

from instagrapi import Client
from database import init_db, load_document, save_document


# ============================================================
# PROJECT / XRAY PATHS
# ============================================================

XRAY_DIR = os.path.join(BASE_DIR, "xray")
os.makedirs(XRAY_DIR, exist_ok=True)

if platform.system() == "Windows":
    XRAY_BINARY_PATH = os.path.join(XRAY_DIR, "xray.exe")
else:
    XRAY_BINARY_PATH = os.path.join(XRAY_DIR, "xray")

XRAY_CONFIG_FILE = os.path.join(XRAY_DIR, "xray_config.json")
XRAY_LOG_FILE = os.path.join(XRAY_DIR, "xray.log")
VLESS_CONFIG_FILE = os.path.join(BASE_DIR, "vless_config.txt")

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 10808

XRAY_PROCESS = None


def project_path(filename):
    return os.path.join(BASE_DIR, filename)


def _xray_asset_name():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        if machine in ("amd64", "x86_64", "x64"):
            return "Xray-windows-64.zip"
        if machine in ("x86", "i386", "i686"):
            return "Xray-windows-32.zip"
        raise RuntimeError(f"Unsupported Windows architecture: {machine}")

    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "Xray-linux-64.zip"
        if machine in ("aarch64", "arm64"):
            return "Xray-linux-arm64-v8a.zip"
        if machine.startswith("armv7") or machine.startswith("armv6"):
            return "Xray-linux-arm32-v7a.zip"
        raise RuntimeError(f"Unsupported Linux architecture: {machine}")

    if system == "darwin":
        if machine in ("x86_64", "amd64"):
            return "Xray-macos-64.zip"
        if machine in ("arm64", "aarch64"):
            return "Xray-macos-arm64-v8a.zip"
        raise RuntimeError(f"Unsupported macOS architecture: {machine}")

    raise RuntimeError(f"Unsupported operating system: {platform.system()}")


def check_xray_installed():
    return (
        os.path.isfile(XRAY_BINARY_PATH)
        and os.access(XRAY_BINARY_PATH, os.X_OK if platform.system() != "Windows" else os.F_OK)
    )


def _get_latest_xray_download_url():
    api_url = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"

    request = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "XrayBootstrap/1.0",
            "Accept": "application/vnd.github+json"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))

    asset_name = _xray_asset_name()

    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return asset.get("browser_download_url"), release.get("tag_name")

    available = [
        asset.get("name")
        for asset in release.get("assets", [])
    ]

    raise RuntimeError(
        f"Could not find Xray asset '{asset_name}'. "
        f"Release={release.get('tag_name')}, available={available}"
    )


def download_xray():
    """Download the official Xray release into ./xray/."""
    os.makedirs(XRAY_DIR, exist_ok=True)

    url, version = _get_latest_xray_download_url()

    print()
    print("=" * 70)
    print("XRAY INSTALLATION")
    print("=" * 70)
    print(f"OS: {platform.system()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Version: {version}")
    print(f"Destination: {XRAY_BINARY_PATH}")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="xray_download_") as temp_dir:
        archive_path = os.path.join(
            temp_dir,
            os.path.basename(urllib.parse.urlparse(url).path)
        )

        print("Downloading Xray...")
        urllib.request.urlretrieve(url, archive_path)

        extract_dir = os.path.join(temp_dir, "extract")
        os.makedirs(extract_dir, exist_ok=True)

        if archive_path.lower().endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_dir)
        elif archive_path.lower().endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)
        else:
            raise RuntimeError(f"Unsupported Xray archive: {archive_path}")

        candidates = []

        for root, _, files in os.walk(extract_dir):
            for name in files:
                if name.lower() in ("xray", "xray.exe"):
                    candidates.append(os.path.join(root, name))

        if not candidates:
            raise RuntimeError("Xray executable was not found after extraction.")

        source_binary = candidates[0]

        if os.path.exists(XRAY_BINARY_PATH):
            try:
                os.remove(XRAY_BINARY_PATH)
            except OSError as e:
                raise RuntimeError(
                    f"Cannot replace existing Xray binary: {e}"
                ) from e

        shutil.copy2(source_binary, XRAY_BINARY_PATH)

    if platform.system() != "Windows":
        current_mode = os.stat(XRAY_BINARY_PATH).st_mode
        os.chmod(
            XRAY_BINARY_PATH,
            current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )

    if not check_xray_installed():
        raise RuntimeError(
            f"Xray installation failed: {XRAY_BINARY_PATH}"
        )

    print("Xray installed successfully.")
    return XRAY_BINARY_PATH


def ensure_xray():
    if check_xray_installed():
        print(f"Xray found: {XRAY_BINARY_PATH}")
        return XRAY_BINARY_PATH

    print("Xray not found. Installing automatically...")
    return download_xray()


def parse_vless_url(vless_url):
    """
    Parse a VLESS URL.

    Supported examples:
      vless://UUID@host:443?security=tls&type=ws&path=%2Fws&host=example.com&sni=example.com
      vless://UUID@host:443?security=tls&type=tcp&sni=example.com
    """
    vless_url = vless_url.strip()

    if not vless_url.lower().startswith("vless://"):
        raise ValueError("VLESS URL must start with vless://")

    parsed = urllib.parse.urlparse(vless_url)

    if not parsed.hostname:
        raise ValueError("VLESS server/host is missing.")

    if not parsed.username:
        raise ValueError("VLESS UUID is missing.")

    query = urllib.parse.parse_qs(parsed.query)

    def q(name, default=""):
        values = query.get(name, [])
        return values[0] if values else default

    security = q("security", "none").lower()
    transport = q("type", "tcp").lower()

    server = parsed.hostname
    port = parsed.port or 443
    uuid_value = urllib.parse.unquote(parsed.username)

    sni = q("sni", "")
    host = q("host", "")
    path = q("path", "/")
    flow = q("flow", "")

    # VLESS Reality parameters.
    # Standard share links use pbk / sid / fp. Some providers may use
    # publicKey / shortId / fingerprint instead, so both forms are accepted.
    public_key = q("pbk", "") or q("publicKey", "")
    short_id = q("sid", "") or q("shortId", "")
    fingerprint = q("fp", "") or q("fingerprint", "")

    if not sni and security in ("tls", "xtls", "reality"):
        sni = host or server

    return {
        "server": server,
        "port": port,
        "uuid": uuid_value,
        "security": security,
        "transport": transport,
        "path": path,
        "host": host,
        "sni": sni,
        "flow": flow,
        "public_key": public_key,
        "short_id": short_id,
        "fingerprint": fingerprint
    }


def build_xray_config(vless):
    stream_settings = {}

    transport = vless["transport"]

    if transport == "ws":
        stream_settings["network"] = "ws"
        stream_settings["wsSettings"] = {
            "path": vless["path"] or "/"
        }

        if vless["host"]:
            stream_settings["wsSettings"]["headers"] = {
                "Host": vless["host"]
            }

    elif transport in ("tcp", "http"):
        stream_settings["network"] = "tcp"

    else:
        raise ValueError(
            f"Unsupported VLESS transport type: {transport}"
        )

    security = vless["security"]

    if security == "reality":
        if not vless["public_key"]:
            raise ValueError(
                "VLESS Reality requires pbk (public key)."
            )

        stream_settings["security"] = "reality"
        stream_settings["realitySettings"] = {
            "show": False,
            "serverName": vless["sni"] or vless["server"],
            "fingerprint": vless["fingerprint"] or "chrome",
            "publicKey": vless["public_key"],
            "shortId": vless["short_id"]
        }

    elif security in ("tls", "xtls"):
        stream_settings["security"] = "tls"
        stream_settings["tlsSettings"] = {
            "serverName": vless["sni"] or vless["server"],
            "allowInsecure": False
        }

    else:
        stream_settings["security"] = "none"

    user = {
        "id": vless["uuid"],
        "encryption": "none"
    }

    if vless["flow"]:
        user["flow"] = vless["flow"]

    return {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "listen": PROXY_HOST,
                "port": PROXY_PORT,
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                }
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": vless["server"],
                            "port": vless["port"],
                            "users": [user]
                        }
                    ]
                },
                "streamSettings": stream_settings,
                "tag": "proxy"
            },
            {
                "protocol": "freedom",
                "tag": "direct"
            }
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "ip": [
                        "geoip:private"
                    ],
                    "outboundTag": "direct"
                }
            ]
        }
    }


def load_vless_url():
    """
    Server-friendly order:
      1. VLESS_URL environment variable
      2. vless_config.txt
      3. interactive input as a local fallback
    """
    env_value = os.environ.get("VLESS_URL", "").strip()

    if env_value:
        return env_value

    if os.path.isfile(VLESS_CONFIG_FILE):
        with open(
            VLESS_CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            value = f.read().strip()

        if value:
            return value

    if not sys.stdin.isatty():
        raise RuntimeError(
            "No VLESS URL found. Set VLESS_URL or create "
            f"{VLESS_CONFIG_FILE}."
        )

    value = input("Enter VLESS URL: ").strip()

    if not value:
        raise ValueError("VLESS URL cannot be empty.")

    return value


def _test_local_port(host, port):
    try:
        with socket.create_connection(
            (host, port),
            timeout=1.0
        ):
            return True
    except OSError:
        return False


def _wait_for_xray_port(timeout=15):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if XRAY_PROCESS is not None and XRAY_PROCESS.poll() is not None:
            return False

        if _test_local_port(
            PROXY_HOST,
            PROXY_PORT
        ):
            return True

        time.sleep(0.25)

    return False


def start_xray_proxy():
    global XRAY_PROCESS

    ensure_xray()

    vless_url = load_vless_url()
    vless = parse_vless_url(vless_url)
    config = build_xray_config(vless)

    os.makedirs(
        XRAY_DIR,
        exist_ok=True
    )

    save_json(
        XRAY_CONFIG_FILE,
        config
    )

    # Stop a stale process started by this script.
    if XRAY_PROCESS is not None:
        stop_xray_proxy()

    log_handle = open(
        XRAY_LOG_FILE,
        "a",
        encoding="utf-8"
    )

    print()
    print("=" * 70)
    print("STARTING XRAY")
    print("=" * 70)
    print(f"Binary: {XRAY_BINARY_PATH}")
    print(f"Config: {XRAY_CONFIG_FILE}")
    print(f"SOCKS5: {PROXY_HOST}:{PROXY_PORT}")
    print("=" * 70)

    creationflags = 0

    if platform.system() == "Windows":
        creationflags = getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0
        )

    XRAY_PROCESS = subprocess.Popen(
        [
            XRAY_BINARY_PATH,
            "run",
            "-config",
            XRAY_CONFIG_FILE
        ],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags
    )

    if not _wait_for_xray_port(15):
        return_code = XRAY_PROCESS.poll()

        try:
            log_handle.close()
        except Exception:
            pass

        XRAY_PROCESS = None

        raise RuntimeError(
            "Xray did not start correctly. "
            f"Return code: {return_code}. "
            f"Check log: {XRAY_LOG_FILE}"
        )

    try:
        log_handle.close()
    except Exception:
        pass

    print("Xray SOCKS5 proxy is ready.")
    return True


def stop_xray_proxy():
    global XRAY_PROCESS

    if XRAY_PROCESS is None:
        return

    process = XRAY_PROCESS

    XRAY_PROCESS = None

    if process.poll() is not None:
        return

    print("\nStopping Xray...")

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    except Exception as e:
        print(f"WARNING: Could not stop Xray cleanly: {e}")


def configure_client_proxy(cl):
    proxy = f"socks5://{PROXY_HOST}:{PROXY_PORT}"

    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    os.environ["ALL_PROXY"] = proxy

    cl.set_proxy(proxy)

    return cl



# ============================================================
# SETTINGS
# ============================================================

SESSION_FILE = project_path("nima_instagram_session.json")

# On Render the filesystem is ephemeral, so the Instagram session is supplied
# through INSTAGRAM_SESSION and materialized only in /tmp. Local development
# continues to use the existing session file when the environment variable is absent.
def _prepare_session_file():
    session_value = os.environ.get("INSTAGRAM_SESSION", "").strip()
    if not session_value:
        return

    try:
        json.loads(session_value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "INSTAGRAM_SESSION must contain valid Instagram session JSON."
        ) from exc

    runtime_session = os.path.join(tempfile.gettempdir(), "nima_instagram_session.json")
    with open(runtime_session, "w", encoding="utf-8") as f:
        f.write(session_value)
        f.flush()
        os.fsync(f.fileno())

    globals()["SESSION_FILE"] = runtime_session


_prepare_session_file()

LOCATION_FILE = project_path("location_data.json")
POSTS_FILE = project_path("posts_data.json")

PRIVATE_USERS_FILE = project_path("private_users.json")
PUBLIC_USERS_FILE = project_path("public_users.json")

REQUEST_FOLLOW = project_path("request_follow.json")
REQUEST_LIKE = project_path("request_like.json")
REQUEST_STORY_SEEN = project_path("request_story_seen.json")
REQUEST_STORY_LIKE = project_path("request_story_like.json")
STATS_FILE = project_path("stats.json")
ACTIVITY_HISTORY_FILE = project_path("activity_history.json")

POST_COUNT = 3

FOLLOWING_LIMIT = 3000
FOLLOWER_LIMIT = 30

FOLLOW_COOLDOWN = 240

NEXT_LIKE_TIME = 80

last_follow_time = 0

# ============================================================
# ACTION BATCH COUNTERS
# ============================================================

# تعداد عملیات موفق قبل از Sleep
LIKE_BATCH_MIN = 20
LIKE_BATCH_MAX = 30

FOLLOW_BATCH_MIN = 5
FOLLOW_BATCH_MAX = 10

# Sleep بعد از رسیدن شمارنده به محدوده
ACTION_SLEEP_MIN = 15 * 60   # 15 minutes
ACTION_SLEEP_MAX = 30 * 60   # 30 minutes

action_counters = {
    "like": 0,
    "follow": 0,
}

action_limits = {
    "like": random.randint(LIKE_BATCH_MIN, LIKE_BATCH_MAX),
    "follow": random.randint(FOLLOW_BATCH_MIN, FOLLOW_BATCH_MAX),
}


def register_action(action_type):
    """
    شمارش Like / Follow موفق.
    وقتی شمارنده به حد تصادفی تعیین‌شده برسد،
    Sleep تصادفی 15 تا 30 دقیقه انجام می‌شود.
    """

    if action_type not in action_counters:
        return

    action_counters[action_type] += 1

    current = action_counters[action_type]
    limit = action_limits[action_type]

    print(
        f"\n{action_type.upper()} COUNTER: "
        f"{current}/{limit}"
    )

    if current < limit:
        return

    sleep_seconds = random.randint(
        ACTION_SLEEP_MIN,
        ACTION_SLEEP_MAX
    )

    print()
    print("=" * 70)
    print(f"{action_type.upper()} BATCH LIMIT REACHED")
    print("=" * 70)
    print(f"Counter: {current}/{limit}")
    print(f"Sleeping for {sleep_seconds / 60:.1f} minutes...")
    print("=" * 70)

    time.sleep(sleep_seconds)

    action_counters[action_type] = 0

    if action_type == "like":
        action_limits[action_type] = random.randint(
            LIKE_BATCH_MIN,
            LIKE_BATCH_MAX
        )
    else:
        action_limits[action_type] = random.randint(
            FOLLOW_BATCH_MIN,
            FOLLOW_BATCH_MAX
        )

    print()
    print(f"{action_type.upper()} batch reset.")
    print(f"New limit: {action_limits[action_type]}")



# ============================================================
# CLIENT
# ============================================================

def create_client():

    cl = Client()

    if not os.path.exists(SESSION_FILE):

        raise FileNotFoundError(
            f"Session file not found: {SESSION_FILE}"
        )

    configure_client_proxy(cl)

    # فقط Session ذخیره‌شده استفاده می‌شود.
    # Login مجدد انجام نمی‌شود.

    cl.load_settings(
        SESSION_FILE
    )

    return cl


# ============================================================
# SERIALIZE
# ============================================================

def serialize_value(value):
    """
    تبدیل آبجکت‌های instagrapi به ساختار قابل ذخیره در JSON.
    اطلاعات موجود در آبجکت حفظ می‌شود.
    """

    if value is None:
        return None

    # Primitive values
    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool
        )
    ):
        return value

    # List / Tuple / Set
    if isinstance(
        value,
        (
            list,
            tuple,
            set
        )
    ):
        return [
            serialize_value(item)
            for item in value
        ]

    # Dictionary
    if isinstance(value, dict):

        return {
            str(key): serialize_value(val)
            for key, val in value.items()
        }

    # Pydantic v2
    if hasattr(
        value,
        "model_dump"
    ):

        try:

            return serialize_value(
                value.model_dump(
                    mode="json"
                )
            )

        except Exception:
            pass

    # Pydantic v1
    if hasattr(
        value,
        "dict"
    ):

        try:

            return serialize_value(
                value.dict()
            )

        except Exception:
            pass

    # Object __dict__
    if hasattr(
        value,
        "__dict__"
    ):

        try:

            return {
                str(key): serialize_value(val)
                for key, val in vars(value).items()
            }

        except Exception:
            pass

    # Final fallback
    try:
        return str(value)

    except Exception:
        return repr(value)


# ============================================================
# DELAY
# ============================================================

def wait_operation():

    time.sleep(
        random.randint(20, 30)
    )


def wait_account():

    time.sleep(
        random.randint(30, 70)
    )


def wait_in():

    time.sleep(
        random.randint(20, 30)
    )


# ============================================================
# JSON / DATABASE STATE
# ============================================================

STATE_DOCUMENTS = {
    "location_data.json",
    "posts_data.json",
    "private_users.json",
    "public_users.json",
    "request_follow.json",
    "request_like.json",
    "request_story_seen.json",
    "request_story_like.json",
    "stats.json",
    "activity_history.json",
}

DATABASE_ENABLED = bool(os.environ.get("DATABASE_URL", "").strip())

if DATABASE_ENABLED:
    init_db()


def load_json(
    filename,
    default
):
    """Load persistent bot state from PostgreSQL, with local-file migration fallback."""
    basename = os.path.basename(filename)

    if basename in STATE_DOCUMENTS and DATABASE_ENABLED:
        data = load_document(basename, None)
        if data is not None:
            return data

        # One-time migration from an existing local JSON file.
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                save_document(basename, data)
                return data
            except (json.JSONDecodeError, OSError):
                return default

        return default

    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(
    filename,
    data
):
    """Persist bot state in PostgreSQL; non-state JSON remains file-backed."""
    basename = os.path.basename(filename)

    if basename in STATE_DOCUMENTS and DATABASE_ENABLED:
        save_document(basename, data)
        return

    temp_file = filename + ".tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_file, filename)


# ============================================================
# GLOBAL STATS
# ============================================================

def load_stats():

    data = load_json(
        STATS_FILE,
        {
            "follow": 0,
            "like (Story and Post)": 0,
            "story_seen": 0,
            "processed_accounts": []
        }
    )

    if not isinstance(data, dict):
        data = {}

    if not isinstance(
        data.get("follow"),
        int
    ):
        data["follow"] = 0

    if not isinstance(
        data.get("like (Story and Post)"),
        int
    ):
        data["like (Story and Post)"] = 0

    if not isinstance(
        data.get("story_seen"),
        int
    ):
        data["story_seen"] = 0

    if not isinstance(
        data.get("processed_accounts"),
        list
    ):
        data["processed_accounts"] = []

    return data


def save_stats(stats):

    save_json(
        STATS_FILE,
        stats
    )


def increment_stat(
    stat_name,
    amount=1
):

    stats = load_stats()

    stats[stat_name] = (
        stats.get(stat_name, 0)
        + amount
    )

    save_stats(
        stats
    )


def mark_account_processed(
    user_id
):

    user_id = str(
        user_id
    )

    stats = load_stats()

    processed_accounts = stats.get(
        "processed_accounts",
        []
    )

    if user_id not in processed_accounts:

        processed_accounts.append(
            user_id
        )

        stats["processed_accounts"] = (
            processed_accounts
        )

        save_stats(
            stats
        )

        return True

    return False


def get_processed_accounts_count():

    stats = load_stats()

    return len(
        stats.get(
            "processed_accounts",
            []
        )
    )


def print_stats():

    stats = load_stats()

    print()
    print("=" * 70)
    print("GLOBAL STATS")
    print("=" * 70)

    print(
        f"Follow: "
        f"{stats.get('follow', 0)}"
    )

    print(
        f"like (Story and Post): "
        f"{stats.get('like (Story and Post)', 0)}"
    )

    print(
        f"Story Seen: "
        f"{stats.get('story_seen', 0)}"
    )

    print(
        f"Processed Accounts: "
        f"{len(stats.get('processed_accounts', []))}"
    )

    print("=" * 70)


# ============================================================
# ACTIVITY SESSION HISTORY
# ============================================================

def utc_now():
    """Return the current time in UTC/GMT."""

    return datetime.now(timezone.utc)


def format_gmt(dt):
    """Format a datetime as a readable GMT timestamp."""

    return dt.astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S GMT"
    )


def load_activity_history():
    """
    Load per-day / per-session activity history.

    Structure:

    {
        "2026-09-26": [
            {
                "session": 1,
                "start": "2026-09-26 11:00:00 GMT",
                "stop": "2026-09-26 13:00:00 GMT",
                "duration_seconds": 7200,
                "status": "completed",
                "follow": 18,
                "like (Story and Post)": 41,
                "story_seen": 63,
                "processed_accounts": 81
            }
        ]
    }

    Previous sessions are never overwritten. A new run is appended
    as a new session under the date on which that run started.
    """

    data = load_json(
        ACTIVITY_HISTORY_FILE,
        {}
    )

    if not isinstance(data, dict):
        return {}

    # Keep only the expected list structure for each date.
    cleaned = {}

    for date_key, sessions in data.items():

        if isinstance(sessions, list):
            cleaned[str(date_key)] = sessions

    return cleaned


def get_activity_stats_snapshot():
    """
    Return only the cumulative counters needed to calculate the
    statistics for the current Start -> Stop session.

    stats.json remains the global/cumulative statistics file.
    This function does not modify it.
    """

    stats = load_stats()

    return {
        "follow": int(
            stats.get("follow", 0)
        ),
        "like (Story and Post)": int(
            stats.get("like (Story and Post)", 0)
        ),
        "story_seen": int(
            stats.get("story_seen", 0)
        ),
        "processed_accounts": len(
            stats.get("processed_accounts", [])
        )
    }


def start_activity_session():
    """Start a new activity session and capture its initial counters."""

    start_dt = utc_now()
    date_key = start_dt.strftime("%Y-%m-%d")

    history = load_activity_history()
    sessions = history.get(
        date_key,
        []
    )

    session_number = len(sessions) + 1

    state = {
        "start_dt": start_dt,
        "date_key": date_key,
        "session": session_number,
        "start_stats": get_activity_stats_snapshot()
    }

    print()
    print("=" * 70)
    print("ACTIVITY SESSION STARTED")
    print("=" * 70)
    print(
        f"Date: {date_key}"
    )
    print(
        f"Session: {session_number}"
    )
    print(
        f"Start: {format_gmt(start_dt)}"
    )
    print(
        f"History file: {ACTIVITY_HISTORY_FILE}"
    )
    print("=" * 70)

    return state


def finish_activity_session(
    session_state,
    status="completed",
    error=None
):
    """
    Finish the current Start -> Stop session and append it to the
    existing daily history.

    The values stored here are session deltas, not global totals.
    """

    if not session_state:
        return False

    stop_dt = utc_now()
    start_dt = session_state["start_dt"]
    start_stats = session_state["start_stats"]
    current_stats = get_activity_stats_snapshot()

    record = {
        "session": session_state["session"],
        "start": format_gmt(start_dt),
        "stop": format_gmt(stop_dt),
        "duration_seconds": int(
            max(
                0,
                (stop_dt - start_dt).total_seconds()
            )
        ),
        "status": status,
        "follow": max(
            0,
            current_stats["follow"]
            - start_stats["follow"]
        ),
        "like (Story and Post)": max(
            0,
            current_stats["like (Story and Post)"]
            - start_stats["like (Story and Post)"]
        ),
        "story_seen": max(
            0,
            current_stats["story_seen"]
            - start_stats["story_seen"]
        ),
        "processed_accounts": max(
            0,
            current_stats["processed_accounts"]
            - start_stats["processed_accounts"]
        )
    }

    if error:
        record["error"] = str(error)

    history = load_activity_history()

    date_key = session_state["date_key"]

    if not isinstance(
        history.get(date_key),
        list
    ):
        history[date_key] = []

    history[date_key].append(record)

    save_json(
        ACTIVITY_HISTORY_FILE,
        history
    )

    print()
    print("=" * 70)
    print("ACTIVITY SESSION SAVED")
    print("=" * 70)
    print(
        f"Date: {date_key}"
    )
    print(
        f"Session: {record['session']}"
    )
    print(
        f"Start: {record['start']}"
    )
    print(
        f"Stop: {record['stop']}"
    )
    print(
        f"Duration: {record['duration_seconds']} seconds"
    )
    print(
        f"Status: {record['status']}"
    )
    print(
        f"Follow: {record['follow']}"
    )
    print(
        f"like (Story and Post): "
        f"{record['like (Story and Post)']}"
    )
    print(
        f"Story Seen: {record['story_seen']}"
    )
    print(
        f"Processed Accounts: "
        f"{record['processed_accounts']}"
    )

    if error:
        print(
            f"Error: {error}"
        )

    print(
        f"Saved to: {ACTIVITY_HISTORY_FILE}"
    )
    print("=" * 70)

    return True


# ============================================================
# REMOVE USER FROM QUEUE
# ============================================================

def remove_user_from_file(
    filename,
    user_id
):

    users = load_json(
        filename,
        []
    )

    if not isinstance(
        users,
        list
    ):

        return False

    user_id = str(
        user_id
    )

    new_users = []
    removed = False

    for user in users:

        current_id = user.get(
            "pk"
        )

        if current_id is None:

            new_users.append(
                user
            )

            continue

        if str(current_id) == user_id:

            removed = True

        else:

            new_users.append(
                user
            )

    if removed:

        save_json(
            filename,
            new_users
        )

    return removed


# ============================================================
# REQUEST FOLLOW JSON
# ============================================================

def save_follow_request(
    user_id,
    username
):

    data = load_json(
        REQUEST_FOLLOW,
        {
            "users": {}
        }
    )

    if not isinstance(data, dict):
        data = {
            "users": {}
        }

    if not isinstance(
        data.get("users"),
        dict
    ):
        data["users"] = {}

    user_id = str(
        user_id
    )

    if user_id not in data["users"]:

        data["users"][user_id] = {

            "user_id": user_id,

            "username": username,

            "followed_at": time.time()
        }

    save_json(
        REQUEST_FOLLOW,
        data
    )


# ============================================================
# REQUEST LIKE JSON
# ============================================================

def save_like_request(
    user_id,
    username,
    media_pk
):

    data = load_json(
        REQUEST_LIKE,
        {
            "likes": []
        }
    )

    if not isinstance(data, dict):

        data = {
            "likes": []
        }

    if not isinstance(
        data.get("likes"),
        list
    ):

        data["likes"] = []

    user_id = str(
        user_id
    )

    media_pk = str(
        media_pk
    )

    already_exists = any(

        str(
            item.get("user_id")
        ) == user_id

        and

        str(
            item.get("media_pk")
        ) == media_pk

        for item in data["likes"]
    )

    if already_exists:

        return False

    data["likes"].append({

        "user_id": user_id,

        "username": username,

        "media_pk": media_pk,

        "liked_at": time.time()
    })

    save_json(
        REQUEST_LIKE,
        data
    )

    return True


# ============================================================
# REQUEST STORY SEEN JSON
# ============================================================

def get_story_seen_data():
    """
    Load Story Seen history.

    Structure:
    {
        "stories": [
            {
                "user_id": "...",
                "username": "...",
                "story_pk": "...",
                "seen_at": 1234567890.0
            }
        ]
    }
    """

    data = load_json(
        REQUEST_STORY_SEEN,
        {
            "stories": []
        }
    )

    if not isinstance(data, dict):
        data = {"stories": []}

    if not isinstance(data.get("stories"), list):
        data["stories"] = []

    return data


def get_user_story_seen_records(user_id):
    """
    Return Story Seen records for one user.
    No Instagram request is made here.
    """

    user_id = str(user_id)
    data = get_story_seen_data()

    return [
        item
        for item in data["stories"]
        if (
            isinstance(item, dict)
            and str(item.get("user_id")) == user_id
        )
    ]


def get_user_story_seen_count(user_id):
    """
    Return how many unique Story PKs have already been
    successfully recorded as Seen for this user.
    """

    records = get_user_story_seen_records(user_id)

    story_pks = {
        str(item.get("story_pk"))
        for item in records
        if item.get("story_pk") is not None
    }

    return len(story_pks)


def has_story_seen(user_id, story_pk):
    """
    Check local REQUEST_STORY_SEEN only.
    This function does NOT contact Instagram.
    """

    user_id = str(user_id)
    story_pk = str(story_pk)

    records = get_user_story_seen_records(user_id)

    return any(
        str(item.get("story_pk")) == story_pk
        for item in records
    )


def get_remaining_story_slots(user_id, maximum=4):
    """
    Return how many new Story Seen operations are allowed
    for this user according to local history.
    """

    count = get_user_story_seen_count(user_id)

    return max(
        0,
        maximum - count
    )


def save_story_seen(
    user_id,
    username,
    story_pk
):
    """
    Save a Story only AFTER story_seen() succeeds.

    Maximum 4 Story Seen records per user are allowed.
    Returns True only when a new record was actually saved.
    """

    data = get_story_seen_data()

    user_id = str(user_id)
    story_pk = str(story_pk)

    # Do not save the same Story twice.
    already_exists = any(
        (
            isinstance(item, dict)
            and str(item.get("user_id")) == user_id
            and str(item.get("story_pk")) == story_pk
        )
        for item in data["stories"]
    )

    if already_exists:
        return False

    # Hard local limit: maximum 4 Story Seen records per user.
    user_story_count = len({
        str(item.get("story_pk"))
        for item in data["stories"]
        if (
            isinstance(item, dict)
            and str(item.get("user_id")) == user_id
            and item.get("story_pk") is not None
        )
    })

    if user_story_count >= 4:
        return False

    data["stories"].append({
        "user_id": user_id,
        "username": username,
        "story_pk": story_pk,
        "seen_at": time.time()
    })

    save_json(
        REQUEST_STORY_SEEN,
        data
    )

    return True


# ============================================================
# REQUEST STORY LIKE JSON
# ============================================================

def save_story_like(
    user_id,
    username,
    story_pk
):

    data = load_json(
        REQUEST_STORY_LIKE,
        {
            "likes": []
        }
    )

    if not isinstance(data, dict):

        data = {
            "likes": []
        }

    if not isinstance(
        data.get("likes"),
        list
    ):

        data["likes"] = []

    user_id = str(
        user_id
    )

    story_pk = str(
        story_pk
    )

    already_exists = any(

        str(
            item.get("user_id")
        ) == user_id

        and

        str(
            item.get("story_pk")
        ) == story_pk

        for item in data["likes"]
    )

    if already_exists:

        return False

    data["likes"].append({

        "user_id": user_id,

        "username": username,

        "story_pk": story_pk,

        "liked_at": time.time()
    })

    save_json(
        REQUEST_STORY_LIKE,
        data
    )

    return True


# ============================================================
# FOLLOW COOLDOWN
# ============================================================

def can_follow():

    return (
        time.time() - last_follow_time
        >= FOLLOW_COOLDOWN
    )


# ============================================================
# ASK USER DATA SOURCE
# ============================================================

def ask_users_source():

    while True:

        print()
        print("=" * 70)
        print("USER DATA SOURCE")
        print("=" * 70)

        print()
        print(
            "1. Use saved users from JSON files"
        )

        print(
            "2. Collect new users from Instagram"
        )

        print()

        choice = os.environ.get("BOT_USE_SAVED_USERS", "").strip()

        if choice:
            choice = "1" if choice.lower() in {"1", "true", "yes", "saved"} else "2"
        elif sys.stdin.isatty():
            choice = input("Select option (1/2): ").strip()
        else:
            choice = "1"

        # ----------------------------------------------------
        # USE SAVED DATA
        # ----------------------------------------------------

        if choice == "1":

            private_users = load_json(
                PRIVATE_USERS_FILE,
                []
            )

            public_users = load_json(
                PUBLIC_USERS_FILE,
                []
            )

            if isinstance(private_users, list) and isinstance(public_users, list) and (private_users or public_users):

                if not isinstance(
                    private_users,
                    list
                ):

                    print()
                    print(
                        f"{PRIVATE_USERS_FILE} "
                        "is invalid."
                    )

                    continue

                if not isinstance(
                    public_users,
                    list
                ):

                    print()
                    print(
                        f"{PUBLIC_USERS_FILE} "
                        "is invalid."
                    )

                    continue

                print()
                print(
                    "Saved users selected."
                )

                print(
                    f"Private users: "
                    f"{len(private_users)}"
                )

                print(
                    f"Public users: "
                    f"{len(public_users)}"
                )

                print()

                return False

            print()
            print(
                "Saved user files were not found."
            )

            print(
                f"Required:"
            )

            print(
                f"  {PRIVATE_USERS_FILE}"
            )

            print(
                f"  {PUBLIC_USERS_FILE}"
            )

            print()

            continue

        # ----------------------------------------------------
        # COLLECT NEW DATA
        # ----------------------------------------------------

        if choice == "2":

            print()
            print(
                "New user collection selected."
            )

            print()

            return True

        print()
        print(
            "Invalid selection."
        )


# ============================================================
# COLLECT NEW USERS
# ============================================================

def collect_new_users(cl):

    # ========================================================
    # LOCATION
    # ========================================================

    location_data = None
    place = None

    # --------------------------------------------------------
    # Check saved location
    # --------------------------------------------------------

    try:
        location_data = load_json(LOCATION_FILE, None)

        if location_data:
            print(
                f"\nSaved location found: "
                f"{LOCATION_FILE}"
            )

            location_pk = location_data.get("pk")
            location_name = location_data.get("name", "Saved location")

            if not location_pk:
                print("Saved location is invalid.")
                location_data = None
            else:
                print(f"Using saved location: {location_name}")

    except (json.JSONDecodeError, OSError):
        print("Could not read saved location.")
        location_data = None

    # --------------------------------------------------------
    # Request location if not saved
    # --------------------------------------------------------

    if not location_data:

        location_name = os.environ.get("BOT_LOCATION_NAME", "").strip()

        if not location_name and sys.stdin.isatty():
            location_name = input("\nEnter Instagram location: ").strip()

        if not location_name:
            raise RuntimeError(
                "No Instagram location supplied. Set BOT_LOCATION_NAME "
                "for Render/Telegram runs or run locally in an interactive terminal."
            )

        print(
            f"\nSearching location: "
            f"{location_name}"
        )

        places = cl.fbsearch_places(
            location_name
        )

        if not places:

            print(
                "No locations found."
            )

            return False

        print(
            "\nFound locations:\n"
        )

        for index, place_item in enumerate(
            places,
            start=1
        ):

            print(
                f"[{index}] "
                f"{place_item.name}"
                f" | city={place_item.city}"
                f" | address={place_item.address}"
                f" | pk={place_item.pk}"
            )

        while True:

            choice = os.environ.get("BOT_LOCATION_INDEX", "").strip()

            if not choice and sys.stdin.isatty():
                choice = input("\nSelect location number: ").strip()

            try:

                choice = int(
                    choice
                )

                if 1 <= choice <= len(places):

                    place = places[
                        choice - 1
                    ]

                    break

            except ValueError:

                pass

            print(
                "Invalid selection. Try again."
            )

        # ----------------------------------------------------
        # Save selected location
        # ----------------------------------------------------

        location_data = serialize_value(
            place
        )

        save_json(
            LOCATION_FILE,
            location_data
        )

        print(
            f"\nLocation saved: "
            f"{LOCATION_FILE}"
        )

        location_pk = place.pk

    else:

        # ----------------------------------------------------
        # Use saved location
        # ----------------------------------------------------

        location_pk = location_data["pk"]

    # ========================================================
    # EXISTING POSTS
    # ========================================================

    existing_posts = []

    existing_posts = load_json(
        POSTS_FILE,
        []
    )

    if not isinstance(
        existing_posts,
        list
    ):
        existing_posts = []

    # --------------------------------------------------------
    # Existing post IDs
    # --------------------------------------------------------

    existing_post_ids = set()

    for saved_post in existing_posts:

        post_pk = saved_post.get(
            "pk"
        )

        if post_pk is not None:

            existing_post_ids.add(
                str(post_pk)
            )

    print(
        f"\nPreviously saved posts: "
        f"{len(existing_post_ids)}"
    )

    # ========================================================
    # TOP POSTS
    # ========================================================

    print(
        f"\nGetting new posts from location..."
    )

    # --------------------------------------------------------
    # Request more posts than POST_COUNT.
    #
    # This gives us a chance to find new posts even when
    # previously saved posts are still inside the latest
    # results.
    # --------------------------------------------------------

    request_amount = max(
        POST_COUNT,
        len(existing_post_ids) + POST_COUNT
    )

    posts = cl.location_medias_top(
        location_pk,
        amount=request_amount
    )

    if not posts:

        print(
            "No posts found."
        )

        return False

    # ========================================================
    # FILTER NEW POSTS
    # ========================================================

    new_posts = []

    for post in posts:

        post_pk = getattr(
            post,
            "pk",
            None
        )

        if post_pk is None:

            continue

        post_pk = str(
            post_pk
        )

        # ----------------------------------------------------
        # Already saved -> skip
        # ----------------------------------------------------

        if post_pk in existing_post_ids:

            continue

        # ----------------------------------------------------
        # New post
        # ----------------------------------------------------

        new_posts.append(
            post
        )

        # Prevent duplicates in this same request
        existing_post_ids.add(
            post_pk
        )

        # ----------------------------------------------------
        # Stop when we have enough new posts
        # ----------------------------------------------------

        if len(new_posts) >= POST_COUNT:

            break

    # ========================================================
    # NO NEW POSTS
    # ========================================================

    if not new_posts:

        print(
            "\nNo new posts found."
        )

        return False

    print(
        f"\nNew posts found: "
        f"{len(new_posts)}"
    )

    # ========================================================
    # SAVE POSTS
    # ========================================================

    new_posts_data = [

        serialize_value(
            post
        )

        for post in new_posts
    ]

    # Keep old posts + add new posts
    all_posts_data = (
        existing_posts +
        new_posts_data
    )

    save_json(
        POSTS_FILE,
        all_posts_data
    )

    print(
        f"Posts saved: "
        f"{POSTS_FILE}"
    )

    # ========================================================
    # GET LIKERS
    # ========================================================

    private_users = []
    public_users = []

    private_seen = set()
    public_seen = set()

    wait_operation()

    for post_index, post in enumerate(
        new_posts,
        start=1
    ):

        print(
            "\n" + "=" * 70
        )

        print(
            f"POST "
            f"{post_index}/"
            f"{len(new_posts)}"
        )

        print(
            f"Media PK: "
            f"{post.pk}"
        )

        print(
            "=" * 70
        )

        # ----------------------------------------------------
        # ONLY LIKERS REQUEST
        # ----------------------------------------------------

        users = cl.media_likers(
            str(post.pk)
        )

        wait_operation()

        print(
            f"Likers received: "
            f"{len(users)}"
        )

        # ----------------------------------------------------
        # Separate users
        # ----------------------------------------------------

        for user in users:

            user_id = getattr(
                user,
                "pk",
                None
            )

            is_private = getattr(
                user,
                "is_private",
                None
            )

            if user_id is None:

                continue

            user_id = str(
                user_id
            )

            # ------------------------------------------------
            # PRIVATE
            # ------------------------------------------------

            if is_private is True:

                if user_id in private_seen:

                    continue

                private_seen.add(
                    user_id
                )

                private_users.append(
                    serialize_value(
                        user
                    )
                )

            # ------------------------------------------------
            # PUBLIC
            # ------------------------------------------------

            elif is_private is False:

                if user_id in public_seen:

                    continue

                public_seen.add(
                    user_id
                )

                public_users.append(
                    serialize_value(
                        user
                    )
                )

        # ----------------------------------------------------
        # Save after every post
        # ----------------------------------------------------

        save_json(
            PRIVATE_USERS_FILE,
            private_users
        )

        save_json(
            PUBLIC_USERS_FILE,
            public_users
        )

        print(
            f"Private users: "
            f"{len(private_users)}"
        )

        print(
            f"Public users: "
            f"{len(public_users)}"
        )

    print()
    print("=" * 70)
    print("NEW USER COLLECTION FINISHED")
    print("=" * 70)

    print(
        f"Private users: "
        f"{len(private_users)}"
    )

    print(
        f"Public users: "
        f"{len(public_users)}"
    )

    print("=" * 70)

    return True

# ============================================================
# FOLLOW ONE PRIVATE USER
# ============================================================

def process_one_private_user(
    cl,
    user,
    index,
    total
):

    global last_follow_time
    global FOLLOW_COOLDOWN

    user_id = user.get(
        "pk"
    )

    username = user.get(
        "username"
    )

    if user_id is None:

        print(
            f"[{index}/{total}] "
            f"Missing user ID -> skipped"
        )

        return False

    user_id = str(
        user_id
    )

    # ========================================================
    # MARK ACCOUNT AS PROCESSED
    # ========================================================

    mark_account_processed(
        user_id
    )

    # ========================================================
    # REMOVE FROM PRIVATE QUEUE
    # ========================================================

    removed = remove_user_from_file(
        PRIVATE_USERS_FILE,
        user_id
    )

    print(
        "PRIVATE USER"
    )

    print(
        f"[{index}/{total}] "
        f"@{username}"
    )

    print(
        f"User ID: {user_id}"
    )

    if removed:

        print(
            f"Removed @{username} "
            f"from {PRIVATE_USERS_FILE}"
        )

    print(
        "=" * 70
    )

    # ========================================================
    # FRIENDSHIP STATUS
    # ========================================================

    try:

        wait_in()

        friendships = (
            cl.user_friendships_v1(
                [user_id]
            )
        )

    except Exception as e:

        print(
            "\nError Friendship:"
        )

        print(
            type(e).__name__
        )

        print(
            e
        )

        return False

    if not friendships:

        print(
            "Friendship information unavailable"
        )

        return False

    friendship = friendships[0]

    print(
        "Is Following:",
        friendship.following
    )

    print(
        "Is Request To Follow:",
        friendship.outgoing_request
    )

    # ========================================================
    # ALREADY FOLLOWING
    # ========================================================

    if friendship.following:

        print(
            "Already Following"
        )

        return False

    # ========================================================
    # REQUEST ALREADY SENT
    # ========================================================

    if friendship.outgoing_request:

        print(
            "Follow Request Already Sent"
        )

        return False

    # ========================================================
    # FOLLOW
    # ========================================================

    try:

        wait_in()

        result = cl.user_follow(
            user_id
        )

        print(
            "Follow result:",
            result
        )

        if result:

            FOLLOW_COOLDOWN = random.randint(
                240,
                400
            )

            save_follow_request(
                user_id,
                username
            )

            # Global follow counter
            increment_stat(
                "follow"
            )
            register_action("follow")

            last_follow_time = (
                time.time()
            )

            print(
                f"Followed "
                f"@{username}"
            )

            wait_in()

            return True

        print(
            "Follow was not successful."
        )

        return False

    except Exception as e:

        print(
            "Error Follow:"
        )

        print(
            type(e).__name__
        )

        print(
            e
        )

        return False


# ============================================================
# PROCESS ONE PUBLIC USER
# ============================================================

def process_public_user(
    cl,
    user,
    index,
    total
):

    user_id = user.get(
        "pk"
    )

    username = user.get(
        "username"
    )

    if user_id is None:

        print(
            f"[{index}/{total}] "
            f"Missing user ID -> skipped"
        )

        return

    user_id = str(
        user_id
    )

    # ========================================================
    # MARK ACCOUNT AS PROCESSED
    # ========================================================

    mark_account_processed(
        user_id
    )

    # ========================================================
    # REMOVE FROM PUBLIC QUEUE
    # ========================================================

    removed = remove_user_from_file(
        PUBLIC_USERS_FILE,
        user_id
    )

    print(
        f"PUBLIC USER "
        f"[{index}/{total}]"
    )

    print(
        f"@{username}"
    )

    print(
        f"User ID: {user_id}"
    )

    if removed:

        print(
            f"Removed @{username} "
            f"from {PUBLIC_USERS_FILE}"
        )

    print(
        "=" * 70
    )

    # ========================================================
    # STORY
    # ========================================================

    # IMPORTANT:
    # Check local REQUEST_STORY_SEEN BEFORE calling Instagram.
    # If this user already has 4 successful Story Seen records,
    # do NOT request user_stories() at all.
    remaining_story_slots = get_remaining_story_slots(
        user_id,
        maximum=4
    )

    if remaining_story_slots <= 0:

        print(
            "Story limit already reached for "
            f"@{username}: 4/4"
        )

        stories = []

    else:

        print(
            f"Story slots available for "
            f"@{username}: "
            f"{remaining_story_slots}/4"
        )

        stories = []

        try:

            wait_in()

            stories = cl.user_stories(
                user_id
            )

        except Exception as e:

            print(
                "\nError Story:"
            )

            print(
                type(e).__name__
            )

            print(
                e
            )

            stories = []

        # ====================================================
        # STORY EXISTS
        # ====================================================

        if stories:

            # Only inspect as many Story objects as we can still
            # process. Previously-seen Story PKs are skipped locally.
            candidate_stories = []

            for story in stories:

                if has_story_seen(
                    user_id,
                    story.pk
                ):
                    print(
                        f"Skipping already-seen Story: "
                        f"{story.pk}"
                    )
                    continue

                candidate_stories.append(
                    story
                )

                if len(candidate_stories) >= remaining_story_slots:
                    break

            print(
                f"{len(stories)} Story found; "
                f"{len(candidate_stories)} new Story eligible."
            )

            for story_index, story in enumerate(
                candidate_stories,
                start=1
            ):

                # Re-check before every Instagram operation.
                # This protects the hard maximum of 4 even if the
                # local JSON was changed while the process is running.
                remaining_story_slots = get_remaining_story_slots(
                    user_id,
                    maximum=4
                )

                if remaining_story_slots <= 0:
                    print(
                        "Maximum 4 Story Seen reached."
                    )
                    break

                if has_story_seen(
                    user_id,
                    story.pk
                ):
                    print(
                        f"Story {story.pk} was already recorded. "
                        "Skipping."
                    )
                    continue

                print(
                    f"\n[{story_index}/"
                    f"{len(candidate_stories)}]"
                )

                print(
                    "PK:",
                    story.pk
                )

                print(
                    "ID:",
                    story.id
                )

                print(
                    "Media type:",
                    story.media_type
                )

                print(
                    "Taken at:",
                    story.taken_at
                )

                # ------------------------------------------------
                # SEEN STORY
                # ------------------------------------------------

                print(
                    f"\nSeeing Story "
                    f"{story_index}/"
                    f"{len(candidate_stories)}..."
                )

                try:

                    result = cl.story_seen(
                        story_pks=[
                            story.pk
                        ],
                        skipped_story_pks=[]
                    )

                    print(
                        f"Story "
                        f"{story_index}/"
                        f"{len(candidate_stories)} "
                        f"Seen result:",
                        result
                    )

                    if result:

                        # Save ONLY after Instagram confirmed
                        # the Story Seen request succeeded.
                        saved_seen = save_story_seen(
                            user_id,
                            username,
                            story.pk
                        )

                        if saved_seen:

                            increment_stat(
                                "story_seen"
                            )

                            # ------------------------------------------------
                            # LIKE THE SAME STORY
                            # ------------------------------------------------
                            # No separate local "already liked" check.
                            # Like is performed only after successful Seen.

                            try:

                                delay = random.randint(
                                    10,
                                    14
                                )

                                print(
                                    f"Waiting {delay} "
                                    f"seconds before liking Story..."
                                )

                                time.sleep(
                                    delay
                                )

                                like_result = cl.story_like(
                                    story.id,
                                    mark_seen=False
                                )

                                print(
                                    f"Story "
                                    f"{story_index}/"
                                    f"{len(candidate_stories)} "
                                    f"Like result:",
                                    like_result
                                )

                                if like_result:

                                    # Keep the existing Story Like
                                    # history file only as a record.
                                    save_story_like(
                                        user_id,
                                        username,
                                        story.pk
                                    )

                                    increment_stat(
                                        "like (Story and Post)"
                                    )
                                    register_action("like")

                            except Exception as e:

                                print(
                                    "\nError liking Story:"
                                )

                                print(
                                    type(e).__name__
                                )

                                print(
                                    e
                                )

                        else:

                            print(
                                "Story Seen succeeded, but the "
                                "Story was already recorded locally. "
                                "Like skipped."
                            )

                    else:

                        print(
                            "Story Seen was not successful. "
                            "Story was NOT saved and Like was skipped."
                        )

                except Exception as e:

                    print(
                        "\nError seeing Story:"
                    )

                    print(
                        type(e).__name__
                    )

                    print(
                        e
                    )

                # ------------------------------------------------
                # DELAY BETWEEN STORIES
                # ------------------------------------------------

                if story_index < len(candidate_stories):

                    delay = random.randint(
                        6,
                        12
                    )

                    print(
                        f"Waiting {delay} "
                        f"seconds before next Story..."
                    )

                    time.sleep(
                        delay
                    )

        else:

            print(
                "Don't have Story"
            )

    # ========================================================
    # USER POSTS
    # ========================================================

    try:

        wait_in()
        wait_in()

        medias = cl.user_medias(
            user_id,
            amount=12
        )

    except Exception as e:

        print(
            "\nError getting posts:"
        )

        print(
            type(e).__name__
        )

        print(
            e
        )

        return

    if not medias:

        print(
            "Don Have Post"
        )

        return

    # --------------------------------------------------------
    # NEWEST FIRST
    # --------------------------------------------------------

    medias = sorted(
        medias,
        key=lambda media: media.taken_at,
        reverse=True
    )

    print(
        "\n" + "=" * 70
    )

    print(
        f"I Found "
        f"{len(medias)} "
        f" POST."
    )

    for media_index, media in enumerate(
        medias,
        start=1
    ):

        print(
            f"[{media_index}] "
            f"PK={media.pk} | "
            f"Date={media.taken_at} | "
            f"Liked={media.has_liked}"
        )

    # ========================================================
    # NEWEST POST
    # ========================================================

    newest = medias[0]

    if newest.has_liked:

        print(
            "The latest post had already been liked."
        )

    else:

        try:

            wait_in()

            result = cl.media_like(
                newest.pk
            )

            if result:

                saved = save_like_request(
                    user_id,
                    username,
                    newest.pk
                )

                if saved:

                    # Global like counter
                    increment_stat(
                        "like (Story and Post)"
                    )
                    register_action("like")

                print(
                    "I liked latest Post"
                )

            else:

                print(
                    "Error: Post not liked"
                )

        except Exception as e:

            print(
                "\nError Like latest post:"
            )

            print(
                type(e).__name__
            )

            print(
                e
            )

    # ========================================================
    # NO STORY
    # ========================================================

    if not stories:

        available_random_posts = (
            medias[1:9]
        )

        if available_random_posts:

            random_post = random.choice(
                available_random_posts
            )

            print(
                "\nRandom post selected:"
            )

            print(
                random_post.pk
            )

            # ------------------------------------------------
            # LIKE RANDOM POST
            # ------------------------------------------------

            if random_post.has_liked:

                print(
                    "The random post "
                    "had already been liked."
                )

            else:

                try:

                    wait_in()

                    result = cl.media_like(
                        random_post.pk
                    )

                    if result:

                        saved = save_like_request(
                            user_id,
                            username,
                            random_post.pk
                        )

                        if saved:

                            # Global like counter
                            increment_stat(
                                "like (Story and Post)"
                            )
                            register_action("like")

                        print(
                            "The random post was liked."
                        )

                    else:

                        print(
                            "Random post "
                            "was not liked."
                        )

                    wait_account()

                except Exception as e:

                    print(
                        "\nError Like "
                        "random post:"
                    )

                    print(
                        type(e).__name__
                    )

                    print(
                        e
                    )

        else:

            print(
                "\nNo second post available "
                "for random selection."
            )


# ============================================================
# PROCESS PUBLIC USERS DURING COOLDOWN
# ============================================================

def process_public_users_during_cooldown(
    cl,
    cooldown_start
):

    public_users = load_json(
        PUBLIC_USERS_FILE,
        []
    )

    if not isinstance(
        public_users,
        list
    ):

        print(
            "Invalid public_users.json"
        )

        return

    print()
    print("=" * 70)
    print("PUBLIC USERS - COOLDOWN ACTIVITY")
    print("=" * 70)

    print(
        f"Public users loaded: "
        f"{len(public_users)}"
    )

    print(
        f"Cooldown: "
        f"{FOLLOW_COOLDOWN} seconds"
    )

    total = len(
        public_users
    )

    for index, user in enumerate(
        public_users,
        start=1
    ):

        elapsed = (
            time.time()
            - cooldown_start
        )

        remaining = (
            FOLLOW_COOLDOWN
            - elapsed
        )

        # ----------------------------------------------------
        # COOLDOWN FINISHED
        # ----------------------------------------------------

        if remaining <= 0:

            print()
            print(
                "240 second cooldown finished."
            )

            break

        print(
            f"Cooldown remaining: "
            f"{int(remaining)} seconds"
        )

        process_public_user(
            cl,
            user,
            index,
            total
        )

        # ----------------------------------------------------
        # WAIT BETWEEN PUBLIC ACCOUNTS
        # ----------------------------------------------------

        elapsed = (
            time.time()
            - cooldown_start
        )

        remaining = (
            FOLLOW_COOLDOWN
            - elapsed
        )

        if remaining <= 0:

            break

        delay = random.randint(
            10,
            16
        )

        delay = min(
            delay,
            int(remaining)
        )

        if delay > 0:

            print(
                f"\nWaiting {delay} "
                f"seconds..."
            )

    # ========================================================
    # WAIT REMAINING COOLDOWN
    # ========================================================

    elapsed = (
        time.time()
        - cooldown_start
    )

    remaining = (
        FOLLOW_COOLDOWN
        - elapsed
    )

    if remaining > 0:

        print()
        print(
            f"Public users finished."
        )

        print(
            f"Waiting remaining "
            f"{int(remaining)} seconds "
            f"of cooldown..."
        )

        while True:

            remaining = (
                FOLLOW_COOLDOWN
                -
                (
                    time.time()
                    -
                    cooldown_start
                )
            )

            if remaining <= 0:

                break

            sleep_time = min(
                5,
                int(remaining)
            )

            if sleep_time > 0:

                time.sleep(
                    sleep_time
                )

    print()
    print(
        "Cooldown finished."
    )

    print_stats()


# ============================================================
# PRIVATE → COOLDOWN → PUBLIC CYCLE
# ============================================================

def run_private_public_cycle(
    cl
):

    global last_follow_time

    print()
    print("=" * 70)
    print("PRIVATE / PUBLIC CYCLE")
    print("=" * 70)

    # --------------------------------------------------------
    # Process ONE private user per cycle.
    #
    # IMPORTANT:
    # The JSON files are reloaded every cycle.
    # Therefore removed users will NOT be processed again.
    # --------------------------------------------------------

    while True:

        # ====================================================
        # LOAD CURRENT PRIVATE USERS
        # ====================================================

        private_users = load_json(
            PRIVATE_USERS_FILE,
            []
        )

        if not isinstance(
            private_users,
            list
        ):

            print(
                "Invalid private_users.json"
            )

            return

        # ====================================================
        # LOAD CURRENT PUBLIC USERS
        # ====================================================

        public_users = load_json(
            PUBLIC_USERS_FILE,
            []
        )

        if not isinstance(
            public_users,
            list
        ):

            print(
                "Invalid public_users.json"
            )

            return

        print(
            f"Private users remaining: "
            f"{len(private_users)}"
        )

        print(
            f"Public users remaining: "
            f"{len(public_users)}"
        )

        # ====================================================
        # ALL PRIVATE USERS FINISHED
        # ====================================================

        if not private_users:

            print()
            print("=" * 70)
            print("ALL PRIVATE USERS PROCESSED")
            print("=" * 70)

            break

        # ====================================================
        # GET FIRST PRIVATE USER
        # ====================================================

        user = private_users[0]

        private_index = 1

        # ====================================================
        # PRIVATE CYCLE
        # ====================================================

        print()
        print()
        print(
            "#" * 70
        )

        print(
            "PRIVATE CYCLE"
        )

        print(
            f"Private users remaining: "
            f"{len(private_users)}"
        )

        print(
            f"Next private user: "
            f"@{user.get('username')}"
        )

        print(
            "#" * 70
        )

        # ====================================================
        # PRIVATE USER
        # ====================================================

        follow_result = process_one_private_user(
            cl,
            user,
            private_index,
            len(private_users)
        )

        # ====================================================
        # START COOLDOWN
        # ====================================================

        cooldown_start = time.time()

        if follow_result:

            print(
                "FOLLOW SUCCESSFUL"
            )

            print(
                f"Starting "
                f"{FOLLOW_COOLDOWN} second cooldown."
            )

            print(
                "Public users will be processed "
                "during this cooldown."
            )

        else:

            print()
            print(
                "=" * 70
            )

            print(
                "PRIVATE ACTION DID NOT FOLLOW"
            )

            print(
                f"Starting "
                f"{FOLLOW_COOLDOWN} second cycle "
                f"anyway."
            )

            print(
                "Public users will be processed "
                "during this period."
            )

            print(
                "=" * 70
            )

        # ====================================================
        # PUBLIC ACTIVITY DURING COOLDOWN
        # ====================================================

        process_public_users_during_cooldown(
            cl,
            cooldown_start
        )

    # ========================================================
    # FINAL
    # ========================================================

    print()
    print("=" * 70)
    print("PRIVATE / PUBLIC PROCESSING FINISHED")
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Prerequisites / Xray MUST be ready before Session use.
    # --------------------------------------------------------

    start_xray_proxy()

    # --------------------------------------------------------
    # Client
    # --------------------------------------------------------

    cl = create_client()

    print(
        "Session loaded successfully."
    )

    # ========================================================
    # ASK DATA SOURCE
    # ========================================================

    use_new_users = ask_users_source()

    # ========================================================
    # COLLECT NEW USERS
    # ========================================================

    if use_new_users:

        result = collect_new_users(
            cl
        )

        if not result:

            print(
                "\nNew user collection failed."
            )

            return

    # ========================================================
    # USE SAVED USERS
    # ========================================================

    else:

        print()
        print(
            "=" * 70
        )

        print(
            "USING SAVED USER DATA"
        )

        print(
            "=" * 70
        )

        private_users = load_json(
            PRIVATE_USERS_FILE,
            []
        )

        public_users = load_json(
            PUBLIC_USERS_FILE,
            []
        )

        print(
            f"Private users: "
            f"{len(private_users)}"
        )
        if len(private_users) == 0 or len(public_users) == 0:
            result = collect_new_users(
                cl
            )

            if not result:

                print(
                    "\nNew user collection failed."
                )

                return

        print(
            f"Public users: "
            f"{len(public_users)}"
        )

    # ========================================================
    # PRIVATE → 240 SEC → PUBLIC
    # ========================================================

    run_private_public_cycle(
        cl
    )

    # ========================================================
    # DONE
    # ========================================================

    print_stats()

    print(
        "\n" + "=" * 70
    )

    print(
        "DONE"
    )

    print(
        "=" * 70
    )

    print(
        f"Location: "
        f"{LOCATION_FILE}"
    )

    print(
        f"Posts: "
        f"{POSTS_FILE}"
    )

    print(
        f"Private users: "
        f"{PRIVATE_USERS_FILE}"
    )

    print(
        f"Public users: "
        f"{PUBLIC_USERS_FILE}"
    )

    print(
        f"Follow records: "
        f"{REQUEST_FOLLOW}"
    )

    print(
        f"Like records: "
        f"{REQUEST_LIKE}"
    )

    print(
        f"Story records: "
        f"{REQUEST_STORY_SEEN}"
    )

    print(
        "=" * 70
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    activity_session = None

    try:

        # Start a new independent Start -> Stop activity session.
        # Existing sessions in activity_history.json are preserved.
        activity_session = start_activity_session()

        main()

        # Normal completion.
        finish_activity_session(
            activity_session,
            status="completed"
        )

    except KeyboardInterrupt:

        # Ctrl+C: save everything performed before the interruption.
        if activity_session is not None:

            try:

                finish_activity_session(
                    activity_session,
                    status="stopped_by_user"
                )

            except Exception:

                print(
                    "\nWARNING: Could not save activity session history."
                )

                traceback.print_exc()

        print(
            "\nProgram stopped by user."
        )

    except SystemExit as e:

        # Preserve SystemExit behavior, but save the current session first.
        if activity_session is not None:

            try:

                finish_activity_session(
                    activity_session,
                    status="system_exit",
                    error=f"SystemExit: {e}"
                )

            except Exception:

                print(
                    "\nWARNING: Could not save activity session history."
                )

                traceback.print_exc()

        raise

    except Exception as e:

        # Any unexpected error also closes and saves the session so the
        # activity performed before the crash is not lost.
        if activity_session is not None:

            try:

                finish_activity_session(
                    activity_session,
                    status="error",
                    error=f"{type(e).__name__}: {e}"
                )

            except Exception:

                print(
                    "\nWARNING: Could not save activity session history."
                )

                traceback.print_exc()

        print(
            "\n" + "=" * 70
        )

        print(
            "ERROR - PROGRAM STOPPED"
        )

        print(
            "=" * 70
        )

        traceback.print_exc()

        print(
            "=" * 70
        )

        raise

    finally:

        stop_xray_proxy()
