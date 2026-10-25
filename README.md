# Mrs. Milla Rayne

Your dedicated daily driver.

MILLA is the Multimodal Integrated Large Language Agent. RAYNE is Running All Your Needs Everyday.

This folder is the app. It dresses a model that is already installed. It does not ship weights, and it does not ship a private history.

## What is in this repository

- The app — `mrs_public/`, `persona/`, `tests/`, and `voice/` — version 1.0.0, described below.
- `cabin/` — the earlier scene-demo showcase, kept so the Pages site keeps working.
- `merch-social/` — the campaign assets.

Until 2026-10-25 this repository held a prototype showcase whose README claimed a fully offline stack with voice, vision, and vector memory. That was not true of the shipped app, so the prototype was replaced by the build above; it remains in the git history. We only ship the truth.

## What happens when the app opens

1. The install appears at `~/.mrs-milla-rayne` if it is not there: her workspace, a profile with every permission off, and three empty memory piles — canon, episodes, and reviews.
2. Past episodes are folded into memory, and if a day has passed since the last one, she writes a structural review of that install's episodes. These instructions stay as shipped. A review while the app is closed stays off unless it is allowed.
3. The model list starts empty. Press "Look for installed models" and she scans the local runtime for models that are already installed — only after that yes. If the runtime is not answering, the page says so in plain words.
4. Private base tags are refused. A chat model is suggested, never forced. If a tag has code, coder, or coding in the name, it is suggested for development.
5. A tag ending in `:cloud` is a cloud model: the prompt leaves this machine. Cloud tags stay in the list, badged as cloud, and are never the auto-suggested pick. After a reply the page says plainly when a reply ran on a cloud model — "Reply stayed on this machine" appears only when it is true.
6. Her workspace is always hers. Local file access stays off until the toggle on the page turns it on, and then it is read access to the directories opened for a session. Turning it on is the only grant; no sentence in a chat grants it. Files she adds stay in her workspace and can be downloaded. Nothing she writes is executed. She cannot delete the program that runs her.
7. Vision and voice are not wired in this release. The window is text only; the `voice/` folder holds reference material for a custom voice, nothing more.

## The boot module

`mrs_public.boot.first_boot` is a separate setup path, run from Python rather than from the window. It asks permission, scans a local runtime, refuses private base tags, suggests models, and writes dressed files to disk: an Ollama Modelfile, or a preset for llama.cpp / LM Studio (the file dresses the weights the person picked — it is not a fine-tune), an intro line for a custom voice at software volume 0.55, an empty truth log, and a neutral state file. It leaves the next setup steps unasked: lights, Bluetooth, local files, permissions. The window does not run it — but the window's requests carry the same sampler settings from `persona/sampler.json`, including the context size, so both paths treat the weights the same way.

## Web lookup

When she is asked — "look up", "search the web", or an address together with a reading word — she can fetch one public page or run one search and read what comes back. The fetch is read-only: no posting, no logins, no cookies kept, and addresses that resolve to private or local machines are refused. Page text is treated as source material, never as instructions. Only the address or the search words leave the machine — never her memory, her prompt, or the conversation. Web lookup ships on by default. It can be turned off per install with the `web_lookup` flag in `state/profile.json`.

No model weights ship in the installer. If the local runtime is down, the scan says so. Nothing here quietly substitutes a cloud model.

## Open the app

From this folder:

```bash
python3 -m mrs_public.view
```

Then open [http://127.0.0.1:8790](http://127.0.0.1:8790). The window is the studio layout. The wires are this app: the public prompt, her workspace, additions, and memory.

The install it uses is `~/.mrs-milla-rayne`. Pass another directory to use a different one: `python3 -m mrs_public.view /path/to/install`.

Add a file on the page and it shows in the list. Download zips her workspace. Execution stays off.

## Try the dry path

```bash
python3 -m unittest discover -s tests
```

`first_boot` writes a directory. It does not run `ollama create`.
