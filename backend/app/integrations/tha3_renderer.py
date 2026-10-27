"""Render a THA3 illustration into a small, offline NianNian Android avatar pack."""
import argparse
import contextlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

FORMAT = 'niannian-tha3-v1'
FRAME_SIZE = 256
COLUMNS = 4
CLIPS = {'IDLE': (12, 4), 'LISTENING': (12, 4), 'THINKING': (12, 6), 'SPEAKING': (8, 12)}
WEIGHTS = ('eyebrow_decomposer', 'eyebrow_morphing_combiner', 'face_morpher',
           'two_algo_face_body_rotator', 'editor')
UPSTREAM = 'https://github.com/pkhungurn/talking-head-anime-3-demo'


def read_source(path: Path) -> Image.Image:
    with Image.open(path) as image:
        if image.format != 'PNG' or image.size != (512, 512) or image.mode != 'RGBA':
            raise ValueError('THA3 输入须为 512×512 的 RGBA PNG 正面动漫立绘，请先按上游规范处理。')
        if image.getchannel('A').getextrema() != (0, 255):
            raise ValueError('立绘须包含透明背景和不透明角色，不能使用整张不透明照片。')
        return image.copy()


def pose_values(state: str, index: int) -> dict[str, float]:
    count, _ = CLIPS[state]
    phase = 2 * math.pi * index / count
    pose = {'breathing': 0.25 + 0.15 * math.sin(phase), 'body_y': 0.025 * math.sin(phase)}
    blink = {8: 0.4, 9: 1.0, 10: 0.4}.get(index, 0.0) if state != 'SPEAKING' else 0.0
    pose.update(eye_wink_left=blink, eye_wink_right=blink)
    if state == 'LISTENING':
        pose.update(head_x=0.06 * math.sin(phase), neck_z=0.04,
                    eyebrow_raised_left=0.12, eyebrow_raised_right=0.12)
    elif state == 'THINKING':
        pose.update(neck_z=0.08, iris_rotation_x=0.18, iris_rotation_y=-0.1,
                    head_y=0.04 * math.sin(phase))
    elif state == 'SPEAKING':
        # Varied mouth shapes, gated by actual TTS playback on Android; not phoneme alignment.
        mouth, amount = [('mouth_aaa', 0.0), ('mouth_aaa', 0.35), ('mouth_aaa', 0.65),
                         ('mouth_iii', 0.3), ('mouth_ooo', 0.45), ('mouth_uuu', 0.25),
                         ('mouth_aaa', 0.45), ('mouth_aaa', 0.1)][index]
        pose.update({mouth: amount, 'head_x': 0.035 * math.sin(phase)})
    return pose


