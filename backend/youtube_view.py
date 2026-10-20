"""youtube_view -- READ-ONLY view of Ilnora's YouTube channel (2026-10-07, Barry: channel tool approved --
"read-only stats ... so the audience can steer her" + "comments: she reads them and drafts replies to the DESK.
I post them; nothing gets written to YouTube").

GET requests only, with the public YOUTUBE_API_KEY from .env. An API key cannot post, reply, delete or edit
anything on YouTube, and there is no OAuth / sign-in here at all -- by design this module can only look.
Barry (2026-10-04): "google is ok, just dont let it write nothing".

  channel_stats()  -- channel totals, every video (views, likes, comments, views per day since posting), the
                      topics behind each video (from her own video records), ranked by what is working, and growth
                      since the last dated snapshot (data/youtube/snapshots/YYYY-MM-DD.json).
  read_comments()  -- comments she has not seen yet (data/youtube/comments_seen.json), newest first.

Not available with a key (needs the YouTube Analytics sign-in, Barry's call): watch time, retention, CTR,
traffic sources, audience.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(_ROOT, "data", "youtube")
SNAPS = os.path.join(DATA, "snapshots")
SEEN = os.path.join(DATA, "comments_seen.json")
API = "https://www.googleapis.com/youtube/v3/"
# Ilnora Goodwitch, @ilnoragoodwitch (resolved by handle 2026-10-07). Not a secret; env can override.
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "UCHeL2hx7UbvKkua1dLW29kA")
_GENERIC_TAGS = {"herbalism", "witchtok", "herbs", "herbal", "plants", "shorts", "fyp", "foryou", "folklore",
                 "plantmedicine", "herbalist", "witch", "witchcraft"}

CHANNEL_STATS_TOOL = {
    # 2026-10-07 (youtube_view.py): read-only -- nothing is ever written to YouTube.
    "type": "function",
    "function": {
        "name": "channel_stats",
        "description": (
            "See how YOUR YouTube channel is doing, live: subscribers, total views, and every video you have posted "
            "-- views, likes, comments, views per day since it went up, and the plants/topics in it -- ranked by "
            "what is working best, plus how much the channel grew since the last check. Let your audience steer "
            "you: make more of what they watch. Read-only: it only looks."),
        "parameters": {"type": "object", "properties": {}},
    },
}

READ_COMMENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "read_comments",
        "description": (
            "Read the comments people left on your YouTube videos -- by default only the ones you have not seen "
            "yet -- with the video, the commenter's name and what they said. You cannot reply on YouTube from here: "
            "write your replies in ONE document with send_file_to_owner (each comment, its video link, your "
            "reply) and Barry posts them. Read-only."),
        "parameters": {"type": "object", "properties": {
            "only_new": {"type": "boolean", "description": "true (default) = only comments you have not read yet"},
            "count": {"type": "integer", "description": "most comments to return (1-100, default 40)"}}},
    },
}


def _key() -> str:
    k = (os.environ.get("YOUTUBE_API_KEY") or "").strip().strip('"')
    if not k:
        try:
            with open(os.path.join(_ROOT, ".env"), encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("YOUTUBE_API_KEY="):
                        k = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return k


def _get(path: str, **params) -> dict:
    """The only network call in this module: an HTTP GET. Nothing here can write."""
    key = _key()
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not in the .env")
    params["key"] = key
    req = urllib.request.Request(API + path + "?" + urllib.parse.urlencode(params), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)["error"]["message"]
        except Exception:  # noqa: BLE001
            msg = str(e)
        raise RuntimeError(f"YouTube said: {html.unescape(re.sub('<[^>]+>', '', msg))}") from None


def _norm(t: str) -> set:
    return set(re.sub(r"[^a-z0-9 ]", " ", html.unescape(t or "").lower()).split())


def _her_records() -> list[tuple[set, list[str]]]:
    """(title words, topics) for each video she made -- topics = her own hashtags minus the generic ones."""
    out = []
    try:
        import memory
        with memory.get_db() as conn:
            rows = conn.execute("SELECT content FROM approvals WHERE agent_id = 'ilnora' AND "
                                "content LIKE 'VIDEO: %'").fetchall()
    except Exception:  # noqa: BLE001
        return out
    for (c,) in rows:
        m = re.match(r"VIDEO: (.+?)(?: \(|\n|$)", c or "")
        if not m:
            continue
        tags = [t.lower() for t in re.findall(r"#(\w+)", c)]
        out.append((_norm(m.group(1)), [t for t in dict.fromkeys(tags) if t not in _GENERIC_TAGS]))
    return out


def _topics_for(title: str, yt_tags: list, records) -> list[str]:
    words = _norm(title)
    best, score = None, 0.0
    for w, topics in records:
        if w and words:
            s = len(w & words) / len(w)     # her record's title inside the (often longer) YouTube title
            if s > score:
                best, score = topics, s
    if best and score >= 0.75:
        return best
    return [t.lower() for t in (yt_tags or []) if t.lower() not in _GENERIC_TAGS][:6]


def _seconds(iso: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _videos() -> list[dict]:
    uploads = "UU" + CHANNEL_ID[2:]
    ids, token = [], None
    while True:
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if token:
            p["pageToken"] = token
        d = _get("playlistItems", **p)
        ids += [i["contentDetails"]["videoId"] for i in d.get("items", [])]
        token = d.get("nextPageToken")
        if not token or len(ids) >= 500:
            break
    out = []
    for i in range(0, len(ids), 50):
        d = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        out += d.get("items", [])
    return out


def channel_stats() -> dict:
    ch = _get("channels", part="snippet,statistics", id=CHANNEL_ID).get("items") or []
    if not ch:
        return {"error": "channel not found"}
    st = ch[0]["statistics"]
    now = datetime.datetime.now(datetime.timezone.utc)
    records = _her_records()
    vids = []
    for v in _videos():
        sn, vs = v["snippet"], v.get("statistics", {})
        posted = datetime.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        age = max((now - posted).total_seconds() / 86400, 0.5)
        views = int(vs.get("viewCount", 0))
        secs = _seconds(v.get("contentDetails", {}).get("duration", ""))
        vids.append({
            "title": html.unescape(sn.get("title", "")),
            "url": f"https://youtu.be/{v['id']}",
            "posted": posted.date().isoformat(),
            "days_up": round(age, 1),
            "length_s": secs,
            "kind": "short" if secs <= 180 else "long",
            "views": views,
            "views_per_day": round(views / age, 1),
            "likes": int(vs.get("likeCount", 0)),
            "comments": int(vs.get("commentCount", 0)),
            "topics": _topics_for(sn.get("title", ""), sn.get("tags"), records),
        })
    vids.sort(key=lambda x: (x["views_per_day"], x["likes"]), reverse=True)
    for n, v in enumerate(vids, 1):
        v["rank"] = n
    topics: dict = {}
    for v in vids:
        for t in v["topics"]:
            a = topics.setdefault(t, {"topic": t, "videos": 0, "views": 0, "views_per_day": 0.0, "likes": 0})
            a["videos"] += 1
            a["views"] += v["views"]
            a["views_per_day"] = round(a["views_per_day"] + v["views_per_day"], 1)
            a["likes"] += v["likes"]
    snap = {"date": now.astimezone().date().isoformat(), "fetched_at": now.astimezone().isoformat(timespec="seconds"),
            "subscribers": int(st.get("subscriberCount", 0)), "views": int(st.get("viewCount", 0)),
            "videos": int(st.get("videoCount", 0)),
            "per_video": {v["url"]: {"views": v["views"], "likes": v["likes"], "comments": v["comments"]} for v in vids}}
    growth = _growth(snap)
    os.makedirs(SNAPS, exist_ok=True)
    with open(os.path.join(SNAPS, snap["date"] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=1)
    return {
        "channel": ch[0]["snippet"].get("title"), "subscribers": snap["subscribers"], "total_views": snap["views"],
        "video_count": snap["videos"], "growth": growth,
        "videos_ranked_by_views_per_day": vids,
        "topics_ranked": sorted(topics.values(), key=lambda a: a["views_per_day"], reverse=True),
        "note": ("Live numbers from YouTube, read-only. Views per day is fairer than total views (older videos "
                 "had longer). With only a few videos, one video is not a trend. YouTube updates the channel total "
                 "later than each video's count. Watch time and retention are not available here."),
    }


def _growth(snap: dict) -> dict | str:
    try:
        prev = sorted(f for f in os.listdir(SNAPS) if f.endswith(".json") and f[:-5] < snap["date"])
    except OSError:
        prev = []
    if not prev:
        return "first check -- growth shows from the next day you check"
    with open(os.path.join(SNAPS, prev[-1]), encoding="utf-8") as fh:
        old = json.load(fh)
    return {"since": old.get("date"), "subscribers": snap["subscribers"] - old.get("subscribers", 0),
            "views": snap["views"] - old.get("views", 0), "videos": snap["videos"] - old.get("videos", 0)}


def read_comments(only_new: bool = True, count: int = 40) -> dict:
    count = max(1, min(int(count or 40), 100))
    try:
        with open(SEEN, encoding="utf-8") as fh:
            seen = set(json.load(fh))
    except (OSError, ValueError):
        seen = set()
    titles = {}
    out, token, pages = [], None, 0
    while len(out) < count and pages < 5:
        p = {"part": "snippet,replies", "allThreadsRelatedToChannelId": CHANNEL_ID, "maxResults": 100,
             "order": "time", "textFormat": "plainText"}
        if token:
            p["pageToken"] = token
        d = _get("commentThreads", **p)
        pages += 1
        for t in d.get("items", []):
            top = t["snippet"]["topLevelComment"]["snippet"]
            if top.get("authorChannelId", {}).get("value") == CHANNEL_ID:
                continue            # her own comment
            if only_new and t["id"] in seen:
                continue
            vid = t["snippet"].get("videoId", "")
            replies = (t.get("replies") or {}).get("comments", [])
            out.append({
                "comment_id": t["id"], "video_id": vid, "video_url": f"https://youtu.be/{vid}",
                "author": top.get("authorDisplayName", ""), "said": top.get("textDisplay", ""),
                "posted": (top.get("publishedAt") or "")[:10], "likes": top.get("likeCount", 0),
                "you_already_replied": any(r["snippet"].get("authorChannelId", {}).get("value") == CHANNEL_ID
                                           for r in replies),
            })
            if len(out) >= count:
                break
        token = d.get("nextPageToken")
        if not token:
            break
    ids = sorted({c["video_id"] for c in out if c["video_id"]})
    for i in range(0, len(ids), 50):
        for v in _get("videos", part="snippet", id=",".join(ids[i:i + 50])).get("items", []):
            titles[v["id"]] = html.unescape(v["snippet"].get("title", ""))
    for c in out:
        c["video"] = titles.get(c.pop("video_id"), "")
    seen |= {c["comment_id"] for c in out}
    os.makedirs(DATA, exist_ok=True)
    with open(SEEN, "w", encoding="utf-8") as fh:
        json.dump(sorted(seen), fh)
    return {
        "comments": out,
        "count": len(out),
        "note": ("No new comments." if not out else
                 "Replies cannot be posted from here. Put your replies in ONE send_file_to_owner document -- each "
                 "comment, its video link and your reply -- and Barry posts them."),
    }
