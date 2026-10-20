"""Small development checks. Pass test paths to run only the feature being changed."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('check', choices=['lint', 'test', 'integration', 'android', 'windows'], nargs='?', default='test')
    parser.add_argument('paths', nargs='*', help='Optional pytest paths or Gradle tasks')
    args = parser.parse_args()
    env = {**os.environ, 'PYTHONUTF8': '1', 'APP_ENV': 'test', 'PROVIDER_MODE': 'mock'}
    env['PYTHONPATH'] = os.pathsep.join(map(str, [ROOT, ROOT / 'backend', ROOT / 'windows/src']))
    cwd = ROOT
    if args.check == 'lint':
        command = [sys.executable, '-m', 'ruff', 'check', *(args.paths or ['backend', 'scripts', 'tests', 'windows'])]
    elif args.check == 'android':
        cwd = ROOT / 'android'
        wrapper = 'gradlew.bat' if os.name == 'nt' else 'gradlew'
        command = [str(cwd / wrapper), *(args.paths or [':shared:testDebugUnitTest', ':app-elder:assembleDemoDebug', ':app-family:assembleDemoDebug'])]
    else:
        if args.check == 'integration':
            sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
            from backend.tests.support import require_test_database
            try:
                require_test_database(env.get('TEST_DATABASE_URL'))
            except ValueError as exc:
                parser.error(str(exc))
            paths = args.paths or ['backend/tests/integration']
        elif args.check == 'windows':
            paths = args.paths or ['windows/tests']
        else:
            paths = args.paths or ['backend/tests', 'tests']
        command = [sys.executable, '-m', 'pytest', '-c', str(ROOT / 'pytest.ini'), '-q', *paths]
        if args.check == 'test':
            command += ['--ignore=backend/tests/integration']
    return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
