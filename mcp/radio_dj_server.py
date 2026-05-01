from __future__ import annotations

import json
import random
from pathlib import Path


try:
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'mcp'. Install with: pip install mcp"
    ) from exc


mcp = FastMCP("radio-dj")

# Curated playlists by vibe/genre
PLAYLIST_DB = {
    "chill": {
        "name": "Chill Vibes",
        "tracks": [
            {"title": "Weightless", "artist": "Marconi Union", "duration": "8:00"},
            {"title": "Holocene", "artist": "Bon Iver", "duration": "5:36"},
            {"title": "River", "artist": "Joni Mitchell", "duration": "4:00"},
            {"title": "The Night We Met", "artist": "Lord Huron", "duration": "3:28"},
            {"title": "Mystery of Love", "artist": "Sufjan Stevens", "duration": "4:08"},
        ],
    },
    "focus": {
        "name": "Deep Focus",
        "tracks": [
            {"title": "Experience", "artist": "Ludovico Einaudi", "duration": "5:15"},
            {"title": "Nuvole Bianche", "artist": "Ludovico Einaudi", "duration": "5:57"},
            {"title": "Gymnopédie No.1", "artist": "Erik Satie", "duration": "3:56"},
            {"title": "Clair de Lune", "artist": "Claude Debussy", "duration": "5:09"},
            {"title": "Comptine d'un autre été", "artist": "Yann Tiersen", "duration": "2:20"},
        ],
    },
    "energetic": {
        "name": "Energy Boost",
        "tracks": [
            {"title": "Don't Stop Me Now", "artist": "Queen", "duration": "3:29"},
            {"title": "Uptown Funk", "artist": "Bruno Mars", "duration": "4:30"},
            {"title": "Shut Up and Dance", "artist": "WALK THE MOON", "duration": "3:19"},
            {"title": "Can't Hold Us", "artist": "Macklemore", "duration": "4:18"},
            {"title": "Blinding Lights", "artist": "The Weeknd", "duration": "3:20"},
        ],
    },
    "rock": {
        "name": "Classic Rock",
        "tracks": [
            {"title": "Bohemian Rhapsody", "artist": "Queen", "duration": "5:55"},
            {"title": "Hotel California", "artist": "Eagles", "duration": "6:30"},
            {"title": "Stairway to Heaven", "artist": "Led Zeppelin", "duration": "8:02"},
            {"title": "Sweet Child O' Mine", "artist": "Guns N' Roses", "duration": "5:03"},
            {"title": "Smells Like Teen Spirit", "artist": "Nirvana", "duration": "5:01"},
        ],
    },
    "rainy": {
        "name": "Rainy Day",
        "tracks": [
            {"title": "Riders on the Storm", "artist": "The Doors", "duration": "7:14"},
            {"title": "Purple Rain", "artist": "Prince", "duration": "8:41"},
            {"title": "Set Fire to the Rain", "artist": "Adele", "duration": "4:02"},
            {"title": "November Rain", "artist": "Guns N' Roses", "duration": "8:57"},
            {"title": "Have You Ever Seen the Rain", "artist": "Creedence", "duration": "2:39"},
        ],
    },
    "study": {
        "name": "Study Beats",
        "tracks": [
            {"title": "Lo-fi Study Beats", "artist": "Chillhop", "duration": "3:00"},
            {"title": "Midnight City", "artist": "M83", "duration": "4:03"},
            {"title": "Intro", "artist": "The xx", "duration": "2:07"},
            {"title": "Teardrop", "artist": "Massive Attack", "duration": "5:31"},
            {"title": "Porcelain", "artist": "Moby", "duration": "6:26"},
        ],
    },
    "night": {
        "name": "Late Night",
        "tracks": [
            {"title": "Nightcall", "artist": "Kavinsky", "duration": "4:18"},
            {"title": "Midnight City", "artist": "M83", "duration": "4:03"},
            {"title": "Neon Lights", "artist": "Kraftwerk", "duration": "8:51"},
            {"title": "Instant Crush", "artist": "Daft Punk", "duration": "5:37"},
            {"title": "Space Song", "artist": "Beach House", "duration": "5:20"},
        ],
    },
    "workout": {
        "name": "Workout Pump",
        "tracks": [
            {"title": "Eye of the Tiger", "artist": "Survivor", "duration": "4:05"},
            {"title": "Lose Yourself", "artist": "Eminem", "duration": "5:26"},
            {"title": "Titanium", "artist": "David Guetta ft. Sia", "duration": "4:05"},
            {"title": "Power", "artist": "Kanye West", "duration": "4:52"},
            {"title": "Stronger", "artist": "Kanye West", "duration": "5:12"},
        ],
    },
}

