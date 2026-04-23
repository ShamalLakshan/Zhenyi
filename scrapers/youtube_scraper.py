"""
YouTube Scraper (via yt-dlp)
────────────────────────────
Searches YouTube for videos and extracts metadata.
No API key required (uses yt-dlp library which bypasses YouTube API limits).
Rate limit: Depends on YouTube infrastructure; generally high.
Reliability: High (yt-dlp is widely maintained and updated).

yt-dlp is a maintained fork of youtube-dl with regular updates and broad compatibility.
Extracts: video title, description, duration, view count, upload date, channel.
"""

import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class YoutubeScraper(BaseScraper):
    """Search YouTube for videos and extract metadata."""

    def __init__(self, config: dict):
        super().__init__("youtube", config)

    async def _fetch(self, query: str) -> list[dict]:
        """
        Search YouTube for videos.
        """
        try:
            results = await asyncio.to_thread(
                self._search_youtube,
                query,
                self.results_per_query
            )
            logger.info(f"[youtube] Found {len(results)} videos for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[youtube] Error searching: {e}")
            return []

    def _search_youtube(self, query: str, max_results: int) -> list[dict]:
        """
        Search YouTube for videos and extract metadata.
        Run in thread pool to avoid blocking.
        """
        try:
            import yt_dlp
            
            # Search for videos
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',  # Don't download, just extract metadata
                'skip_download': True,
                'default_search': 'ytsearch',  # Search YouTube
            }
            
            search_query = f"ytsearch{max_results}:{query}"
            
            results = []
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(search_query, download=False)
                    
                    # Extract individual videos from the search result
                    entries = info.get('entries', []) if info else []
                    
                    for video_info in entries[:max_results]:
                        try:
                            title = video_info.get('title', '')
                            video_id = video_info.get('id', '')
                            duration = video_info.get('duration', 0)
                            view_count = video_info.get('view_count', 0)
                            uploader = video_info.get('uploader', '')
                            upload_date = video_info.get('upload_date', '')
                            description = video_info.get('description', '')
                            
                            url = f"https://www.youtube.com/watch?v={video_id}"
                            
                            # Format duration
                            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "N/A"
                            
                            content = f"{title}\n\n"
                            content += f"Channel: {uploader}\n"
                            content += f"Duration: {duration_str}\n"
                            content += f"Views: {view_count:,}\n"
                            content += f"Upload Date: {upload_date}\n\n"
                            content += f"Description:\n{description[:500]}..."
                            
                            results.append({
                                "source": "youtube",
                                "title": title,
                                "url": url,
                                "content": content,
                                "duration": duration,
                                "views": view_count,
                                "channel": uploader,
                            })
                        
                        except Exception as e:
                            logger.debug(f"[youtube] Error extracting video metadata: {e}")
                            continue
                
                except Exception as e:
                    logger.warning(f"[youtube] Search extraction failed: {e}")
                    return []
            
            return results
        
        except ImportError:
            logger.error("[youtube] yt-dlp not installed; cannot search YouTube")
            return []
        
        except Exception as e:
            logger.error(f"[youtube] Search failed: {e}")
            return []
