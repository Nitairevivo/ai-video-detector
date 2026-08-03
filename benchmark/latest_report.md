# VerifAI Real-World Benchmark Report

*Run config: 162 videos, deep=True, gemini=False, skipped=0*

## Real-footage run (false-positive test)

No AI videos in this set — AI collection was unavailable (datacenter IPs are blocked by video platforms; AI recall requires phone-collected samples). The meaningful number here is how often **real footage is wrongly flagged as AI**:

| Metric | Value |
|---|---|
| Real videos tested | 162 |
| **False-positive rate** (real → wrongly AI) | **0.6%** |
| **Specificity** (real correctly kept real) | **99.4%** |
| Wrongly flagged | 1 of 162 |

Confusion: TP=0  FP=1  FN=0  TN=161

## By platform

| Platform | N | Accuracy | Precision | Recall | FPR |
|---|---|---|---|---|---|
| archive_org | 33 | 100.0% | — | — | 0.0% |
| wikimedia | 129 | 99.2% | 0.0% | — | 0.8% |

## By category

| Category | N | Accuracy | Precision | Recall | FPR |
|---|---|---|---|---|---|
| aerial | 8 | 100.0% | — | — | 0.0% |
| animal | 13 | 100.0% | — | — | 0.0% |
| cctv | 2 | 100.0% | — | — | 0.0% |
| chaotic | 9 | 100.0% | — | — | 0.0% |
| machine | 7 | 100.0% | — | — | 0.0% |
| misc | 7 | 100.0% | — | — | 0.0% |
| nature | 41 | 100.0% | — | — | 0.0% |
| news | 1 | 100.0% | — | — | 0.0% |
| people | 31 | 100.0% | — | — | 0.0% |
| sport | 19 | 100.0% | — | — | 0.0% |
| street | 9 | 88.9% | 0.0% | — | 11.1% |
| weather | 15 | 100.0% | — | — | 0.0% |

## By deciding layer

| Layer | Decisions | Correct | Accuracy |
|---|---|---|---|
| Ensemble — layers | 162 | 161 | 99.4% |

## Misclassified videos

| File | Expected | Predicted | Confidence | Method |
|---|---|---|---|---|
| wiki_70344947.ogv | REAL | AI | 80% | Ensemble — layers: metadata |
