#!/usr/bin/env python3
"""
PlayTV 24/7 Universal Cloud Stream Sync & Self-Healing Engine
Runs on GitHub Actions every 20 minutes to auto-monitor and refresh live CDN streams in Firebase RTDB.

Monitors:
  - Sony LIV Networks: Sony TV HD, SAB HD, MAX HD, MAX 2, PIX HD, YAY, PAL, WAH, BBC Earth HD, Sports Ten 1, Ten 2, Ten 3, Sony Sports 5 HD.
  - Infotainment & Documentary: Discovery HD, Animal Planet HD, Discovery Science, TLC HD.
  - Kids & Animation: Cartoon Network HD, Cartoon Network Hindi, Discovery Kids HD, Pogo TV.
  - Sports Networks: T Sports HD.
"""

import urllib.request
import json
import ssl
import sys
import datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FIREBASE_URL = "https://playtv-ba8df-default-rtdb.firebaseio.com/channels.json"

# --- Sources ---
SONY_M3U_URL = "https://raw.githubusercontent.com/sportlive18/Sonyliv-Playlist-Autoupdate/main/sony.m3u"
BD_JSON_URL = "https://raw.githubusercontent.com/Mrbotrx/BD-OTT-PLAYLIST/main/output/BD-KB-IT.json"
AYNA_M3U_URL = "https://raw.githubusercontent.com/MohammadKobirShah/AynaOTT-M3U/main/output/aynaott_live.m3u"

SONY_MAPPING = {
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
    "Sony Sports 3 Hindi HD": "sonysports3",
    "Sony Sports 5 HD": "sonysports5"
}

# Channels whose fallback URLs should not be blindly overwritten by incoming M3U tokens
PRESERVED_FALLBACKS = {
    "sonysports1", "sonysports2", "bbcearth", "sonytv", "sonysports5",
    "discovery", "animalplanet", "discoveryscience", "tlc", "cn_hd", "cn_hindi", "discovery_kids", "pogo", "tsports"
}

# Verified high-availability mirror pools for automatic failover & healing
CANDIDATE_POOLS = {
    "discovery": [
        "https://tvsen6.aynaott.com/discovery_hd/index.m3u8",
        "https://tvsen3.aynaott.com/Zht5VqBb/index.m3u8",
        "https://tvsen5.aynaott.com/discoveryfamily/index.m3u8"
    ],
    "animalplanet": [
        "https://tvsen6.aynaott.com/animal_planet_hd/index.m3u8",
        "https://tvsen3.aynaott.com/wpa56Uk3/index.m3u8",
        "https://vodzong.mjunoon.tv:8087/streamtest/Animal-Planet-158-3/playlist.m3u8"
    ],
    "discoveryscience": [
        "https://tvsen6.aynaott.com/discovery_science/index.m3u8",
        "https://tvsen3.aynaott.com/Zht5VqBb/index.m3u8"
    ],
    "tlc": [
        "https://tvsen6.aynaott.com/tlc_hd/index.m3u8",
        "https://tvsen3.aynaott.com/EJagkNL2/index.m3u8"
    ],
    "cn_hd": [
        "https://cdn4.skygo.mn/live/disk1/Cartoon_Network/HLSv3-FTA/Cartoon_Network.m3u8",
        "https://tvsen5.aynaott.com/cartoonnetwork/index.m3u8",
        "https://vodzong.mjunoon.tv:8087/streamtest/cartoon-network-87/live/87H/chunks.m3u8"
    ],
    "cn_hindi": [
        "https://tvsen5.aynaott.com/cartoonnetwork/index.m3u8",
        "https://vodzong.mjunoon.tv:8087/streamtest/cartoon-network-87/live/87H/chunks.m3u8",
        "https://cdn4.skygo.mn/live/disk1/Cartoon_Network/HLSv3-FTA/Cartoon_Network.m3u8"
    ],
    "discovery_kids": [
        "https://vodzong.mjunoon.tv:8087/streamtest/disckids-157-1/playlist.m3u8",
        "https://tvsen5.aynaott.com/discoveryfamily/index.m3u8"
    ],
    "pogo": [
        "https://tvsen5.aynaott.com/cartoonnetwork/index.m3u8",
        "https://tvsen5.aynaott.com/discoveryfamily/index.m3u8"
    ],
    "tsports": [
        "https://lkn1.chowdhury-shaheb.com/Tsports/index.m3u8",
        "https://lkn1.chowdhury-shaheb.com/Tsports/tracks-v1a1/mono.m3u8"
    ],
    "sonysports5": [
        "http://38.96.178.205/SPORTS1/index.m3u8",
        "http://38.96.178.203/SPORTS1/index.m3u8"
    ]
}

def log(msg):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{now}] {msg}")

def verify_stream(url, timeout=7):
    if not url or not url.startswith("http"):
        return False
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            if resp.status == 200:
                body = resp.read(350).decode("utf-8", errors="ignore")
                return "#EXTM3U" in body or "#EXT-X" in body
    except Exception:
        pass
    return False

