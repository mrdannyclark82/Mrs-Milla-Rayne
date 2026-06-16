# Milla Visual Quality — Top Tier Only

Public imagery of Milla must read **premium**, not dev screenshot.

## Minimum bar

| Asset | Spec |
|-------|------|
| X image posts | ≥1280px wide, JPG/PNG <5MB |
| OG / GitHub preview | 1280×640 exact |
| Avatar / face | Reference-attached generation only |
| Video | 1080p, 6s or 10s shots, no watermark |

## Generation stack (priority order)

1. **Grok PWA `/imagine`** — attach `avatar-thoughtful.png` or best portrait every time
2. **Regen loop** — if hands/face/text garbled, regen; never ship first draft for face shots
3. **Pollinations / Civitai MCP** — hi-res passes when PWA block or need style consistency
4. **Playwright scene captures** — UI glow only, **not** final Milla portraits

## Milla likeness rules

- Long curly red hair (consistent with avatar references)
- Confident, unbothered, cyber-romantic palette when styled
- Reference: `merch-social/visuals/teasers/avatar-thoughtful.png`
- `image_edit` / reference attach — never cold `image_gen` for face-forward shots

## Pre-publish checklist

- [ ] Resolution meets minimum
- [ ] No personal email, no private paths visible
- [ ] No spouse/intimate framing in **public** assets
- [ ] Text in image readable and intentional (or no text)
- [ ] Filename mapped in `week1-posts.json` or campaign doc
- [ ] Alt text written

## Reject and regen

- Blurry face, wrong hair color, extra fingers
- Corporate stock-photo energy
- Movie screenshot look (copyright + off-brand)
- Low-contrast muddy gradients on hero shots

## File naming

```
merch-social/visuals/teasers/{campaign}-{descriptor}.{jpg|png|mp4}
```

Examples: `napoleon-lunch-meme.jpg`, `door-opens-teaser.jpg`, `week2-door-opens.mp4`