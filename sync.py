#!/usr/bin/env python3
"""
PlayTV 24/7 Cloud Stream Sync Engine
Runs on GitHub Actions to auto-update live Akamai CDN streams into Firebase RTDB.
Monitors: Sony TV HD, SAB HD, MAX HD, MAX 2, PIX HD, YAY, PAL, WAH, BBC Earth HD, Sports Ten 1, Ten 2, Ten 3.
"""

import urllib.request
import json
import ssl
import sys
import datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

M3U_URL = "https://raw.githubusercontent.com/sportlive18/Sonyliv-Playlist-Autoupdate/main/sony.m3u"
FIREBASE_URL = "https://playtv-ba8df-default-rtdb.firebaseio.com/channels.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

CH_MAPPING = {
    "Sony Entertainment Television HD": "sonytv",
    "Sony SAB": "sonysab",
    "Sony MAX HD": "sonymaxhd",
    "Sony MAX 2": "sonymax2",
    "Sony PIX HD": "sonypix",
    "Sony YAY": "sonyyay",
    "Sony PAL": "sonypal",
    "Sony WAH": "sonywah",
    "Sony BBC Earth HD": "bbcearth",
    "Sony Sports 1 HD": "sonysports1",
    "Sony Sports 2 HD": "sonysports2",
    "Sony Sports 3 Hindi HD": "sonysports3"
}

PRESERVED_FALLBACKS = {"sonysports1", "sonysports2", "bbcearth", "sonytv"}

def log(msg):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{now}] {msg}")

def verify_stream(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            if resp.status == 200:
                body = resp.read(300).decode("utf-8", errors="ignore")
                return "#EXTM3U" in body or "#EXT-X" in body
    except Exception as e:
        log(f"Stream verification failed: {e}")
    return False

def main():
    log("Starting PlayTV 24/7 Cloud Sync...")
    
    # 1. Fetch fresh streams from M3U
    try:
        req_m3u = urllib.request.Request(M3U_URL, headers=HEADERS)
        with urllib.request.urlopen(req_m3u, context=ctx, timeout=10) as r:
            lines = r.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as e:
        log(f"Error fetching source m3u: {e}")
        sys.exit(1)

    fresh_streams = {}
    for i, l in enumerate(lines):
        if l.startswith("#EXTINF:"):
            next_url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            for tag, ch_id in CH_MAPPING.items():
                if tag in l and next_url.startswith("http"):
                    fresh_streams[ch_id] = next_url

    log(f"Extracted {len(fresh_streams)} candidate streams from source.")

    # 2. Fetch Firebase channels
    try:
        req_fb = urllib.request.Request(FIREBASE_URL, headers=HEADERS)
        with urllib.request.urlopen(req_fb, context=ctx, timeout=10) as r:
            channels = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log(f"Error fetching Firebase channels: {e}")
        sys.exit(1)

    updated = False
    for ch in channels:
        ch_id = ch.get("id")
        if ch_id in fresh_streams:
            new_url = fresh_streams[ch_id]
            cur_url = ch.get("primaryUrl", "")
            if cur_url != new_url:
                if verify_stream(new_url):
                    log(f"Stream updated for {ch.get('name')}:")
                    log(f"  Old: {cur_url[:60]}...")
                    log(f"  New: {new_url[:60]}...")
                    ch["primaryUrl"] = new_url
                    if ch_id not in PRESERVED_FALLBACKS:
                        ch["fallbackUrl"] = new_url
                    updated = True
                else:
                    log(f"New stream verification failed for {ch.get('name')}, skipping.")

    if updated:
        try:
            data = json.dumps(channels, indent=2).encode("utf-8")
            put_req = urllib.request.Request(
                FIREBASE_URL,
                data=data,
                method="PUT",
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(put_req, context=ctx, timeout=12) as resp:
                log(f"Firebase RTDB updated successfully! HTTP Status: {resp.status}")
        except Exception as e:
            log(f"Failed to PUT updated channels to Firebase: {e}")
            sys.exit(1)
    else:
        log("All channel tokens are already up to date and healthy.")

    log("Cloud sync finished successfully.")

if __name__ == "__main__":
    main()