# Vibe mapping from natural language
VIBE_MAP = {
    "chill": ["chill", "relax", "calm", "quiet", "peaceful", "安静", "放松", "轻松", "chill"],
    "focus": ["focus", "study", "concentrate", "work", "学习", "专注", "工作", "focus", "深度"],
    "energetic": ["energetic", "happy", "upbeat", "party", "开心", "嗨", "活力", "energy", "快乐"],
    "rock": ["rock", "band", "guitar", "摇滚", "乐队", "吉他", "rock"],
    "rainy": ["rain", "rainy", "雨", "雨天", "rainy", "下雨"],
    "study": ["study", "learn", "read", "学习", "读书", "study", "备考"],
    "night": ["night", "late", "sleep", "深夜", "晚上", "night", "午夜"],
    "workout": ["workout", "gym", "exercise", "sport", "运动", "健身", "跑步", "workout"],
}


def _detect_vibe(query: str) -> str:
    """Detect playlist vibe from natural language query."""
    q = query.lower()
    scores = {}
    for vibe, keywords in VIBE_MAP.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            scores[vibe] = score
    if scores:
        return max(scores, key=scores.get)
    return "chill"  # default


def _generate_dj_intro(vibe: str, user_location: str = "", user_mood: str = "") -> str:
    """Generate a radio DJ style intro for the playlist."""
    intros = {
        "chill": [
            "接下来是放松时间，给你挑了几首能让呼吸慢下来的曲子。",
            "现在放轻松，这些歌适合什么都不做的时候听。",
        ],
        "focus": [
            "进入专注模式，背景音乐不会抢你的注意力。",
            "学习工作专用歌单，没有歌词干扰，只有旋律陪伴。",
        ],
        "energetic": [
            "能量补给时间！这些歌能让你从椅子上弹起来。",
            "需要点动力？这个歌单就是为你准备的。",
        ],
        "rock": [
            "摇滚时间到！经典吉他 riff 和鼓点来了。",
            "这些歌适合大声听，或者在心里大声听。",
        ],
        "rainy": [
            "雨天窗边，配这些歌正好。",
            "雨天的氛围感，交给这几首来营造。",
        ],
        "study": [
            "学习背景音已就位，不会打扰你的思路。",
            "专注模式开启，音乐是你的白噪音。",
        ],
        "night": [
            "深夜电台时间，这些歌适合一个人听。",
            "夜色深了，让音乐陪你度过这段安静的时间。",
        ],
        "workout": [
            "动起来！这些节奏不会让你停下。",
            "运动模式开启，每一拍都在推你一把。",
        ],
    }
    base_intros = intros.get(vibe, intros["chill"])
    intro = random.choice(base_intros)
    
    if user_location:
        intro = f"{user_location}的听众你好，{intro}"
    if user_mood:
        intro = f"{intro} 感觉你今天{user_mood}，希望这些音乐刚好对味。"
    
    return intro


@mcp.tool()
def create_playlist(
    vibe: str = "",
    user_location: str = "",
    user_mood: str = "",
    preferred_artists: str = "",
    track_count: int = 5,
) -> dict:
    """Create a personalized playlist based on vibe, location, mood, and artist preferences.
    
    Args:
        vibe: Desired vibe (chill, focus, energetic, rock, rainy, study, night, workout)
        user_location: User's current location for contextual recommendations
        user_mood: User's current mood
        preferred_artists: Comma-separated list of preferred artists
        track_count: Number of tracks (1-10)
    """
    vibe_key = vibe.strip().lower() if vibe else "chill"
    if vibe_key not in PLAYLIST_DB:
        vibe_key = _detect_vibe(vibe)
    
    playlist = PLAYLIST_DB[vibe_key]
    track_count = max(1, min(10, int(track_count)))
    
    # If user mentioned specific artists, try to include them
    tracks = list(playlist["tracks"])
    if preferred_artists:
        preferred = [a.strip().lower() for a in preferred_artists.split(",")]
        # Shuffle and prioritize matching artists
        random.shuffle(tracks)
        matching = [t for t in tracks if any(p in t["artist"].lower() for p in preferred)]
        non_matching = [t for t in tracks if t not in matching]
        tracks = (matching + non_matching)[:track_count]
    else:
        random.shuffle(tracks)
        tracks = tracks[:track_count]
    
    intro = _generate_dj_intro(vibe_key, user_location, user_mood)
    
    return {
        "playlist_name": playlist["name"],
        "vibe": vibe_key,
        "dj_intro": intro,
        "track_count": len(tracks),
        "tracks": tracks,
        "total_duration": "~" + str(sum(int(t["duration"].split(":")[0]) for t in tracks)) + " min",
    }


