import json
import os
import time
import traceback
import random
from datetime import datetime, timezone

from instagrapi import Client


# ============================================================
# SETTINGS
# ============================================================

SESSION_FILE = "instagram_session.json"

LOCATION_FILE = "location_data.json"
POSTS_FILE = "posts_data.json"

PRIVATE_USERS_FILE = "private_users.json"
PUBLIC_USERS_FILE = "public_users.json"

REQUEST_FOLLOW = "request_follow.json"
REQUEST_LIKE = "request_like.json"
REQUEST_STORY_SEEN = "request_story_seen.json"
REQUEST_STORY_LIKE = "request_story_like.json"
STATS_FILE = "stats.json"
ACTIVITY_HISTORY_FILE = "activity_history.json"

POST_COUNT = 10

FOLLOWING_LIMIT = 3000
FOLLOWER_LIMIT = 30

FOLLOW_COOLDOWN = 240

NEXT_LIKE_TIME = 80

last_follow_time = 0


# ============================================================
# CLIENT
# ============================================================

def create_client():

    cl = Client()

    if not os.path.exists(SESSION_FILE):

        raise FileNotFoundError(
            f"Session file not found: {SESSION_FILE}"
        )

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
# JSON
# ============================================================

def load_json(
    filename,
    default
):

    if not os.path.exists(filename):

        return default

    try:

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except (
        json.JSONDecodeError,
        OSError
    ):

        return default


def save_json(
    filename,
    data
):

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

        os.fsync(
            f.fileno()
        )

    os.replace(
        temp_file,
        filename
    )


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

        choice = input(
            "Select option (1/2): "
        ).strip()

        # ----------------------------------------------------
        # USE SAVED DATA
        # ----------------------------------------------------

        if choice == "1":

            private_exists = os.path.exists(
                PRIVATE_USERS_FILE
            )

            public_exists = os.path.exists(
                PUBLIC_USERS_FILE
            )

            if (
                private_exists
                and
                public_exists
            ):

                private_users = load_json(
                    PRIVATE_USERS_FILE,
                    []
                )

                public_users = load_json(
                    PUBLIC_USERS_FILE,
                    []
                )

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

    location_name = input(
        "\nEnter Instagram location: "
    ).strip()

    if not location_name:

        raise ValueError(
            "Location cannot be empty."
        )

    # --------------------------------------------------------
    # Search location
    # --------------------------------------------------------

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

    for index, place in enumerate(
        places,
        start=1
    ):

        print(
            f"[{index}] "
            f"{place.name}"
            f" | city={place.city}"
            f" | address={place.address}"
            f" | pk={place.pk}"
        )

    while True:

        choice = input(
            "\nSelect location number: "
        ).strip()

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

    # ========================================================
    # LOCATION DATA
    # ========================================================

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

    # ========================================================
    # TOP POSTS
    # ========================================================

    print(
        f"\nGetting latest "
        f"{POST_COUNT} posts..."
    )

    posts = cl.location_medias_top(
        place.pk,
        amount=POST_COUNT
    )

    if not posts:

        print(
            "No posts found."
        )

        return False

    # --------------------------------------------------------
    # Save posts
    # --------------------------------------------------------

    posts_data = [

        serialize_value(
            post
        )

        for post in posts
    ]

    save_json(
        POSTS_FILE,
        posts_data
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
        posts,
        start=1
    ):

        print(
            "\n" + "=" * 70
        )

        print(
            f"POST "
            f"{post_index}/"
            f"{len(posts)}"
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