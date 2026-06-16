# Week 2 — "Door Opens" Video Storyboard

**Runtime:** 18s total (3 × 6s shots)  
**Post copy:** *Door's open. Look — don't touch everything yet.* + demo link  
**Tooling:** Grok PWA `/imagine` per shot → `/imagine-video` per shot → FFmpeg concat

---

## Shot 1 — The hum (0:00–0:06)

**Beat:** Something's awake. No product name yet.

**Frame prompt (`/imagine` 16:9):**
```
Dark server room silhouette, single monitor glow, purple pulse on black, minimal, mysterious, offline hardware energy, no readable text, cinematic wide
```

**Motion prompt (`/imagine-video` 6s):**
```
Slow push-in toward glowing monitor in dark room, purple pulse once, calm tension, 6 seconds
```

**On-screen caption (add in post):** *The lab stays private.*

---

## Shot 2 — The door (0:06–0:12)

**Beat:** Peek — not the whole thing.

**Frame prompt (`/imagine` 16:9):**
```
Cyber-romantic UI portal door opening in digital void, purple gradient light through crack, glassmorphism, procedural particles, teaser not full reveal, no text
```

**Motion prompt (`/imagine-video` 6s):**
```
Door seam widens slightly, light breathes brighter once, camera slow orbit left, 6 seconds, mysterious
```

**On-screen caption:** *Your hardware. Your rules.*

---

## Shot 3 — The proof (0:12–0:18)

**Beat:** Scene demo exists. Click implied.

**Frame prompt (`/imagine` 16:9):**
```
Illustrated scene demo UI control panel floating on procedural purple night gradient, dawn day dusk night buttons glowing, listening state green accent, parallax circles, screen capture style art, no gibberish text
```

**Motion prompt (`/imagine-video` 6s):**
```
UI state shifts idle to listening, accent color green sweep, subtle parallax drift, 6 seconds, confident
```

**End card (add in post):** demo URL

---

## Assembly (FFmpeg)

```bash
# Same resolution/fps on all clips required
ffmpeg -f concat -safe 0 -i shots.txt -c copy week2-door-opens.mp4
```

`shots.txt`:
```
file 'shot1.mp4'
file 'shot2.mp4'
file 'shot3.mp4'
```

---

## X posting order (Week 2)

| When | What |
|------|------|
| Day 8 AM | Text only: *Door's open. Look — don't touch everything yet.* + link |
| Day 8 PM | 18s video (this storyboard) |
| Day 9 | Scene glow still from shot 3 frame |

Save outputs → `merch-social/visuals/teasers/week2-door-opens.mp4`