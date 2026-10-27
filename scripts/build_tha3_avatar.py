"""CLI entry for the shared THA3 renderer; see docs/deployment.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.integrations.tha3_renderer import CLIPS, pose_values, read_source, write_pack, main

if __name__ == '__main__':
    main()
