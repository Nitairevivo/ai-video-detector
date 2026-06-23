"""
Labels all videos in AI_Videos and Real_Videos folders and trains the model.
Run: python label_all.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import extract_features
from models.classifier import get_classifier

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}
AI_DIR   = Path("/Users/nitai/Desktop/dataset/AI_Videos")
REAL_DIR = Path("/Users/nitai/Desktop/dataset/Real_Videos")

classifier = get_classifier()
ai_count = real_count = errors = 0

def label_dir(folder, is_ai):
    global ai_count, real_count, errors
    label_str = "AI  " if is_ai else "Real"
    files = [f for f in folder.iterdir() if f.suffix.lower() in EXTENSIONS]
    print(f"\n{'='*60}")
    print(f"Labeling {len(files)} files as {label_str} from {folder.name}")
    print('='*60)
    for f in sorted(files):
        try:
            result = extract_features(str(f))
            classifier.add_sample(result.feature_vector, label=is_ai, source=f.name)
            if is_ai: ai_count += 1
            else: real_count += 1
            print(f"  ✓ {label_str} | {f.name[:70]}")
        except Exception as e:
            errors += 1
            print(f"  ✗ ERROR | {f.name[:60]} → {e}")

label_dir(AI_DIR, is_ai=True)
label_dir(REAL_DIR, is_ai=False)

print(f"\n{'='*60}")
print(f"Labeled: {ai_count} AI + {real_count} Real ({errors} errors)")

if ai_count >= 5 and real_count >= 5:
    print("\nTraining ML model...")
    result = classifier.train()
    if "error" in result:
        print(f"  ✗ {result['error']}")
    else:
        print(f"  ✓ Trained on {result['samples_used']} samples")
        print(f"  ✓ AUC: {result['cv_auc_mean']:.3f} ± {result['cv_auc_std']:.3f}")
        print(f"  ✓ Model saved to {result['model_saved']}")
else:
    print("Not enough samples to train yet.")
