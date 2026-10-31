document.addEventListener('DOMContentLoaded', () => {
    const searchModeSelect = document.getElementById('search_mode');
    const creatorGroup = document.getElementById('creator-group');
    const commentaryGroup = document.getElementById('commentary-group');
    const urlGroup = document.getElementById('url-group');

    const videoLimitSlider = document.getElementById('video_limit');
    const limitValSpan = document.getElementById('limit-val');

    const scanForm = document.getElementById('scan-form');
    const loadingState = document.getElementById('loading-state');
    const errorBox = document.getElementById('error-box');
    const summarySection = document.getElementById('summary-section');
    const videosContainer = document.getElementById('videos-container');

    // Update Slider Limit Value
    videoLimitSlider.addEventListener('input', (e) => {
        limitValSpan.textContent = e.target.value;
    });

    // Handle Search Mode Input Visibility
    searchModeSelect.addEventListener('change', (e) => {
        const mode = e.target.value;
        creatorGroup.classList.add('hidden');
        commentaryGroup.classList.add('hidden');
        urlGroup.classList.add('hidden');

        if (mode === 'creator') {
            creatorGroup.classList.remove('hidden');
        } else if (mode === 'commentary') {
            commentaryGroup.classList.remove('hidden');
        } else if (mode === 'url') {
            urlGroup.classList.remove('hidden');
        }
    });

    // Form Submission / API Scan
    scanForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // UI Reset
        errorBox.classList.add('hidden');
        summarySection.classList.add('hidden');
        videosContainer.innerHTML = '';
        loadingState.classList.remove('hidden');

        const payload = {
            search_mode: searchModeSelect.value,
            target_creator: document.getElementById('target_creator').value,
            topic_query: document.getElementById('topic_query').value,
            exclude_creator: document.getElementById('exclude_creator').value,
            video_url_id: document.getElementById('video_url_id').value,
            use_youtube_api: document.getElementById('use_youtube_api').checked,
            use_gemini_api: document.getElementById('use_gemini_api').checked,
            yt_api_key: document.getElementById('yt_api_key').value,
            gemini_api_key: document.getElementById('gemini_api_key').value,
            video_limit: parseInt(videoLimitSlider.value),
            max_comments: 50
        };

        try {
            const resp = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await resp.json();
            loadingState.classList.add('hidden');

            if (!resp.ok) {
                errorBox.textContent = `⚠️ Error: ${result.error || 'Failed to complete scan.'}`;
                errorBox.classList.remove('hidden');
                return;
            }

            // Render Aggregate Summary
            document.getElementById('scanned_count').textContent = `${result.summary.scanned_count} Videos`;
            document.getElementById('total_views').textContent = result.summary.total_views;
            document.getElementById('total_likes').textContent = result.summary.total_likes;
            document.getElementById('avg_likes_per_comment').textContent = result.summary.avg_likes_per_comment;
            summarySection.classList.remove('hidden');

            // Render ALL Videos
            renderVideos(result.videos);

        } catch (err) {
            loadingState.classList.add('hidden');
            errorBox.textContent = `⚠️ Connection Error: ${err.message}`;
            errorBox.classList.remove('hidden');
        }
    });

    function renderVideos(videos) {
        videosContainer.innerHTML = '';

        videos.forEach((v, idx) => {
            const card = document.createElement('article');
            card.className = 'video-card';

            const isDemo = v.video_id.startswith ? v.video_id.startswith('demo') : v.video_id.startsWith('demo');
            const mediaHtml = isDemo 
                ? `<img src="https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg" alt="${escapeHtml(v.title)}">`
                : `<iframe src="https://www.youtube.com/embed/${v.video_id}" allowfullscreen></iframe>`;

            // Positive Comments HTML
            let posHtml = '';
            if (v.positive_comments.length === 0) {
                posHtml = '<p style="color: #94a3b8; font-size: 0.85rem;">No strongly positive comments detected.</p>';
            } else {
                v.positive_comments.forEach(c => {
                    posHtml += `
                        <div class="comment-item pos-item">
                            <div class="comment-header">
                                <span>👤 ${escapeHtml(c.author)} (👍 ${c.likes})</span>
                                <span class="badge-score-pos">🟢 +${c.score.toFixed(2)}</span>
                            </div>
                            <div class="comment-text">${escapeHtml(c.text)}</div>
                        </div>
                    `;
                });
            }

            // Negative Comments HTML
            let negHtml = '';
            if (v.negative_comments.length === 0) {
                negHtml = '<p style="color: #94a3b8; font-size: 0.85rem;">No strongly negative comments detected.</p>';
            } else {
                v.negative_comments.forEach(c => {
                    negHtml += `
                        <div class="comment-item neg-item">
                            <div class="comment-header">
                                <span>👤 ${escapeHtml(c.author)} (👍 ${c.likes})</span>
                                <span class="badge-score-neg">🔴 ${c.score.toFixed(2)}</span>
                            </div>
                            <div class="comment-text">${escapeHtml(c.text)}</div>
                        </div>
                    `;
                });
            }

            // Transcript & AI Narrative Box
            let aiSummaryHtml = '';
            if (v.ai_summary) {
                aiSummaryHtml = `
                    <div class="ai-summary-box">
                        <h5>📜 Video Transcript, Topic & Both-Sides Intelligence Summary</h5>
                        <div class="ai-summary-text">${escapeHtml(v.ai_summary).replace(/\n/g, '<br>')}</div>
                    </div>
                `;
            } else if (v.ai_status === 'blocked') {
                aiSummaryHtml = `
                    <div class="ai-summary-box" style="border-color: #f59e0b;">
                        <h5 style="color: #fbbf24;">💡 Gemini Key Permission Note</h5>
                        <div class="ai-summary-text">Your YouTube API Key works for video stats & comments, but has Generative Language API restricted on Google Cloud. Paste a free key from <a href="https://aistudio.google.com/" target="_blank" style="color: #60a5fa;">aistudio.google.com</a> into the Optional Gemini Key input.</div>
                    </div>
                `;
            }

            card.innerHTML = `
                <div style="font-size: 0.8rem; font-weight: 700; color: #3b82f6; text-transform: uppercase; margin-bottom: 8px;">Video #${idx + 1} of ${videos.length}</div>
                <div class="video-header">
                    <div class="video-embed">${mediaHtml}</div>
                    <div class="video-info">
                        <h3>${escapeHtml(v.title)}</h3>
                        <div class="video-meta">👤 Channel: <strong>${escapeHtml(v.channel)}</strong> | 📅 Published: ${v.published}</div>
                        
                        <div class="metrics-row">
                            <div class="metric-pill"><span class="lbl">Views</span><span class="val">${v.views_formatted}</span></div>
                            <div class="metric-pill"><span class="lbl">Likes</span><span class="val">${v.likes_formatted}</span></div>
                            <div class="metric-pill"><span class="lbl">Comments</span><span class="val">${v.comments_formatted}</span></div>
                            <div class="metric-pill"><span class="lbl">Likes/Comment</span><span class="val">${v.likes_per_comment}</span></div>
                        </div>

                        <div class="ratio-badge">${escapeHtml(v.ratio_label)} (${v.likes_per_comment} likes per comment)</div>
                    </div>
                </div>

                ${aiSummaryHtml}

                <div class="both-sides-header">
                    <h4>⚖️ Both-Sides Sentiment Balance (Scanned ${v.total_comments_scanned} comments | Net Vibe: ${v.avg_vibe > 0.05 ? '🟢 Positive' : (v.avg_vibe < -0.05 ? '🔴 Negative' : '⚪ Neutral')})</h4>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width: ${v.pos_pct}%"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.82rem; color: #94a3b8; font-weight: 600;">
                        <span>🟢 ${v.pos_pct}% Positive</span>
                        <span>⚪ ${v.neu_pct}% Neutral</span>
                        <span>🔴 ${v.neg_pct}% Negative</span>
                    </div>
                </div>

                <div class="comments-grid">
                    <div class="comment-column">
                        <h5 class="pos-title">🟢 Positive Side (Top Praises)</h5>
                        ${posHtml}
                    </div>
                    <div class="comment-column">
                        <h5 class="neg-title">🔴 Negative Side (Top Criticisms)</h5>
                        ${negHtml}
                    </div>
                </div>
            `;

            videosContainer.appendChild(card);
        });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
});
