from flask import Flask, render_template, request, jsonify
import pandas as pd
import requests
import html
import time
import re
import sys
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Try importing google-genai for Gemini AI features
try:
    from google import genai
    HAS_GEMINI_SDK = True
except ImportError:
    HAS_GEMINI_SDK = False

app = Flask(__name__)
analyzer = SentimentIntensityAnalyzer()

# --- HELPER FUNCTIONS ---
def format_num(num):
    if num is None:
        return "N/A"
    num = float(num)
    if num >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(int(num))


def extract_video_id(url_or_id):
    if not url_or_id:
        return ""
    pattern = r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url_or_id.strip())
    return match.group(1) if match else url_or_id.strip()


# --- REQUESTS SESSION ENGINE ---
def get_requests_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YouTubeIntel/1.0"})
    return session

session = get_requests_session()


def resolve_channel_id(api_key, channel_handle_or_name):
    url = "https://www.googleapis.com/youtube/v3/search"
    clean_name = channel_handle_or_name.lstrip("@").strip()
    params = {
        "q": clean_name,
        "type": "channel",
        "part": "snippet",
        "maxResults": 1,
        "key": api_key
    }
    try:
        resp = session.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                snippet = items[0]["snippet"]
                return items[0]["snippet"]["channelId"], snippet.get("title", clean_name)
    except Exception:
        pass
    return None, clean_name


def fetch_latest_channel_videos(api_key, channel_id, max_results=6):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "channelId": channel_id,
        "order": "date",
        "type": "video",
        "part": "snippet",
        "maxResults": max_results,
        "key": api_key
    }
    resp = session.get(url, params=params, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("items", [])
    return []


def search_youtube_videos(api_key, query, max_results=6, order="relevance", exclude_channel_name="", retries=3):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": max_results * 2 if exclude_channel_name else max_results,
        "order": order,
        "relevanceLanguage": "en",
        "key": api_key
    }
    
    last_err = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                raw_items = resp.json().get("items", [])
                if not exclude_channel_name.strip():
                    return raw_items[:max_results]
                
                ex_clean = exclude_channel_name.lstrip("@").strip().lower()
                filtered = []
                for item in raw_items:
                    ch_title = item.get("snippet", {}).get("channelTitle", "").lower()
                    if ex_clean not in ch_title:
                        filtered.append(item)
                    if len(filtered) >= max_results:
                        break
                return filtered
            else:
                err_data = resp.json().get("error", {})
                raise Exception(f"HTTP {resp.status_code}: {err_data.get('message', resp.text)}")
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.0)
            else:
                raise last_err


def get_video_details(api_key, video_ids, retries=3):
    if not video_ids:
        return {}
    
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "id": ",".join(video_ids),
        "part": "snippet,statistics",
        "key": api_key
    }
    
    last_err = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                details = {}
                for item in resp.json().get("items", []):
                    v_id = item["id"]
                    stats = item.get("statistics", {})
                    snippet = item.get("snippet", {})
                    
                    views = int(stats.get("viewCount", 0))
                    likes = int(stats.get("likeCount", 0)) if "likeCount" in stats else 0
                    comments = int(stats.get("commentCount", 0)) if "commentCount" in stats else 0
                    
                    ratio = (likes / comments) if comments > 0 else (float(likes) if likes > 0 else 0.0)
                    
                    details[v_id] = {
                        "title": html.unescape(snippet.get("title", "")),
                        "channel": snippet.get("channelTitle", ""),
                        "published": snippet.get("publishedAt", "")[:10],
                        "description": snippet.get("description", ""),
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                        "likes_per_comment": ratio,
                        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                    }
                return details
            else:
                err_data = resp.json().get("error", {})
                raise Exception(f"HTTP {resp.status_code}: {err_data.get('message', resp.text)}")
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.0)
            else:
                raise last_err


def fetch_and_analyze_comments(api_key, video_id, max_comments=50, retries=2):
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "videoId": video_id,
        "part": "snippet",
        "maxResults": max_comments,
        "textFormat": "plainText",
        "key": api_key
    }
    
    comments_list = []
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    top_comment = item["snippet"]["topLevelComment"]["snippet"]
                    text = top_comment.get("textDisplay", "")
                    author = top_comment.get("authorDisplayName", "Anonymous")
                    likes = top_comment.get("likeCount", 0)
                    
                    if not text.strip():
                        continue
                    
                    score = analyzer.polarity_scores(text)["compound"]
                    
                    comments_list.append({
                        "author": author,
                        "text": text,
                        "score": score,
                        "likes": likes
                    })
                return comments_list, "ok"
            else:
                err_data = resp.json().get("error", {})
                msg = err_data.get("message", "")
                if resp.status_code == 403 and ("commentsDisabled" in msg or "disabled comments" in msg.lower()):
                    return [], "disabled"
                return [], f"error: HTTP {resp.status_code} {msg}"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.0)
            else:
                return [], f"error: {e}"
                
    return comments_list, "ok"


