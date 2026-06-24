"""
Parses the MP4/MOV container box structure at the binary level.
AI tools have unique box orderings and often include proprietary boxes
that reveal their origin without needing to decode a single frame.
"""
import struct
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# Known proprietary boxes left by AI tools
AI_PROPRIETARY_BOXES = {
    b'sora': 'OpenAI Sora',
    b'rnwy': 'Runway',
    b'rnw2': 'Runway',
    b'pika': 'Pika Labs',
    b'klng': 'Kuaishou Kling',
    b'kwai': 'Kuaishou Kling',
    b'luai': 'Luma AI',
    b'luma': 'Luma AI',
    b'veo\x00': 'Google Veo',
    b'hvid': 'Tencent HunyuanVideo',
    b'wan2': 'Wan 2.0',
    b'haip': 'Haiper',
    b'cgvx': 'CogVideoX',
    b'c2pa': 'C2PA Provenance',
    b'JUMB': 'JUMBF (C2PA)',
    b'uuid': 'UUID Box (check for C2PA)',
}

# ftyp major brands used exclusively or predominantly by AI tools
AI_FTYP_BRANDS = {
    'sora': 'OpenAI Sora',
    'rnwy': 'Runway',
    'pika': 'Pika Labs',
    'klng': 'Kuaishou Kling',
    'luai': 'Luma AI',
    'hvid': 'Tencent HunyuanVideo',
}

# Standard box type ordering for camera-captured MP4 (most cameras follow this)
STANDARD_BOX_ORDER = ['ftyp', 'mdat', 'moov']
# AI tools often put moov before mdat (fragmented or structured differently)
AI_BOX_PATTERNS = [
    ['ftyp', 'moov', 'mdat'],  # common in AI tools
    ['ftyp', 'free', 'moov', 'mdat'],
]

READ_BYTES = 131072  # 128KB - enough to read all top-level boxes

# Box types always present in legitimate camera-captured MP4s
STANDARD_CAMERA_BOXES = {
    'ftyp', 'mdat', 'moov', 'free', 'skip', 'wide', 'pnot',
    'udta', 'meta', 'ilst', 'mdia', 'minf', 'dinf', 'stbl',
    'trak', 'tkhd', 'mdhd', 'hdlr', 'vmhd', 'smhd', 'dref',
    'stsd', 'stts', 'stss', 'stsc', 'stsz', 'stco', 'co64',
    'ctts', 'mvhd', 'iods', 'elst', 'edts', 'url ', 'urn ',
    # Fragmented (legit streaming)
    'moof', 'mfhd', 'traf', 'tfhd', 'trun', 'mfra', 'tfra', 'mfro',
    'mvex', 'mehd', 'trex',
    # Common extension boxes
    'uuid', 'JUMB', 'xml ', 'bxml',
    # Apple QuickTime
    'moov', 'cmov', 'rmra', 'rmda', 'rdrf', 'rmdr', 'rmvc', 'rmcd',
}

# 4-char box types that look like real ASCII words/names but are actually unknown
# We flag boxes whose type is printable ASCII but not in STANDARD_CAMERA_BOXES
def _is_suspicious_box(box_type_str: str) -> bool:
    if box_type_str in STANDARD_CAMERA_BOXES:
        return False
    # Must be 4 printable ASCII chars (letters/digits) to be suspicious
    # Non-printable = binary garbage, not a real box
    if len(box_type_str) == 4 and all(c.isprintable() and not c.isspace() for c in box_type_str):
        return True
    return False


@dataclass
class ContainerFeatures:
    format_detected: Optional[str] = None
    box_sequence: list = field(default_factory=list)
    proprietary_boxes: list = field(default_factory=list)
    has_fragmented_mp4: bool = False
    has_free_box: bool = False
    moov_before_mdat: bool = False
    ftyp_brand: Optional[str] = None
    ftyp_compatible_brands: list = field(default_factory=list)
    total_boxes_found: int = 0
    ai_tool_from_box: Optional[str] = None
    container_ai_score: float = 0.0
    # Anomaly detection — unknown box patterns that don't match any camera
    has_unknown_proprietary_boxes: bool = False
    unknown_box_names: list = field(default_factory=list)
    container_anomaly_score: float = 0.0  # suspicious even without known AI signature


def parse_container(file_path: str) -> ContainerFeatures:
    features = ContainerFeatures()
    path = Path(file_path)

    suffix = path.suffix.lower()
    if suffix in {'.mp4', '.mov', '.m4v', '.m4a'}:
        features.format_detected = 'mp4'
        _parse_mp4_boxes(file_path, features)
    elif suffix in {'.mkv', '.webm'}:
        features.format_detected = 'matroska'
        _parse_matroska_header(file_path, features)

    _compute_container_score(features)
    return features