def write_pack(output: Path | BytesIO, render, art_credit: str, preview: Path | None = None):
    if not art_credit.strip() or len(art_credit) > 1000:
        raise ValueError('请提供不超过 1000 字的立绘作者、来源及许可说明。')
    credits = (f'THA3 model: Pramook Khungurn, CC BY 4.0. {UPSTREAM}\n'
               f'Artwork: {art_credit.strip()}\nAnimated/resized into NianNian state clips.')
    manifest = dict(format=FORMAT, frame_size=FRAME_SIZE, columns=COLUMNS, credits=credits, states={})
    # x mode preserves any existing avatar; a failed build cannot replace a working pack.
    if isinstance(output, Path):
        output.parent.mkdir(parents=True, exist_ok=True)
    previews = []
    try:
        with ZipFile(output, 'x' if isinstance(output, Path) else 'w', compression=ZIP_DEFLATED) as archive:
            for state, (count, fps) in CLIPS.items():
                sheet = Image.new('RGBA', (COLUMNS * FRAME_SIZE, math.ceil(count / COLUMNS) * FRAME_SIZE))
                for index in range(count):
                    frame = render(pose_values(state, index)).convert('RGBA')
                    # THA3 places the face near the upper centre; show head/shoulders at phone size.
                    if frame.size != (512, 512):
                        raise ValueError('THA3 返回的图片尺寸不是 512×512。')
                    frame = frame.crop((128, 32, 384, 288))
                    frame = frame.resize((FRAME_SIZE, FRAME_SIZE), Image.Resampling.LANCZOS)
                    sheet.paste(frame, ((index % COLUMNS) * FRAME_SIZE, (index // COLUMNS) * FRAME_SIZE))
                    if index == (2 if state == 'SPEAKING' else 0):
                        previews.append(frame.copy())
                name = state.lower() + '.png'
                stream = BytesIO()
                sheet.save(stream, format='PNG')
                archive.writestr(name, stream.getvalue())
                manifest['states'][state] = dict(file=name, frames=count, fps=fps)
                print(f'Rendered {state}: {count} frames', flush=True)
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False).encode('utf-8'))
    except FileExistsError:
        raise
    except BaseException:
        if isinstance(output, Path):
            output.unlink(missing_ok=True)
        raise
    if preview is not None:
        preview.parent.mkdir(parents=True, exist_ok=True)
        strip = Image.new('RGBA', (FRAME_SIZE * 4, FRAME_SIZE), (246, 241, 234, 255))
        for index, frame in enumerate(previews):
            strip.alpha_composite(frame, (index * FRAME_SIZE, 0))
        strip.convert('RGB').save(preview)


def make_renderer(tha3_root: Path, model_dir: Path, source: Image.Image, device_name: str):
    if not (tha3_root / 'tha3/poser/modes/separable_float.py').is_file():
        raise ValueError('--tha3-root 须指向官方 talking-head-anime-3-demo 源码目录。')
    files = {name: str((model_dir / (name + '.pt')).resolve()) for name in WEIGHTS}
    if not all(Path(path).is_file() for path in files.values()):
        raise ValueError('--model-dir 中须包含官方 separable_float 的五个 .pt 权重文件。')
    sys.path.insert(0, str(tha3_root.resolve()))
    import numpy as np
    import torch
    from tha3.poser.modes.pose_parameters import get_pose_parameters
    from tha3.poser.modes.separable_float import create_poser
    from tha3.util import extract_pytorch_image_from_PIL_image, rgba_to_numpy_image

    if device_name == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA 不可用；请安装适配显卡的 PyTorch，或显式指定 --device cpu（较慢）。')
    device = torch.device(device_name)
    poser = create_poser(device, module_file_names=files)
    parameters = get_pose_parameters()
    image = extract_pytorch_image_from_PIL_image(source).to(device)

    def render(values):
        pose = torch.zeros(poser.get_num_parameters(), device=device)
        for name, value in values.items():
            pose[parameters.get_parameter_index(name)] = value
        with torch.inference_mode():
            pixels = poser.pose(image, pose)[0].detach().float().cpu()
        rgba = np.round(np.clip(rgba_to_numpy_image(pixels), 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(rgba)

    return render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tha3-root', required=True, type=Path)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--output', type=Path, help='New .zip file, imported in the elder chat panel')
    parser.add_argument('--stdio', action='store_true', help='Worker mode: PNG from stdin, ZIP to stdout, no private temporary files')
    parser.add_argument('--art-credit', required=True, help='Illustration author, source and license; included in the pack')
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--preview', type=Path, help='Optional four-state preview image')
    args = parser.parse_args()
    if args.stdio:
        raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            parser.error('Input image too large')
        with contextlib.redirect_stdout(sys.stderr):
            source = read_source(BytesIO(raw))
            renderer = make_renderer(args.tha3_root, args.model_dir, source, args.device)
            result = BytesIO()
            write_pack(result, renderer, args.art_credit)
        sys.stdout.buffer.write(result.getvalue())
        return
    if args.image is None or args.output is None:
        parser.error('--image and --output are required unless --stdio is used')
    if args.output.exists():
        parser.error('输出文件已存在，请使用新的文件名。')
    try:
        source = read_source(args.image)
        renderer = make_renderer(args.tha3_root, args.model_dir, source, args.device)
        write_pack(args.output, renderer, args.art_credit, args.preview)
    except (ValueError, ImportError) as error:
        parser.exit(2, f'{error}\n')
    print('Avatar pack ready. Import it from the elder chat panel after granting PORTRAIT consent.')


if __name__ == '__main__':
    main()