def run_transcript_and_narrative_analysis(api_key, video_title, description, positive_comments, negative_comments):
    """Call Google Gemini API for deep Transcript, Topic & Both-Sides Narrative Analysis."""
    if not HAS_GEMINI_SDK or not api_key:
        # VADER Fallback summary if Gemini is disabled
        desc_score = analyzer.polarity_scores(description)["compound"] if description else 0.0
        vibe_str = "🟢 Positive Tone" if desc_score > 0.05 else ("🔴 Critical Tone" if desc_score < -0.05 else "⚪ Neutral Tone")
        fallback_msg = f"📜 **Video Overview & Topic Analysis**: {description[:280]}...\n\n• **Spoken Tone**: {vibe_str} (Score: {desc_score:+.2f})\n• **Key Topic Context**: Analysis extracted from video description & comment sentiment."
        return fallback_msg, "ok"
        
    try:
        client = genai.Client(api_key=api_key)
        pos_sample = "\n".join([f"- {c['text']}" for c in positive_comments[:5]])
        neg_sample = "\n".join([f"- {c['text']}" for c in negative_comments[:5]])
        
        prompt = f"""
Perform a deep Video Transcript, Topic & Both-Sides Audience Analysis for:

VIDEO TITLE: "{video_title}"
DESCRIPTION / TRANSCRIPT OVERVIEW: "{description[:800] if description else 'No description available'}"

AUDIENCE POSITIVE FEEDBACK SAMPLE:
{pos_sample if pos_sample else 'None detected'}

AUDIENCE NEGATIVE FEEDBACK SAMPLE:
{neg_sample if neg_sample else 'None detected'}

Generate a structured 4-part intelligence breakdown:
1. 📜 **Transcript & Topic Breakdown**: What is this video's core subject and main points?
2. 🟢 **Positive Audience Perspective**: Key reasons viewers agree, praise, or support the creator.
3. 🔴 **Negative Audience Perspective**: Key points of disagreement, criticism, or debate.
4. ⚖️ **Executive Verdict**: Overall consensus rating and audience reaction.
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text, "ok"
    except Exception as e:
        err_str = str(e)
        if "API_KEY_SERVICE_BLOCKED" in err_str or "PERMISSION_DENIED" in err_str:
            return None, "blocked"
        return None, f"error: {e}"


def get_demo_video_data():
    return {
        "demo_vid_1": {
            "title": "DarkViperAU Commentary Response & Drama Breakdown",
            "channel": "Commentary Corner",
            "published": "2026-08-15",
            "description": "In this video we analyze DarkViperAU's recent commentary on content reaction dynamics, speedrunning history, and YouTube fair use debates.",
            "views": 320000,
            "likes": 22400,
            "comments": 1850,
            "likes_per_comment": 12.11,
            "comments_data": [
                {"author": "SpeedrunFan", "text": "DarkViperAU raises really fair points about content reaction dynamics here.", "score": 0.78, "likes": 510},
                {"author": "GtaLover99", "text": "Great explanation! People are misrepresenting what he actually said.", "score": 0.68, "likes": 230},
                {"author": "Critic_John", "text": "He is overreacting as usual and taking minor internet tweets way too seriously.", "score": -0.72, "likes": 180},
                {"author": "Debater_X", "text": "Completely wrong comparison. His argument falls apart if you look at the stats.", "score": -0.81, "likes": 95}
            ]
        },
        "demo_vid_2": {
            "title": "DarkViperAU Latest Upload: GTA 5 Speedrun World Record Attempt",
            "channel": "DarkViperAU",
            "published": "2026-09-01",
            "description": "Attempting the GTA V No Hit World Record! We breakdown mission strategies, RNG manipulation, and tricks in Los Santos.",
            "views": 450000,
            "likes": 38000,
            "comments": 2100,
            "likes_per_comment": 18.09,
            "comments_data": [
                {"author": "MattoSuperFan", "text": "Matto's speedrun RNG luck was insane in this run! What a legend.", "score": 0.89, "likes": 840},
                {"author": "ViperArmy", "text": "The patience required for this strategy is unreal. Best creator on YouTube!", "score": 0.91, "likes": 420},
                {"author": "RngHater", "text": "That choke at the end of mission 45 was painful to watch.", "score": -0.55, "likes": 40}
            ]
        }
    }


# --- FLASK ROUTES ---
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/scan", methods=["POST"])
def scan_api():
    data = request.json or {}
    
    use_youtube_api = data.get("use_youtube_api", True)
    use_gemini_api = data.get("use_gemini_api", True)
    yt_api_key = data.get("yt_api_key", "").strip()
    gemini_api_key = data.get("gemini_api_key", "").strip()
    
    search_mode = data.get("search_mode", "creator")
    target_creator = data.get("target_creator", "DarkViperAU")
    exclude_creator = data.get("exclude_creator", "")
    video_url_id = data.get("video_url_id", "")
    topic_query = data.get("topic_query", "South Africa commentary")
    
    video_limit = int(data.get("video_limit", 6))
    sort_order = data.get("sort_order", "relevance")
    max_comments = int(data.get("max_comments", 50))
    
    video_details = {}
    
    if use_youtube_api:
        if not yt_api_key:
            return jsonify({"error": "Please provide a valid YouTube Data API Key."}), 400
            
        try:
            if search_mode == "creator":
                ch_id, ch_title = resolve_channel_id(yt_api_key, target_creator)
                if not ch_id:
                    return jsonify({"error": f"Could not find YouTube channel: '{target_creator}'"}), 404
                raw_items = fetch_latest_channel_videos(yt_api_key, ch_id, max_results=video_limit)
                video_ids = [item["id"]["videoId"] for item in raw_items if item.get("id", {}).get("videoId")]
            elif search_mode == "url":
                v_id = extract_video_id(video_url_id)
                if not v_id:
                    return jsonify({"error": "Invalid YouTube Video Link or ID"}), 400
                video_ids = [v_id]
            else:
                q = topic_query if topic_query else "commentary"
                raw_items = search_youtube_videos(yt_api_key, q, max_results=video_limit, order=sort_order, exclude_channel_name=exclude_creator)
                video_ids = [item["id"]["videoId"] for item in raw_items if item.get("id", {}).get("videoId")]
                
            if not video_ids:
                return jsonify({"error": "No matching videos found for your search options."}), 404
                
            # Fetch ALL requested video details without slicing
            video_details = get_video_details(yt_api_key, video_ids[:video_limit])
        except Exception as e:
            return jsonify({"error": f"YouTube API Error: {str(e)}"}), 500
    else:
        video_details = get_demo_video_data()

    # Process and build response list
    videos_result = []
    total_views = 0
    total_likes = 0
    total_comments = 0

    for v_id, details in video_details.items():
        total_views += details["views"]
        total_likes += details["likes"]
        total_comments += details["comments"]
        
        comments = []
        comment_status = "ok"
        
        if use_youtube_api and not v_id.startswith("demo"):
            comments, comment_status = fetch_and_analyze_comments(yt_api_key, v_id, max_comments=max_comments)
        else:
            comments = details.get("comments_data", [])

        pos_comments = [c for c in comments if c["score"] >= 0.05]
        neg_comments = [c for c in comments if c["score"] <= -0.05]
        neu_comments = [c for c in comments if -0.05 < c["score"] < 0.05]
        
        pos_comments.sort(key=lambda x: x["score"], reverse=True)
        neg_comments.sort(key=lambda x: x["score"])
        
        total_c = len(comments)
        pos_pct = round((len(pos_comments) / total_c) * 100, 1) if total_c > 0 else 0
        neg_pct = round((len(neg_comments) / total_c) * 100, 1) if total_c > 0 else 0
        neu_pct = round((len(neu_comments) / total_c) * 100, 1) if total_c > 0 else 0
        avg_vibe = round(sum(c["score"] for c in comments) / total_c, 2) if total_c > 0 else 0.0

        # Transcript & Narrative Analysis
        g_key = gemini_api_key if gemini_api_key else yt_api_key
        ai_summary, ai_status = run_transcript_and_narrative_analysis(g_key, details["title"], details.get("description", ""), pos_comments, neg_comments)

        ratio_val = details["likes_per_comment"]
        ratio_label = "🔥 High Approval" if ratio_val > 15 else ("💬 High Discussion/Debate" if ratio_val < 3 else "👍 Balanced Interaction")

        videos_result.append({
            "video_id": v_id,
            "title": details["title"],
            "channel": details["channel"],
            "published": details["published"],
            "description": details.get("description", ""),
            "views": details["views"],
            "views_formatted": format_num(details["views"]),
            "likes": details["likes"],
            "likes_formatted": format_num(details["likes"]),
            "comments_count": details["comments"],
            "comments_formatted": format_num(details["comments"]),
            "likes_per_comment": round(ratio_val, 2),
            "ratio_label": ratio_label,
            "comment_status": comment_status,
            "total_comments_scanned": total_c,
            "pos_pct": pos_pct,
            "neg_pct": neg_pct,
            "neu_pct": neu_pct,
            "avg_vibe": avg_vibe,
            "positive_comments": pos_comments[:5],
            "negative_comments": neg_comments[:5],
            "all_comments": comments,
            "ai_summary": ai_summary,
            "ai_status": ai_status
        })

    avg_ratio = round((total_likes / total_comments), 2) if total_comments > 0 else 0.0

    return jsonify({
        "summary": {
            "scanned_count": len(videos_result),
            "total_views": format_num(total_views),
            "total_likes": format_num(total_likes),
            "total_comments": format_num(total_comments),
            "avg_likes_per_comment": avg_ratio
        },
        "videos": videos_result
    })


# --- ENTRY POINT & THREAD SAFETY ---
if __name__ == "__main__":
    if "streamlit" not in sys.modules and not any("streamlit" in arg for arg in sys.argv):
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    else:
        print("Notice: app.py is a Flask Application. Please run using: python app.py")
