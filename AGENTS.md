# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a minimal static HTML repository containing a single file (`Random`) that displays a golf tournament schedule (高爾夫球團體賽賽程) and group rankings (分組排名) in Traditional Chinese.

### Running the dev server

The file `Random` has no `.html` extension, so Python's default `http.server` will serve it with an incorrect MIME type (causing the browser to download instead of render). Use the included `serve.py` instead:

```
python3 serve.py
```

This starts an HTTP server on port 8080 that correctly serves `Random` as `text/html`. Access the page at `http://localhost:8080/Random`.

### Notes

- **No build step, linter, or test framework** is configured in this repository.
- The HTML references `style.css` and `script.js` which do not exist in the repository; the page renders without them but lacks styling and interactivity.
- The repository has no `package.json`, no Python requirements, and no other dependencies beyond Python 3 (pre-installed in the VM).
