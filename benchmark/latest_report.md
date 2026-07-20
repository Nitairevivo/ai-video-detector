# VerifAI Real-World Benchmark Report

*Run config: 167 videos, deep=True, gemini=False, skipped=0*

## Real-footage run (false-positive test)

No AI videos in this set — AI collection was unavailable (datacenter IPs are blocked by video platforms; AI recall requires phone-collected samples). The meaningful number here is how often **real footage is wrongly flagged as AI**:

| Metric | Value |
|---|---|
| Real videos tested | 167 |
| **False-positive rate** (real → wrongly AI) | **0.6%** |
| **Specificity** (real correctly kept real) | **99.4%** |
| Wrongly flagged | 1 of 167 |

Confusion: TP=0  FP=1  FN=0  TN=166

## By platform

| Platform | N | Accuracy | Precision | Recall | FPR |
|---|---|---|---|---|---|
| archive_org | 37 | 100.0% | — | — | 0.0% |
| wikimedia | 130 | 99.2% | 0.0% | — | 0.8% |

## By category

| Category | N | Accuracy | Precision | Recall | FPR |
|---|---|---|---|---|---|
| aerial | 8 | 100.0% | — | — | 0.0% |
| animal | 14 | 100.0% | — | — | 0.0% |
| cctv | 3 | 100.0% | — | — | 0.0% |
| chaotic | 9 | 100.0% | — | — | 0.0% |
| machine | 8 | 100.0% | — | — | 0.0% |
| misc | 5 | 100.0% | — | — | 0.0% |
| nature | 43 | 100.0% | — | — | 0.0% |
| news | 1 | 100.0% | — | — | 0.0% |
| people | 33 | 100.0% | — | — | 0.0% |
| sport | 19 | 100.0% | — | — | 0.0% |
| street | 10 | 90.0% | 0.0% | — | 10.0% |
| weather | 14 | 100.0% | — | — | 0.0% |

## By deciding layer

| Layer | Decisions | Correct | Accuracy |
|---|---|---|---|
| Ensemble — layers | 167 | 166 | 99.4% |

## Misclassified videos

| File | Expected | Predicted | Confidence | Method |
|---|---|---|---|---|
| wiki_87673649.ogv | REAL | AI | 80% | Ensemble — layers: metadata |
