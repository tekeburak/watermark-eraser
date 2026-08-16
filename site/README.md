# Site

Static landing page for watermark-eraser, served by GitHub Pages.
No framework, no build step — plain HTML/CSS (`index.html` + `assets/style.css`).

- Live at: <https://tekeburak.github.io/watermark-eraser/>
- Deployed by [`.github/workflows/site.yml`](../.github/workflows/site.yml) on every push to
  `main` that touches `site/**`

## Local preview

```bash
python3 -m http.server 8000 --directory site
# open http://localhost:8000
```

The workflow deploys whatever is in `site/` — to change the page, edit
`index.html` / `assets/style.css` and push to `main`.
