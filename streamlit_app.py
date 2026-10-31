import streamlit as st
import pandas as pd
import requests
import html
import time
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Try importing google-genai for Gemini AI features
try:
    from google import genai
    HAS_GEMINI_SDK = True
except ImportError:
    HAS_GEMINI_SDK = False

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="YouTube Intelligence & Sentiment Dashboard",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS STYLING ---
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background-color: #1e222d;
        border: 1px solid #2e3440;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .metric-title {
        color: #9ba1b0;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value { color: #ffffff; font-size: 1.4rem; font-weight: 700; }
    .positive-comment {
        background-color: #12281e;
        border-left: 4px solid #2e7d32;
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .negative-comment {
        background-color: #2b1717;
        border-left: 4px solid #c62828;
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .comment-author { font-size: 0.8rem; font-weight: 600; color: #e0e0e0; }
    .comment-text { font-size: 0.9rem; color: #d1d5db; margin-top: 4px; white-space: pre-wrap; }
    .score-badge-pos {
        background-color: #1b4332; color: #52b788; font-size: 0.75rem;
        padding: 2px 8px; border-radius: 12px; font-weight: bold; float: right;
    }
    .score-badge-neg {
        background-color: #4a1515; color: #ff7b7b; font-size: 0.75rem;
        padding: 2px 8px; border-radius: 12px; font-weight: bold; float: right;
    }
    .ratio-badge {
        background: linear-gradient(135deg, #3a0ca3, #4361ee);
        color: white; padding: 4px 10px; border-radius: 8px;
        font-weight: bold; display: inline-block; font-size: 0.9rem;
    }
    .ai-box {
        background: linear-gradient(135deg, #1f2937, #111827);
        border: 1px solid #3b82f6; border-radius: 10px; padding: 16px; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)


# --- HELPER FUNCTIONS ---
def format_num(num):
    if num is None: return "N/A"
    num = float(num)
    if num >= 1_000_000: return f"{num / 1_000_000:.2f}M"
    elif num >= 1_000: return f"{num / 1_000:.1f}K"
    return str(int(num))


def extract_video_id(url_or_id):
    if not url_or_id: return ""
    pattern = r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url_or_id.strip())
    return match.group(1) if match else url_or_id.strip()


@st.cache_resource
def get_sentiment_analyzer():
    return SentimentIntensityAnalyzer()

analyzer = get_sentiment_analyzer()

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YouTubeIntel/1.0"})


def resolve_channel_id(api_key, channel_handle_or_name):
    url = "https://www.googleapis.com/youtube/v3/search"
    clean_name = channel_handle_or_name.lstrip("@").strip()
    params = {"q": clean_name, "type": "channel", "part": "snippet", "maxResults": 1, "key": api_key}
    try:
        resp = session.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                return items[0]["snippet"]["channelId"], items[0]["snippet"].get("title", clean_name)
    except Exception: pass
    return None, clean_name


def fetch_latest_channel_videos(api_key, channel_id, max_results=5):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {"channelId": channel_id, "order": "date", "type": "video", "part": "snippet", "maxResults": max_results, "key": api_key}
    resp = session.get(url, params=params, timeout=10)
    if resp.status_code == 200: return resp.json().get("items", [])
    return []


def search_youtube_videos(api_key, query, max_results=10, order="relevance", exclude_channel_name="", retries=3):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {"q": query, "part": "snippet", "type": "video", "maxResults": max_results * 2 if exclude_channel_name else max_results, "order": order, "relevanceLanguage": "en", "key": api_key}
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                raw_items = resp.json().get("items", [])
                if not exclude_channel_name.strip(): return raw_items[:max_results]
                ex_clean = exclude_channel_name.lstrip("@").strip().lower()
                filtered = [i for i in raw_items if ex_clean not in i.get("snippet", {}).get("channelTitle", "").lower()]
                return filtered[:max_results]
        except Exception:
            if attempt < retries - 1: time.sleep(1.0)
    return []


def get_video_details(api_key, video_ids, retries=3):
    if not video_ids: return {}
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"id": ",".join(video_ids), "part": "snippet,statistics", "key": api_key}
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
                        "views": views, "likes": likes, "comments": comments,
                        "likes_per_comment": ratio,
                        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                    }
                return details
        except Exception:
            if attempt < retries - 1: time.sleep(1.0)
    return {}


def fetch_and_analyze_comments(api_key, video_id, max_comments=50, retries=2):
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {"videoId": video_id, "part": "snippet", "maxResults": max_comments, "textFormat": "plainText", "key": api_key}
    comments_list = []
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    top_comment = item["snippet"]["topLevelComment"]["snippet"]
                    text = top_comment.get("textDisplay", "")
                    if not text.strip(): continue
                    comments_list.append({
                        "author": top_comment.get("authorDisplayName", "Anonymous"),
                        "text": text,
                        "score": analyzer.polarity_scores(text)["compound"],
                        "likes": top_comment.get("likeCount", 0)
                    })
                return comments_list, "ok"
            elif resp.status_code == 403: return [], "disabled"
        except Exception:
            if attempt < retries - 1: time.sleep(1.0)
    return comments_list, "ok"


def get_demo_video_data():
    return {
        "demo_vid_1": {
            "title": "DarkViperAU Commentary Response & Drama Breakdown",
            "channel": "Commentary Corner", "published": "2026-08-15",
            "views": 320000, "likes": 22400, "comments": 1850, "likes_per_comment": 12.11,
            "comments_data": [
                {"author": "SpeedrunFan", "text": "DarkViperAU raises really fair points about content reaction dynamics here.", "score": 0.78, "likes": 510},
                {"author": "GtaLover99", "text": "Great explanation! People are misrepresenting what he actually said.", "score": 0.68, "likes": 230},
                {"author": "Critic_John", "text": "He is overreacting as usual and taking minor internet tweets way too seriously.", "score": -0.72, "likes": 180}
            ]
        }
    }


# --- SIDEBAR & DASHBOARD ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/e/ef/Youtube_logo.png", width=160)
    st.title("Settings & Search Modes")
    search_mode = st.radio("Select Search Target", options=["🎯 Specific Creator (Latest Uploads)", "🗣️ Outside Commentary (Exclude Creator)", "🔗 Direct Video URL / Video ID", "🔍 General Topic Search"])
    
    target_creator, exclude_creator, video_url_id, topic_query = "", "", "", ""
    if search_mode == "🎯 Specific Creator (Latest Uploads)": target_creator = st.text_input("Creator Channel / Handle", value="DarkViperAU")
    elif search_mode == "🗣️ Outside Commentary (Exclude Creator)":
        topic_query = st.text_input("Commentary Search Topic", value="DarkViperAU commentary")
        exclude_creator = st.text_input("Exclude Creator Channel", value="DarkViperAU")
    elif search_mode == "🔗 Direct Video URL / Video ID": video_url_id = st.text_input("YouTube Video Link or ID", value="https://www.youtube.com/watch?v=1FYru64kUF8")
    else: topic_query = st.text_input("Search Topic / Keyword", value="South Africa commentary")

    st.divider()
    use_youtube_api = st.checkbox("✅ Enable YouTube Data API v3", value=True)
    use_gemini_api = st.checkbox("✅ Enable Google Gemini AI", value=True)
    yt_api_key = st.text_input("YouTube Data API Key", value="AIzaSyAuWrB7krwRoTptAuwPeJxSV-WXyFd3w74", type="password")
    gemini_api_key = st.text_input("Google Gemini API Key (Optional)", value="", type="password")
    video_limit = st.slider("Number of Videos", min_value=1, max_value=20, value=6, step=1)
    max_comment_scan = st.slider("Comments Scanned Per Video", min_value=10, max_value=100, value=50, step=10)
    run_button = st.button("🚀 Run Intelligence Scan", use_container_width=True, type="primary")

st.title("📺 YouTube Intelligence & Audience Sentiment Dashboard")
st.markdown("Scan specific YouTube creators, analyze outside commentary, track **Likes-to-Comments Ratios**, and inspect **Positive vs Negative** audience feedback.")

if run_button:
    video_details = {}
    if use_youtube_api:
        key = yt_api_key.strip()
        if search_mode == "🎯 Specific Creator (Latest Uploads)":
            ch_id, ch_title = resolve_channel_id(key, target_creator)
            if ch_id:
                raw_items = fetch_latest_channel_videos(key, ch_id, max_results=video_limit)
                video_ids = [i["id"]["videoId"] for i in raw_items if i.get("id", {}).get("videoId")]
                video_details = get_video_details(key, video_ids)
        elif search_mode == "🔗 Direct Video URL / Video ID":
            v_id = extract_video_id(video_url_id)
            if v_id: video_details = get_video_details(key, [v_id])
        else:
            q = topic_query if topic_query else "commentary"
            raw_items = search_youtube_videos(key, q, max_results=video_limit, exclude_channel_name=exclude_creator)
            video_ids = [i["id"]["videoId"] for i in raw_items if i.get("id", {}).get("videoId")]
            video_details = get_video_details(key, video_ids)
    else: video_details = get_demo_video_data()

    if not video_details:
        st.warning("No matching videos found.")
    else:
        st.header("📊 Scanned Overview")
        total_views = sum(v["views"] for v in video_details.values())
        total_likes = sum(v["likes"] for v in video_details.values())
        total_comments = sum(v["comments"] for v in video_details.values())
        avg_ratio = (total_likes / total_comments) if total_comments > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Videos Scanned", len(video_details))
        c2.metric("Total Views", format_num(total_views))
        c3.metric("Total Likes", format_num(total_likes))
        c4.metric("Avg Likes / Comment", f"{avg_ratio:.2f}")

        st.divider()
        st.header("🎥 Detailed Video Analysis")

        for v_id, details in video_details.items():
            col1, col2 = st.columns([1, 1])
            with col1:
                if use_youtube_api and not v_id.startswith("demo"): st.video(f"https://www.youtube.com/watch?v={v_id}")
                else: st.image("https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg", caption=details["title"])
            with col2:
                st.subheader(details["title"])
                st.write(f"👤 Channel: **{details['channel']}** | 📅 Published: {details['published']}")
                st.metric("Likes / Comment Ratio", f"{details['likes_per_comment']:.2f}")

            comments, status = fetch_and_analyze_comments(yt_api_key.strip(), v_id, max_comments=max_comment_scan) if use_youtube_api and not v_id.startswith("demo") else (details.get("comments_data", []), "ok")
            
            if comments:
                pos = [c for c in comments if c["score"] >= 0.05]
                neg = [c for c in comments if c["score"] <= -0.05]
                
                col_p, col_n = st.columns(2)
                with col_p:
                    st.markdown("#### 🟢 Top Positive Comments")
                    for c in pos[:5]:
                        st.markdown(f"**{c['author']}** (👍 {c['likes']}): {c['text']}")
                with col_n:
                    st.markdown("#### 🔴 Top Negative Comments")
                    for c in neg[:5]:
                        st.markdown(f"**{c['author']}** (👍 {c['likes']}): {c['text']}")
            st.divider()
