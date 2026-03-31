"""
WhatsApp-style media compression for task attachments.
- Images: Resize to max 1600px, JPEG @ quality 70, strip EXIF → typically 50-200 KB
- Videos: Re-encode via ffmpeg to 480p, CRF 28, AAC 64k → drastically smaller
Falls back gracefully if Pillow or ffmpeg is missing.
"""
import os
import io
import subprocess
import logging

logger = logging.getLogger(__name__)

# ─── IMAGE COMPRESSION ───────────────────────────────────────

def compress_image(file_stream, max_size_kb=300, max_dimension=1600, quality=70):
    """
    Compress an image file stream.
    Returns: (BytesIO stream, compressed_size_bytes, format_str)
    Falls back to original if Pillow not installed.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed — skipping image compression")
        file_stream.seek(0)
        raw = file_stream.read()
        return io.BytesIO(raw), len(raw), "original"

    try:
        file_stream.seek(0)
        img = Image.open(file_stream)

        # Convert RGBA/P → RGB for JPEG
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Strip EXIF by creating a clean copy
        clean = Image.new("RGB", img.size)
        clean.putdata(list(img.getdata()))
        img = clean

        # Resize if too large
        w, h = img.size
        if max(w, h) > max_dimension:
            ratio = max_dimension / max(w, h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # Save with reducing quality until under max_size_kb
        q = quality
        while q >= 30:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            size = buf.tell()
            if size <= max_size_kb * 1024 or q <= 30:
                buf.seek(0)
                return buf, size, "JPEG"
            q -= 10

        buf.seek(0)
        return buf, buf.tell(), "JPEG"

    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        file_stream.seek(0)
        raw = file_stream.read()
        return io.BytesIO(raw), len(raw), "original"


# ─── VIDEO COMPRESSION ───────────────────────────────────────

def _ffmpeg_available():
    """Check if ffmpeg is installed."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def compress_video(input_path, output_path=None, max_height=480, crf=28, audio_bitrate="64k"):
    """
    Compress a video file using ffmpeg (WhatsApp-style).
    - Re-encode to H.264 with CRF 28 (good quality, small size)
    - Scale down to max 480p height
    - AAC audio at 64kbps
    - Fast preset for reasonable speed

    Returns: (output_path, original_size, compressed_size) or None if failed.
    """
    if not _ffmpeg_available():
        logger.warning("ffmpeg not available — skipping video compression")
        return None

    if not os.path.exists(input_path):
        return None

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed.mp4"

    original_size = os.path.getsize(input_path)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", f"scale=-2:'min({max_height},ih)'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-movflags", "+faststart",
            "-threads", "2",
            output_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,  # 2 min max per video
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr.decode('utf-8', errors='replace')[-500:]}")
            # Cleanup failed output
            if os.path.exists(output_path):
                os.remove(output_path)
            return None

        compressed_size = os.path.getsize(output_path)

        # If compressed version is actually larger, keep original
        if compressed_size >= original_size:
            os.remove(output_path)
            return None

        return output_path, original_size, compressed_size

    except subprocess.TimeoutExpired:
        logger.error("Video compression timed out")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None
    except Exception as e:
        logger.error(f"Video compression failed: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


# ─── HELPERS ──────────────────────────────────────────────────

def get_compressed_size_label(size_bytes):
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
