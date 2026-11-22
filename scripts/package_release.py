"""Build a runtime ZIP from an explicit list of distributable files."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package():
    files = [ROOT / name for name in ('forum_api.py', 'hot_forum.py', 'config.example.json', 'LICENSE', 'README.md', 'docs/reader-demo.png')]
    files.extend((ROOT / 'forum_backend').rglob('*.py'))
    web = ROOT / 'web'
    if not (web / 'index.html').is_file() or not (web / 'THIRD-PARTY.md').is_file():
        raise SystemExit('请先运行 npm --prefix frontend run build')
    files.extend(web / name for name in ('index.html', 'manifest.webmanifest', 'favicon.svg',
                 'app-icon-192.png', 'app-icon-512.png', 'apple-touch-icon.png', 'THIRD-PARTY.md'))
    for ext in ('*.css', '*.js'):
        files.extend((web / 'assets').glob(ext))
    output = ROOT / 'dist/discuz-reader-0.1.0.zip'
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix('.tmp')
    with ZipFile(temporary, 'w', compression=ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(file, 'discuz-reader/' + file.relative_to(ROOT).as_posix())
    temporary.replace(output)
    print(output)


if __name__ == '__main__':
    package()