def _parse_mp4_boxes(file_path: str, features: ContainerFeatures):
    try:
        with open(file_path, 'rb') as f:
            data = f.read(READ_BYTES)
    except Exception:
        return

    offset = 0
    moov_pos = None
    mdat_pos = None

    while offset < len(data) - 8:
        try:
            box_size = struct.unpack('>I', data[offset:offset+4])[0]
            box_type = data[offset+4:offset+8]

            try:
                type_str = box_type.decode('latin-1')
            except Exception:
                type_str = repr(box_type)

            features.box_sequence.append(type_str)
            features.total_boxes_found += 1

            # Track positions for ordering
            if type_str == 'moov' and moov_pos is None:
                moov_pos = offset
            elif type_str == 'mdat' and mdat_pos is None:
                mdat_pos = offset

            # Detect specific box types
            if type_str == 'ftyp' and offset + 16 <= len(data):
                brand = data[offset+8:offset+12]
                features.ftyp_brand = brand.decode('latin-1', errors='replace').strip()
                compat_start = offset + 16
                compat_end = min(offset + box_size, len(data))
                features.ftyp_compatible_brands = [
                    data[i:i+4].decode('latin-1', errors='replace').strip()
                    for i in range(compat_start, compat_end, 4)
                    if i + 4 <= compat_end
                ]

            elif type_str == 'free':
                features.has_free_box = True

            elif type_str in ('moof', 'mfra', 'mvex'):
                features.has_fragmented_mp4 = True

            # Check for proprietary AI boxes
            known_ai = False
            for ai_box, tool_name in AI_PROPRIETARY_BOXES.items():
                if box_type == ai_box:
                    features.proprietary_boxes.append((type_str, tool_name))
                    if features.ai_tool_from_box is None and tool_name != 'C2PA Provenance':
                        features.ai_tool_from_box = tool_name
                    known_ai = True
                    break

            # Flag unknown proprietary boxes — possible new AI tool
            if not known_ai and _is_suspicious_box(type_str):
                features.has_unknown_proprietary_boxes = True
                if type_str not in features.unknown_box_names:
                    features.unknown_box_names.append(type_str)

            # Search inside the box data for AI signatures (first 256 bytes)
            box_content_end = min(offset + box_size, len(data))
            box_content = data[offset+8:min(offset+264, box_content_end)]
            for ai_sig, tool_name in AI_PROPRIETARY_BOXES.items():
                if ai_sig in box_content and features.ai_tool_from_box is None:
                    features.ai_tool_from_box = tool_name

            if box_size < 8:
                break
            offset += box_size

        except struct.error:
            break

    if moov_pos is not None and mdat_pos is not None:
        features.moov_before_mdat = moov_pos < mdat_pos


def _parse_matroska_header(file_path: str, features: ContainerFeatures):
    """
    Matroska (MKV/WebM) uses EBML. We scan for known AI-related tags
    in the file header without full EBML parsing.
    """
    AI_MKV_SIGNATURES = [
        (b'Pika', 'Pika Labs'),
        (b'Runway', 'Runway'),
        (b'Sora', 'OpenAI Sora'),
        (b'HeyGen', 'HeyGen'),
        (b'Synthesia', 'Synthesia'),
        (b'StableVideo', 'Stability AI'),
        (b'AnimateDiff', 'AnimateDiff'),
        (b'CogVideo', 'CogVideo'),
    ]
    try:
        with open(file_path, 'rb') as f:
            header = f.read(READ_BYTES)
    except Exception:
        return

    for sig, tool in AI_MKV_SIGNATURES:
        if sig in header:
            features.ai_tool_from_box = tool
            features.proprietary_boxes.append((sig.decode(), tool))
            break


def _compute_container_score(features: ContainerFeatures):
    score = 0.0

    # Proprietary AI box found — very strong signal
    if features.ai_tool_from_box and 'C2PA' not in features.ai_tool_from_box:
        score = 0.95

    # ftyp brand is an AI tool brand — definitive
    if features.ftyp_brand and features.ftyp_brand.lower().strip() in AI_FTYP_BRANDS:
        score = max(score, 0.96)
        if not features.ai_tool_from_box:
            features.ai_tool_from_box = AI_FTYP_BRANDS[features.ftyp_brand.lower().strip()]

    # Compatible brands include an AI brand
    for brand in features.ftyp_compatible_brands:
        b = brand.lower().strip()
        if b in AI_FTYP_BRANDS:
            score = max(score, 0.80)
            if not features.ai_tool_from_box:
                features.ai_tool_from_box = AI_FTYP_BRANDS[b]

    if features.proprietary_boxes:
        score = max(score, 0.80)

    if features.moov_before_mdat:
        score = max(score, 0.55)

    if features.has_fragmented_mp4:
        score = max(score, 0.45)

    features.container_ai_score = min(score, 1.0)

    # Anomaly score — suspicious even without a known AI tool name
    anomaly = 0.0
    if features.has_unknown_proprietary_boxes:
        # Unknown non-standard boxes + moov-before-mdat = strong anomaly
        anomaly = 0.45
        if features.moov_before_mdat:
            anomaly = 0.60
        if len(features.unknown_box_names) >= 2:
            anomaly = min(anomaly + 0.10, 0.70)
    features.container_anomaly_score = anomaly
