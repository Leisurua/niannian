"""Server-side cutout and deterministic face placement for THA3. No private files."""
import argparse
from io import BytesIO
import os
from pathlib import Path
import sys

from PIL import Image


def place_face(image, face):
    x, y, width, height = map(float, face)
    if min(width, height) < 24 or x < 0 or y < 0 or x + width > image.width or y + height > image.height:
        raise ValueError('Face placement invalid')
    scale = 106.0 / max(width, height)
    if image.width * scale > 4096 or image.height * scale > 4096:
        raise ValueError('Face too small')
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    left = round(256 - (x + width / 2) * scale)
    top = round(142 - (y + height / 2) * scale)
    canvas = Image.new('RGBA', (512, 512))
    canvas.paste(resized, (left, top))
    if canvas.getchannel('A').getextrema() != (0, 255):
        raise ValueError('Cutout invalid')
    out = BytesIO(); canvas.save(out, format='PNG')
    return out.getvalue()


def prepare(data, cascade_path, model_dir):
    import cv2
    import numpy as np
    from rembg import new_session, remove

    weights = (Path(model_dir) / 'u2netp.onnx', Path(model_dir) / 'models/u2netp/u2netp.onnx')
    if not Path(cascade_path).is_file() or not any(path.is_file() for path in weights):
        raise ValueError('Preprocessing models are not installed')
    os.environ['U2NET_HOME'] = str(Path(model_dir).resolve())
    with Image.open(BytesIO(data), formats=['PNG', 'JPEG', 'WEBP']) as image:
        if image.width * image.height > 4194304 or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Image too large')
        image.load()
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        background = Image.new('RGBA', image.size, 'white')
        background.alpha_composite(image.convert('RGBA'))
        rgb = background.convert('RGB')
        # Histogram equalization can erase the flat shading that the anime cascade uses.
        gray = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2GRAY)
        # Seedream can preserve an older person's realistic facial proportions.
        # Use OpenCV's bundled frontal detector only if the anime detector found no face.
        candidates = [(Path(cascade_path), 40),
            (Path(cv2.data.haarcascades) / 'haarcascade_frontalface_alt2.xml', 64)]
        for path, minimum in candidates:
            # Python XML reads also support non-ASCII Windows deployment paths.
            cascade = cv2.FileStorage(path.read_text(encoding='utf-8'), cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
            detector = cv2.CascadeClassifier()
            detector.read(cascade.getFirstTopLevelNode())
            cascade.release()
            faces = detector.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=5, minSize=(minimum, minimum))
            if len(faces):
                break
        if len(faces) != 1:
            raise ValueError('Expected exactly one clear frontal anime face')
        cutout = remove(rgb, session=new_session('u2netp', providers=['CPUExecutionProvider']))
        return place_face(cutout.convert('RGBA'), faces[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cascade', required=True, type=Path)
    parser.add_argument('--models', required=True, type=Path)
    args = parser.parse_args()
    data = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('Image too large')
    sys.stdout.buffer.write(prepare(data, args.cascade, args.models))


if __name__ == '__main__':
    main()