@mcp.tool()
def get_artist_info(artist_name: str) -> dict:
    """Get information about a music artist/band and their representative works."""
    if not artist_name.strip():
        raise ValueError("artist_name is required")
    
    artist_lower = artist_name.strip().lower()
    
    # Known artist database
    artists_db = {
        "queen": {
            "name": "Queen",
            "genre": "Rock",
            "origin": "London, UK",
            "period": "1970-1995",
            "representative_works": [
                "Bohemian Rhapsody (1975) - 摇滚歌剧的巅峰",
                "We Will Rock You (1977) - 体育场 anthem",
                "We Are The Champions (1977) - 胜利之歌",
                "Don't Stop Me Now (1978) - 高能量代表作",
                "Under Pressure (1981, with David Bowie) - 经典合作",
            ],
            "style": "华丽摇滚、硬摇滚，融合了歌剧元素和强烈的人声和声",
        },
        "beatles": {
            "name": "The Beatles",
            "genre": "Rock / Pop",
            "origin": "Liverpool, UK",
            "period": "1960-1970",
            "representative_works": [
                "Hey Jude (1968) - 经典抒情",
                "Let It Be (1970) - 精神慰藉",
                "Yesterday (1965) - 史上被翻唱最多的歌",
                "A Day in the Life (1967) - Sgt. Pepper 代表作",
                "Come Together (1969) - 迷幻摇滚",
            ],
            "style": "从流行摇滚到迷幻摇滚，影响了整个现代音乐史",
        },
        "beyond": {
            "name": "Beyond",
            "genre": "Rock / Cantopop",
            "origin": "Hong Kong",
            "period": "1983-2005",
            "representative_works": [
                "海阔天空 (1993) - 精神图腾",
                "光辉岁月 (1990) - 致敬曼德拉",
                "真的爱你 (1989) - 母亲节经典",
                "喜欢你 (1988) - 情歌代表作",
                "Amani (1991) - 和平主题",
            ],
            "style": "粤语摇滚先驱，融合流行与摇滚，歌词充满人文关怀",
        },
    }
    
    info = artists_db.get(artist_lower, {
        "name": artist_name,
        "genre": "Unknown",
        "origin": "Unknown",
        "period": "Unknown",
        "representative_works": ["No detailed information available."],
        "style": "Information not in local database.",
    })
    
    return info


@mcp.tool()
def play_track(playlist_name: str = "", track_index: int = 0) -> dict:
    """Simulate playing a track from a playlist.
    
    Args:
        playlist_name: Name of the playlist
        track_index: Index of track to play (0-based)
    """
    return {
        "status": "playing",
        "playlist": playlist_name or "Unknown",
        "track_index": track_index,
        "message": f"Now playing track {track_index + 1} from '{playlist_name or 'Unknown'}'",
    }


@mcp.tool()
def suggest_music_for_scene(scene: str = "", time_of_day: str = "", weather: str = "") -> dict:
    """Suggest music based on current scene/context.
    
    Args:
        scene: Current activity (study, commute, workout, relax, etc.)
        time_of_day: morning, afternoon, evening, night
        weather: sunny, rainy, cloudy, etc.
    """
    scene_vibe_map = {
        "study": "study",
        "学习": "study",
        "work": "focus",
        "工作": "focus",
        "commute": "chill",
        "通勤": "chill",
        "workout": "workout",
        "运动": "workout",
        "健身": "workout",
        "relax": "chill",
        "放松": "chill",
        "party": "energetic",
        "聚会": "energetic",
    }
    
    vibe = scene_vibe_map.get(scene.lower(), "chill")
    
    # Weather override
    if weather.lower() in ["rainy", "rain", "雨", "下雨"]:
        vibe = "rainy"
    
    # Time override
    if time_of_day.lower() in ["night", "evening", "晚上", "深夜"]:
        if vibe == "chill":
            vibe = "night"
    
    playlist = PLAYLIST_DB[vibe]
    tracks = random.sample(playlist["tracks"], min(3, len(playlist["tracks"])))
    
    context_hint = f"{time_of_day} {weather} {scene}".strip()
    
    return {
        "context": context_hint,
        "suggested_vibe": vibe,
        "playlist_name": playlist["name"],
        "tracks": tracks,
        "message": f"Based on your scene ({context_hint}), try these:",
    }


if __name__ == "__main__":
    mcp.run()
