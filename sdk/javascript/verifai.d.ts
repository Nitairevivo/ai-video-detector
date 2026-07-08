export type Verdict = "ai_generated" | "ai_edited" | "real" | "unknown";

export interface Provenance {
  c2pa_present?: boolean;
  c2pa_claims_ai?: boolean;
  metadata_stripped?: boolean;
  platform_reencoded?: boolean;
  ai_tool?: string | null;
  edit_tool?: string | null;
}

export interface Explanation {
  deciding_layer?: string;
  layer_scores?: Record<string, number>;
  ml_probability?: number | null;
  provenance?: Provenance;
  caveats?: string[];
}

export declare class DetectionResult {
  verdict: Verdict;
  isAiGenerated: boolean;
  isAiEdited: boolean;
  isReal: boolean;
  confidence: number;
  confidencePct: string;
  aiToolDetected: string | null;
  editToolDetected: string | null;
  detectionMethod: string;
  url: string | null;
  filename: string | null;
  explanation: Explanation | null;
  toString(): string;
}

export declare class VerifAI {
  constructor(options: { apiKey: string; timeout?: number });
  detectUrl(url: string, deep?: boolean): Promise<DetectionResult>;
  detectFile(fileOrPath: string | Blob, filename?: string): Promise<DetectionResult>;
  detectBatch(urls: string[]): Promise<DetectionResult[]>;
}
