"""
VerifAI Python SDK
Detect AI-generated videos with a single API call.

Install:
    pip install requests

Usage:
    from verifai import VerifAI

    client = VerifAI(api_key="your_key")
    result = client.detect_url("https://www.tiktok.com/@user/video/123")
    print(result.verdict)   # "ai_generated" | "ai_edited" | "real"
    print(result.confidence) # 0.97
    print(result.ai_tool)    # "OpenAI Sora"

Get your API key: https://web-zeta-ecru-80.vercel.app/dashboard
"""
import requests
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path


API_BASE = "https://ai-video-detector-production-a305.up.railway.app"


@dataclass
class DetectionResult:
    verdict: str                    # "ai_generated" | "ai_edited" | "real" | "unknown"
    is_ai_generated: bool
    confidence: float               # 0.0 – 1.0
    confidence_pct: str             # "97.0%"
    ai_tool_detected: Optional[str] # "OpenAI Sora", "Kuaishou Kling", etc.
    edit_tool_detected: Optional[str]
    detection_method: str
    url: Optional[str] = None
    filename: Optional[str] = None
    # Audit-grade breakdown: deciding layer, per-layer scores, provenance
    # flags (C2PA, metadata stripped, platform re-encode) and caveats.
    explanation: Optional[dict] = None

    @property
    def is_real(self) -> bool:
        return self.verdict == "real"

    @property
    def is_ai_edited(self) -> bool:
        return self.verdict == "ai_edited"

    def __str__(self):
        label = {"ai_generated": "🤖 AI Generated", "ai_edited": "✏️ AI Edited", "real": "✅ Real"}.get(self.verdict, "❓ Unknown")
        tool = f" ({self.ai_tool_detected})" if self.ai_tool_detected else ""
        return f"{label}{tool} — {self.confidence_pct} confidence"


class VerifAI:
    """
    VerifAI client for AI video detection.

    Args:
        api_key: Your VerifAI API key. Get one at https://web-zeta-ecru-80.vercel.app/dashboard
        timeout: Request timeout in seconds (default: 60)
    """

    def __init__(self, api_key: str, timeout: int = 60):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})

    def detect_url(self, url: str, deep: bool = False) -> DetectionResult:
        """
        Detect if a video URL is AI-generated.

        Args:
            url: Video URL (TikTok, Instagram, YouTube, etc.)
            deep: Run deeper visual analysis (slower, more accurate)

        Returns:
            DetectionResult with verdict and confidence

        Example:
            result = client.detect_url("https://www.tiktok.com/@user/video/123")
            if result.is_ai_generated:
                print(f"AI video! Tool: {result.ai_tool_detected}")
        """
        response = self.session.post(
            f"{API_BASE}/detect-url",
            json={"url": url, "deep": deep},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return DetectionResult(
            verdict=data.get("verdict", "unknown"),
            is_ai_generated=data.get("is_ai_generated", False),
            confidence=data.get("confidence", 0.0),
            confidence_pct=data.get("confidence_pct", "0%"),
            ai_tool_detected=data.get("ai_tool_detected"),
            edit_tool_detected=data.get("edit_tool_detected"),
            detection_method=data.get("detection_method", ""),
            url=url,
            explanation=data.get("explanation"),
        )

    def detect_file(self, file_path: str) -> DetectionResult:
        """
        Detect if a video file is AI-generated.

        Args:
            file_path: Path to video file (.mp4, .mov, .webm, etc.)

        Returns:
            DetectionResult with verdict and confidence
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "rb") as f:
            response = self.session.post(
                f"{API_BASE}/detect",
                files={"file": (path.name, f, "video/mp4")},
                timeout=self.timeout,
            )
        response.raise_for_status()
        data = response.json()
        return DetectionResult(
            verdict=data.get("verdict", "unknown"),
            is_ai_generated=data.get("is_ai_generated", False),
            confidence=data.get("confidence", 0.0),
            confidence_pct=data.get("confidence_pct", "0%"),
            ai_tool_detected=data.get("ai_tool_detected"),
            edit_tool_detected=data.get("edit_tool_detected"),
            detection_method=data.get("detection_method", ""),
            filename=path.name,
            explanation=data.get("explanation"),
        )

    def detect_batch(self, urls: List[str]) -> List[DetectionResult]:
        """
        Detect multiple URLs at once (Enterprise/Business tier required).

        Args:
            urls: List of video URLs to analyze

        Returns:
            List of DetectionResult, one per URL

        Note: Requires Business tier (100 URLs/batch) or Enterprise (1000 URLs/batch).
              Each URL counts as 1 request toward your monthly quota.
        """
        response = self.session.post(
            f"{API_BASE}/detect-batch",
            json=urls,
            timeout=self.timeout * len(urls),
            stream=True,
        )
        response.raise_for_status()
        import json
        results = []
        for item in json.loads(response.content):
            if "error" in item:
                results.append(DetectionResult(
                    verdict="unknown", is_ai_generated=False, confidence=0.0,
                    confidence_pct="0%", ai_tool_detected=None, edit_tool_detected=None,
                    detection_method=f"Error: {item['error']}", url=item.get("url"),
                ))
            else:
                results.append(DetectionResult(
                    verdict=item.get("verdict", "unknown"),
                    is_ai_generated=item.get("is_ai_generated", False),
                    confidence=item.get("confidence", 0.0),
                    confidence_pct=item.get("confidence_pct", "0%"),
                    ai_tool_detected=item.get("ai_tool_detected"),
                    edit_tool_detected=item.get("edit_tool_detected"),
                    detection_method=item.get("detection_method", ""),
                    url=item.get("url"),
                ))
        return results

    def usage(self) -> dict:
        """Returns your current API usage and limits."""
        response = self.session.get(f"{API_BASE}/me", timeout=10)
        response.raise_for_status()
        return response.json()


# ─── Quick-start example ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    key = os.getenv("VERIFAI_API_KEY", "your_api_key_here")
    client = VerifAI(api_key=key)

    # Single URL
    result = client.detect_url("https://www.youtube.com/shorts/3tmd-ClpJxA")
    print(f"Result: {result}")
    print(f"Verdict: {result.verdict}")
    print(f"Confidence: {result.confidence_pct}")

    # Check usage
    usage = client.usage()
    print(f"\nUsage: {usage.get('requests_this_month')}/{usage.get('monthly_limit')} this month")
