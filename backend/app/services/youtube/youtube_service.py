"""
YouTube Video Transcript Extraction and Chunking Service.

Written against youtube-transcript-api==1.2.4 (uses instance-based YouTubeTranscriptApi().fetch(video_id)).
Extracts video transcripts with timestamps, packs consecutive segments into target-sized chunks,
and tracks each chunk's start timestamp.
"""

import re
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs, parse_qsl, urlencode, urlunparse

# Written against youtube-transcript-api==1.2.4
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    InvalidVideoId,
    CouldNotRetrieveTranscript,
    YouTubeTranscriptApiException,
)


class YouTubeCaptionError(Exception):
    """Raised when a YouTube video does not have accessible captions/transcripts."""
    pass


class YouTubeService:

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extract the 11-character video ID from common YouTube URL formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://www.youtube.com/v/VIDEO_ID
        - URLs with timestamp, playlist, or mobile query parameters
        """
        if not url or not isinstance(url, str):
            return None

        clean_url = url.strip()

        # Handle youtu.be/<id>
        parsed = urlparse(clean_url)
        if "youtu.be" in parsed.netloc:
            path_part = parsed.path.strip("/").split("/")[0]
            if len(path_part) == 11:
                return path_part

        # Handle youtube.com/watch?v=<id>
        if "youtube.com" in parsed.netloc or "youtube-nocookie.com" in parsed.netloc:
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                video_ids = qs.get("v", [])
                if video_ids and len(video_ids[0]) == 11:
                    return video_ids[0]
            elif parsed.path.startswith(("/embed/", "/v/")):
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2 and len(parts[1]) == 11:
                    return parts[1]

        # Regex fallback for any 11-char pattern
        regex_match = re.search(r"(?:v=|\/embed\/|\/v\/|youtu\.be\/|\/shorts\/)([a-zA-Z0-9_-]{11})", clean_url)
        if regex_match:
            return regex_match.group(1)

        return None

    @staticmethod
    def fetch_transcript(video_url: str) -> Tuple[str, List[Dict[str, any]]]:
        """Fetch transcript segments for a given YouTube URL.

        Written against youtube-transcript-api==1.2.4.
        Returns:
            (video_id, [{"text": str, "start": float, "duration": float}, ...])

        Raises:
            ValueError if the URL is invalid.
            YouTubeCaptionError if the video has no captions or transcripts enabled.
        """
        video_id = YouTubeService.extract_video_id(video_url)
        if not video_id:
            raise ValueError(f"Could not extract a valid YouTube video ID from URL: {video_url}")

        try:
            # In youtube-transcript-api==1.2.4, fetch is an instance method:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            segments = [
                {
                    "text": snippet.text.replace("\n", " ").strip(),
                    "start": snippet.start,
                    "duration": snippet.duration,
                }
                for snippet in fetched
                if snippet.text.strip()
            ]

            if not segments:
                raise YouTubeCaptionError("The video transcript is empty.")

            return video_id, segments

        except (NoTranscriptFound, TranscriptsDisabled) as e:
            raise YouTubeCaptionError(
                "This YouTube video has no captions or transcript available. "
                "Please choose a video with closed captions (CC) enabled."
            ) from e
        except (VideoUnavailable, InvalidVideoId) as e:
            raise YouTubeCaptionError(f"The YouTube video is unavailable or invalid: {e}") from e
        except CouldNotRetrieveTranscript as e:
            raise YouTubeCaptionError(
                f"Could not retrieve transcripts for this video. The video might be private or region-restricted: {e}"
            ) from e
        except YouTubeTranscriptApiException as e:
            raise YouTubeCaptionError(f"YouTube transcript API error: {e}") from e
        except Exception as e:
            raise YouTubeCaptionError(f"Failed to fetch transcript: {e}") from e

    @staticmethod
    def pack_transcript_chunks(
        segments: List[Dict[str, any]],
        target_chunk_size: int = 800,
    ) -> List[Dict[str, any]]:
        """Group consecutive transcript segments into chunks of roughly target_chunk_size characters.

        Packs by segment rather than splitting sentences to preserve start timestamp mappings.
        Tracks the start timestamp (in integer seconds) of the FIRST segment in each chunk.
        """
        if not segments:
            return []

        chunks: List[Dict[str, any]] = []
        current_texts: List[str] = []
        current_len = 0
        current_start_seconds = int(segments[0]["start"])

        for seg in segments:
            text = seg["text"].strip()
            if not text:
                continue

            seg_len = len(text)
            if current_len + seg_len + 1 > target_chunk_size and current_texts:
                chunks.append({
                    "text": " ".join(current_texts),
                    "start_seconds": current_start_seconds,
                })
                current_texts = [text]
                current_len = seg_len
                current_start_seconds = int(seg["start"])
            else:
                if not current_texts:
                    current_start_seconds = int(seg["start"])
                current_texts.append(text)
                current_len += seg_len + 1

        if current_texts:
            chunks.append({
                "text": " ".join(current_texts),
                "start_seconds": current_start_seconds,
            })

        return chunks

    @staticmethod
    def generate_timestamp_url(source_url: str, start_seconds: Optional[int]) -> Optional[str]:
        """Generate a YouTube timestamp link pointing to start_seconds."""
        if not source_url:
            return None
        if start_seconds is None or start_seconds < 0:
            return source_url

        # Drop any t= already in the saved URL (e.g. a link copied mid-video),
        # otherwise the result ends up with two conflicting t params.
        parsed = urlparse(source_url)
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "t"]
        t_value = str(start_seconds) if "youtu.be" in parsed.netloc else f"{start_seconds}s"
        query.append(("t", t_value))
        return urlunparse(parsed._replace(query=urlencode(query)))
