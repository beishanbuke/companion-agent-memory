"""Simple MCP tool caller for the prototype demo.

This is a lightweight in-process MCP client that directly implements
tool functions without requiring the 'mcp' package.
"""

from __future__ import annotations

import random
from typing import Any


# Curated playlists by vibe/genre (copied from radio_dj_server.py)
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

ARTISTS_DB = {
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


def _generate_dj_intro(vibe: str, user_location: str = "", user_mood: str = "") -> str:
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


def create_playlist(
    vibe: str = "",
    user_location: str = "",
    user_mood: str = "",
    preferred_artists: str = "",
    track_count: int = 5,
) -> dict:
    """Create a personalized playlist."""
    vibe_key = vibe.strip().lower() if vibe else "chill"
    if vibe_key not in PLAYLIST_DB:
        vibe_key = "chill"
    playlist = PLAYLIST_DB[vibe_key]
    track_count = max(1, min(10, int(track_count)))
    tracks = list(playlist["tracks"])
    if preferred_artists:
        preferred = [a.strip().lower() for a in preferred_artists.split(",")]
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


def get_artist_info(artist_name: str) -> dict:
    """Get information about a music artist/band."""
    if not artist_name.strip():
        return {"error": "artist_name is required"}
    artist_lower = artist_name.strip().lower()
    info = ARTISTS_DB.get(artist_lower, {
        "name": artist_name,
        "genre": "Unknown",
        "origin": "Unknown",
        "period": "Unknown",
        "representative_works": ["No detailed information available."],
        "style": "Information not in local database.",
    })
    return info


def execute_skill_mcp(skill_id: str, user_message: str, memory_context: dict[str, Any]) -> dict[str, Any]:
    """Execute MCP tools for a given skill."""
    if skill_id == "radio_dj":
        user_msg_lower = user_message.lower()
        artist = None
        for name in ["queen", "beatles", "beyond", "五月天", "周杰伦"]:
            if name in user_msg_lower:
                artist = name
                break
        vibe = "chill"
        if any(kw in user_msg_lower for kw in ["摇滚", "rock", "band", "乐队"]):
            vibe = "rock"
        elif any(kw in user_msg_lower for kw in ["学习", "study", "focus", "工作"]):
            vibe = "focus"
        elif any(kw in user_msg_lower for kw in ["运动", "workout", "健身", "gym"]):
            vibe = "workout"
        elif any(kw in user_msg_lower for kw in ["雨", "rain", "下雨"]):
            vibe = "rainy"
        elif any(kw in user_msg_lower for kw in ["晚上", "night", "深夜", "sleep"]):
            vibe = "night"
        elif any(kw in user_msg_lower for kw in ["嗨", "energetic", "party", "开心"]):
            vibe = "energetic"
        user_location = memory_context.get("home_city", "")
        result = create_playlist(
            vibe=vibe,
            user_location=user_location,
            preferred_artists=artist or "",
            track_count=5,
        )
        tool_result = {
            "tool_calls": [{"tool": "radio_dj.create_playlist", "arguments": {"vibe": vibe, "track_count": 5}}],
            "tool_results": [result],
            "formatted_context": f"""\
[电台DJ已为你创建歌单]
{result.get('dj_intro', '')}

歌单：{result.get('playlist_name', '')}
曲目：
"""
        }
        for i, track in enumerate(result.get('tracks', []), 1):
            tool_result["formatted_context"] += f"{i}. {track['artist']} - 《{track['title']}》 ({track['duration']})\n"
        return tool_result
    elif skill_id in ("playlist_builder", "radio_dj"):
        # Both skills use the same playlist creation logic
        user_msg_lower = user_message.lower()
        artist = None
        for name in ["queen", "beatles", "beyond", "五月天", "周杰伦"]:
            if name in user_msg_lower:
                artist = name
                break
        vibe = "chill"
        if any(kw in user_msg_lower for kw in ["摇滚", "rock", "band", "乐队"]):
            vibe = "rock"
        elif any(kw in user_msg_lower for kw in ["学习", "study", "focus", "工作"]):
            vibe = "focus"
        elif any(kw in user_msg_lower for kw in ["运动", "workout", "健身", "gym"]):
            vibe = "workout"
        elif any(kw in user_msg_lower for kw in ["雨", "rain", "下雨"]):
            vibe = "rainy"
        elif any(kw in user_msg_lower for kw in ["晚上", "night", "深夜", "sleep"]):
            vibe = "night"
        elif any(kw in user_msg_lower for kw in ["嗨", "energetic", "party", "开心"]):
            vibe = "energetic"
        user_location = memory_context.get("home_city", "")
        result = create_playlist(
            vibe=vibe,
            user_location=user_location,
            preferred_artists=artist or "",
            track_count=5,
        )
        tool_result = {
            "tool_calls": [{"tool": "radio_dj.create_playlist", "arguments": {"vibe": vibe, "track_count": 5}}],
            "tool_results": [result],
            "formatted_context": f"""\
[电台DJ已为你创建歌单]
{result.get('dj_intro', '')}

歌单：{result.get('playlist_name', '')}
曲目：
"""
        }
        for i, track in enumerate(result.get('tracks', []), 1):
            tool_result["formatted_context"] += f"{i}. {track['artist']} - 《{track['title']}》 ({track['duration']})\n"
        return tool_result
    return {"tool_calls": [], "tool_results": [], "formatted_context": ""}
