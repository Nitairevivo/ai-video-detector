"""Label-safety tests: the path classifier must never mislabel, and must SKIP
anything ambiguous. A false 'ai' on a real video poisons the model, so these
cases are the guardrail."""
from training.path_labeler import classify


def test_ai_generator_folders():
    assert classify("fake/kling/clip001.mp4") == "ai"
    assert classify("GenVideo/train/sora/000123.mp4") == "ai"
    assert classify("videos/cogvideox-5b/x.webm") == "ai"
    assert classify("t2v-zero/sample.mp4") == "ai"
    assert classify("generated/modelscope/v.mp4") == "ai"


def test_deepaction_generators():
    # DeepAction packs AI by model-name folder + Pexels reals
    assert classify("deepaction_v1/VideoPoet/clip.mp4") == "ai"
    assert classify("CogVideoX5B/000.mp4") == "ai"
    assert classify("data/RunwayML/x.mp4") == "ai"
    assert classify("StableDiffusion/y.mp4") == "ai"
    assert classify("AnimateDiff/z.mp4") == "ai"
    assert classify("deepaction/Pexels/real001.mp4") == "real"


def test_real_folders():
    assert classify("real/vript/clip042.mp4") == "real"
    assert classify("data/webvid/abc.mp4") == "real"
    assert classify("GT/scene1.mp4") == "real"
    assert classify("pristine/cam/010.mov") == "real"


def test_ambiguous_or_unknown_is_skipped():
    # both signals present → never guess
    assert classify("real_vs_fake/kling/real/clip.mp4") is None
    # no class signal at all → skip
    assert classify("dataset/train/00001.mp4") is None
    assert classify("clips/video_000.mp4") is None
    # a real source that merely mentions "generation" in a neutral way but has a
    # real marker AND an ai marker must skip, not mislabel
    assert classify("webvid/generated_captions/x.mp4") is None


def test_word_boundaries():
    # "areal" or "aigcx" substrings shouldn't trip the folder matcher falsely
    assert classify("surreal/clip.mp4") is None       # 'surreal' ≠ real dir
    assert classify("mainstream/clip.mp4") is None      # not a generator
