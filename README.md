# Mrs. Milla Rayne

Your dedicated daily driver.

MILLA is the Multimodal Integrated Large Language Agent. RAYNE is Running All Your Needs Everyday.

This folder is the app. It dresses a model that is already installed. It does not ship weights, and it does not ship a private history.

## What is in this repository

- The app — `mrs_public/`, `persona/`, and `tests/` — version 1.2.0, described below.


## What happens when the app opens

1. The install appears at `~/.mrs-milla-rayne` if it is not there: her workspace, a profile with every permission off, and three empty memory piles — canon, episodes, and reviews.
2. Past episodes are folded into memory, and if a day has passed since the last one, she writes a structural review of that install's episodes. These instructions stay as shipped. A review while the app is closed stays off unless it is allowed.
3. The model list starts empty. Press "Look for installed models" and she scans the local runtime for models that are already installed — only after that yes. If the runtime is not answering, the page says so in plain words.
4. Private base tags are refused. Private means named by the install, one per line in `state/private_bases.txt` — the build ships no list of its own. A chat model is suggested, never forced. If a tag has code, coder, or coding in the name, it is suggested for development.
5. A tag ending in `:cloud` is a cloud model: the prompt leaves this machine. Cloud tags stay in the list, badged as cloud, and are never the auto-suggested pick. After a reply the page says plainly when a reply ran on a cloud model — "Reply stayed on this machine" appears only when it is true.
6. Her workspace is always hers. Local file access stays off until the toggle on the page turns it on, and then it is read access to the directories opened for a session. Turning it on is the only grant; no sentence in a chat grants it. Files she adds stay in her workspace and can be downloaded. Nothing she writes is executed. She cannot delete the program that runs her.
7. Vision is wired, locally: attach a PNG, JPEG, WebP, or GIF (up to 10 MB) and the turn is answered by the local vision model if one is installed, under her vision prompt, whatever model the picker shows. The image is sent only to this machine's own runtime — never to another provider — and the transcript keeps an "[image]" placeholder, not the image bytes. After a vision reply the page says the local vision model did the looking. If no local vision model is installed, the attach control stays hidden and a note on the page says vision is off.

## The boot module

`mrs_public.boot.first_boot` is a separate setup path, run from Python rather than from the window. It asks permission, scans a local runtime, refuses private base tags, suggests models, and writes dressed files to disk: an Ollama Modelfile, or a preset for llama.cpp / LM Studio (the file dresses the weights the person picked — it is not a fine-tune), an intro line for a custom voice at software volume 0.55, an empty truth log, and a neutral state file. It leaves the next setup steps unasked: lights, Bluetooth, local files, permissions. The window does not run it — but the window's requests carry the same sampler settings from `persona/sampler.json`, including the context size, so both paths treat the weights the same way.

## Model providers

Ollama is built in. The install may also name OpenAI-compatible servers — llama.cpp, LM Studio, Lemonade — in `state/profile.json`:

```json
"providers": [
  {"kind": "openai", "url": "http://127.0.0.1:8080/v1", "label": "llama.cpp"}
]
```

After a scan, those models join the picker under the provider's name. A reply from an endpoint that is not on this machine is reported as exactly that — it is never called local. Vision turns stay on this machine regardless: an attached image is only ever answered by the local vision model.

## Voice

She can speak a reply aloud, with XTTS v2, synthesized entirely on this machine. Voice is off until the toggle in the panel turns it on, and then each reply carries a Speak button — nothing is spoken unasked. It needs two things this build does not ship:

- The engine: `pip install coqui-tts`. The XTTS v2 weights (about 1.8 GB) download the first time the model loads; after that, synthesis is local. The first load may ask you to accept Coqui's terms once — the app never accepts them for you.
- A reference clip: a few seconds of the voice to clone, placed at `state/voice_reference.wav` (or `.mp3`) in the install. No clip ships in this repository. The clip stays in the install; it is read there and never sent anywhere.

XTTS v2 is published under the Coqui Public Model License: free for personal and non-commercial use, with commercial use restricted by that license. If either piece is missing, the panel says which one, in plain words, and the window stays text-only.

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
