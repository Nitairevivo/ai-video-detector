/**
 * VerifAI JavaScript/Node.js SDK
 * Detect AI-generated videos with a single API call.
 *
 * Install:
 *   npm install node-fetch form-data
 *
 * Usage:
 *   const { VerifAI } = require('./verifai');
 *   const client = new VerifAI({ apiKey: 'your_key' });
 *   const result = await client.detectUrl('https://www.tiktok.com/@user/video/123');
 *   console.log(result.verdict); // "ai_generated" | "ai_edited" | "real"
 *
 * Get your API key: https://web-zeta-ecru-80.vercel.app/dashboard
 */

const API_BASE = 'https://ai-video-detector-production-a305.up.railway.app';

class DetectionResult {
  constructor(data, url = null) {
    this.verdict = data.verdict || 'unknown';
    this.isAiGenerated = data.is_ai_generated || false;
    this.isAiEdited = this.verdict === 'ai_edited';
    this.isReal = this.verdict === 'real';
    this.confidence = data.confidence || 0;
    this.confidencePct = data.confidence_pct || '0%';
    this.aiToolDetected = data.ai_tool_detected || null;
    this.editToolDetected = data.edit_tool_detected || null;
    this.detectionMethod = data.detection_method || '';
    this.url = url || data.url || null;
    this.filename = data.filename || null;
  }

  toString() {
    const labels = {
      ai_generated: '🤖 AI Generated',
      ai_edited: '✏️ AI Edited',
      real: '✅ Real',
    };
    const label = labels[this.verdict] || '❓ Unknown';
    const tool = this.aiToolDetected ? ` (${this.aiToolDetected})` : '';
    return `${label}${tool} — ${this.confidencePct} confidence`;
  }
}

class VerifAI {
  /**
   * @param {Object} options
   * @param {string} options.apiKey - Your VerifAI API key
   * @param {number} [options.timeout=60000] - Request timeout in ms
   */
  constructor({ apiKey, timeout = 60_000 } = {}) {
    if (!apiKey) throw new Error('VerifAI: apiKey is required');
    this.apiKey = apiKey;
    this.timeout = timeout;
    this._headers = {
      'X-Api-Key': apiKey,
      'Content-Type': 'application/json',
    };
  }

  async _fetch(path, options = {}) {
    const fetch = (await import('node-fetch')).default;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        signal: controller.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(`VerifAI API error ${res.status}: ${err.detail || res.statusText}`);
      }
      return res;
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * Detect if a video URL is AI-generated.
   * @param {string} url - Video URL (TikTok, Instagram, YouTube, etc.)
   * @param {boolean} [deep=false] - Run deeper visual analysis
   * @returns {Promise<DetectionResult>}
   */
  async detectUrl(url, deep = false) {
    const res = await this._fetch('/detect-url', {
      method: 'POST',
      headers: this._headers,
      body: JSON.stringify({ url, deep }),
    });
    const data = await res.json();
    return new DetectionResult(data, url);
  }

  /**
   * Detect if a video file is AI-generated.
   * @param {string|Buffer} fileOrPath - File path (Node.js) or Buffer
   * @param {string} [filename='video.mp4'] - Filename for the upload
   * @returns {Promise<DetectionResult>}
   */
  async detectFile(fileOrPath, filename = 'video.mp4') {
    const FormData = (await import('form-data')).default;
    const fs = await import('fs');
    const form = new FormData();
    const buffer = typeof fileOrPath === 'string'
      ? fs.readFileSync(fileOrPath)
      : fileOrPath;
    form.append('file', buffer, { filename, contentType: 'video/mp4' });
    const res = await this._fetch('/detect', {
      method: 'POST',
      headers: { 'X-Api-Key': this.apiKey, ...form.getHeaders() },
      body: form,
    });
    const data = await res.json();
    return new DetectionResult(data);
  }

  /**
   * Detect multiple URLs at once (Business/Enterprise tier).
   * @param {string[]} urls - Array of video URLs
   * @returns {Promise<DetectionResult[]>}
   */
  async detectBatch(urls) {
    const res = await this._fetch('/detect-batch', {
      method: 'POST',
      headers: this._headers,
      body: JSON.stringify(urls),
    });
    const items = await res.json();
    return items.map(item => new DetectionResult(item));
  }

  /**
   * Get your current API usage and limits.
   * @returns {Promise<Object>}
   */
  async usage() {
    const res = await this._fetch('/me', { headers: this._headers });
    return res.json();
  }
}

module.exports = { VerifAI, DetectionResult };

// ─── TypeScript types (paste into .d.ts file) ────────────────────────────────
/**
 * @typedef {'ai_generated' | 'ai_edited' | 'real' | 'unknown'} Verdict
 *
 * @typedef {Object} DetectionResultData
 * @property {Verdict} verdict
 * @property {boolean} isAiGenerated
 * @property {boolean} isAiEdited
 * @property {boolean} isReal
 * @property {number} confidence
 * @property {string} confidencePct
 * @property {string|null} aiToolDetected
 * @property {string|null} editToolDetected
 * @property {string} detectionMethod
 */
