from io import BytesIO
import json
from zipfile import ZipFile

from PIL import Image
import pytest

from scripts.build_tha3_avatar import CLIPS, pose_values, read_source, write_pack


def test_source_requires_prepared_transparent_illustration(tmp_path):
    path = tmp_path / 'character.png'
    Image.new('RGB', (512, 512), 'white').save(path)
    with pytest.raises(ValueError, match='RGBA'):
        read_source(path)
    Image.new('RGBA', (512, 512), (20, 30, 40, 255)).save(path)
    with pytest.raises(ValueError, match='透明'):
        read_source(path)
    image = Image.new('RGBA', (512, 512))
    image.paste((20, 30, 40, 255), (180, 50, 330, 500))
    image.save(path)
    assert read_source(path).size == (512, 512)


def test_non_speaking_states_never_open_mouth():
    for state, (count, _) in CLIPS.items():
        for i in range(count):
            pose = pose_values(state, i)
            if state != 'SPEAKING':
                assert not any(name.startswith('mouth_') and value > 0 for name, value in pose.items())
    assert pose_values('SPEAKING', 2)['mouth_aaa'] > 0


def test_export_contract_and_attribution_without_embedding_source(tmp_path):
    output = tmp_path / 'avatar.zip'
    frame = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    frame.paste((255, 100, 30, 255), (190, 65, 320, 190))
    write_pack(output, lambda _: frame, 'Synthetic test illustration')
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {'manifest.json', 'idle.png', 'listening.png', 'thinking.png', 'speaking.png'}
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['format'] == 'niannian-tha3-v1'
        assert 'Pramook Khungurn' in manifest['credits'] and 'Synthetic test illustration' in manifest['credits']
        for state, (count, fps) in CLIPS.items():
            clip = manifest['states'][state]
            assert clip['frames'] == count and clip['fps'] == fps
            with Image.open(BytesIO(archive.read(clip['file']))) as image:
                assert image.mode == 'RGBA'
                assert image.size == (1024, ((count + 3) // 4) * 256)
                assert image.getchannel('A').getextrema() == (0, 255)
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_pack(output, lambda _: frame, 'Synthetic test illustration')
    assert output.read_bytes() == before


def test_failed_inference_never_leaves_an_importable_partial_pack(tmp_path):
    output = tmp_path / 'failed.zip'
    def fail(_):
        raise RuntimeError('inference failed')
    with pytest.raises(RuntimeError, match='inference failed'):
        write_pack(output, fail, 'Synthetic test illustration')
    assert not output.exists()