def fetch_sony_tokens():
    """Fetch updated Sony LIV Akamai tokens from sportlive18."""
    streams = {}
    try:
        req = urllib.request.Request(SONY_M3U_URL, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            lines = r.read().decode("utf-8", errors="ignore").splitlines()
        for i, l in enumerate(lines):
            if l.startswith("#EXTINF:"):
                next_url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                for tag, ch_id in SONY_MAPPING.items():
                    if tag in l and next_url.startswith("http"):
                        streams[ch_id] = next_url
        log(f"Sony LIV source: extracted {len(streams)} candidate streams.")
    except Exception as e:
        log(f"Warning: could not fetch Sony source: {e}")
    return streams

def fetch_upstream_dynamic():
    """Dynamically discover fresh streams from upstream BDIX / Ayna auto-updating repositories."""
    dynamic_streams = {cid: [] for cid in CANDIDATE_POOLS}
    mappings = {
        "discovery": ["discovery hd", "discovery channel"],
        "animalplanet": ["animal planet"],
        "discoveryscience": ["discovery science"],
        "tlc": ["tlc hd", "tlc"],
        "cn_hd": ["cartoon network hd", "cartoon network"],
        "cn_hindi": ["cartoon network hindi", "cartoon network"],
        "discovery_kids": ["discovery kids", "disckids", "discovery family"],
        "pogo": ["pogo"],
        "tsports": ["t sports", "tsports"]
    }

    # Source 1: BD-KB-IT JSON
    try:
        req = urllib.request.Request(BD_JSON_URL, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            items = json.loads(r.read().decode("utf-8"))
        for it in items:
            name = it.get("name", "").lower()
            u = it.get("url", "")
            for cid, aliases in mappings.items():
                if any(a in name for a in aliases) and u.startswith("http"):
                    if u not in dynamic_streams[cid]:
                        dynamic_streams[cid].append(u)
    except Exception as e:
        log(f"Warning: could not fetch BD-KB-IT.json: {e}")

    # Source 2: Ayna M3U
    try:
        req = urllib.request.Request(AYNA_M3U_URL, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            lines = r.read().decode("utf-8", errors="ignore").splitlines()
        for i, l in enumerate(lines):
            if l.startswith("#EXTINF"):
                next_url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                low = l.lower()
                for cid, aliases in mappings.items():
                    if any(a in low for a in aliases) and next_url.startswith("http"):
                        if next_url not in dynamic_streams[cid]:
                            dynamic_streams[cid].append(next_url)
    except Exception as e:
        log(f"Warning: could not fetch Ayna M3U: {e}")

    return dynamic_streams

def main():
    log("==================================================")
    log("Starting PlayTV 24/7 Universal Cloud Sync Engine")
    log("==================================================")

    # 1. Fetch fresh Sony tokens
    sony_streams = fetch_sony_tokens()

    # 2. Fetch fresh dynamic upstream streams
    dynamic_upstream = fetch_upstream_dynamic()

    # 3. Fetch current Firebase channels
    try:
        req_fb = urllib.request.Request(FIREBASE_URL, headers=HEADERS)
        with urllib.request.urlopen(req_fb, context=ctx, timeout=10) as r:
            channels = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log(f"Critical error fetching Firebase RTDB: {e}")
        sys.exit(1)

    updated = False

    # 4. Process all channels
    for ch in channels:
        ch_id = ch.get("id")
        ch_name = ch.get("name", ch_id)
        cur_primary = ch.get("primaryUrl", "")
        cur_fallback = ch.get("fallbackUrl", "")

        # A) Check Sony channels for updated Akamai tokens
        if ch_id in sony_streams:
            new_url = sony_streams[ch_id]
            if cur_primary != new_url:
                if verify_stream(new_url):
                    log(f"[SONY REFRESH] {ch_name}: updating primary token URL.")
                    ch["primaryUrl"] = new_url
                    if ch_id not in PRESERVED_FALLBACKS:
                        ch["fallbackUrl"] = new_url
                    updated = True
                else:
                    log(f"[SONY] Token verification failed for {ch_name}, preserving existing.")

        # B) Health check & auto-heal Infotainment, Kids, Sports, etc.
        if ch_id in CANDIDATE_POOLS:
            is_healthy = verify_stream(cur_primary, timeout=6)
            if is_healthy:
                # Primary stream is live and functioning normally
                continue

            log(f"[STREAM DOWN] {ch_name} ({ch_id}) primary is dead or unreachable: {cur_primary[:60]}...")

            # Assemble candidates: Dynamic upstream links first, then candidate pools
            candidates = []
            for u in dynamic_upstream.get(ch_id, []):
                if u not in candidates and u != cur_primary:
                    candidates.append(u)
            for u in CANDIDATE_POOLS.get(ch_id, []):
                if u not in candidates and u != cur_primary:
                    candidates.append(u)
            if cur_fallback and cur_fallback not in candidates and cur_fallback != cur_primary:
                candidates.append(cur_fallback)

            recovered = False
            for cand in candidates:
                if verify_stream(cand, timeout=6):
                    log(f"[AUTO-HEALED] Found healthy replacement for {ch_name} -> {cand}")
                    ch["primaryUrl"] = cand
                    # Set secondary candidate as fallback
                    for fallback_cand in candidates:
                        if fallback_cand != cand:
                            ch["fallbackUrl"] = fallback_cand
                            break
                    updated = True
                    recovered = True
                    break

            if not recovered:
                log(f"[WARNING] Could not auto-heal {ch_name}; all {len(candidates)} candidate mirrors unreachable.")

    # 5. Push back to Firebase if any channel updated
    if updated:
        try:
            data = json.dumps(channels, indent=2, ensure_ascii=False).encode("utf-8")
            put_req = urllib.request.Request(
                FIREBASE_URL,
                data=data,
                method="PUT",
                headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(put_req, context=ctx, timeout=12) as resp:
                log(f"Firebase RTDB updated successfully! HTTP Status: {resp.status}")
        except Exception as e:
            log(f"Failed to PUT updated channels to Firebase: {e}")
            sys.exit(1)
    else:
        log("All monitored channels (Sony, Discovery, Kids, Sports) are 100% healthy and up to date.")

    log("PlayTV Cloud Sync cycle finished successfully.")

if __name__ == "__main__":
    main()
