"""Bundle local sources into a single offline HTML. Python standard library only."""
from pathlib import Path
root = Path(__file__).resolve().parent
css = '\n'.join((root / name).read_text() for name in ['tokens.css', 'styles.css'])
js = (root / 'app.js').read_text()
html = '''<!doctype html>
<html lang="zh-CN" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'">
<meta name="color-scheme" content="light dark"><title>Kebui U1 Design Demo</title>
<style>''' + css + '''</style></head><body><div id="app"></div><dialog id="dialog" aria-label="Kebui design demo"></dialog><div id="live" role="status" aria-live="polite"></div><script>''' + js + '''</script></body></html>'''
(root / 'index.html').write_text(html)
print(f'Built index.html: {len(html.encode())} bytes')
