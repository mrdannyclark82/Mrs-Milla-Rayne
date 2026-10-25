"""Locked public names. House weights are named here only so auto-setup skips them."""

PRODUCT = "Mrs. Milla Rayne"
LINE = "your dedicated daily driver"
MILLA = "Multimodal Integrated Large Language Agent"
RAYNE = "Running All Your Needs Everyday"

HOUSE_BASES = frozenset(
    {
        "milla-rayne",
        "mrdannyclark82/milla-rayne",
        "devmilla",
    }
)

CODER_HINTS = ("coder", "coding", "code")
VISION_HINTS = ("vision", "moondream", "llava", "bakllava")
EMBED_HINTS = ("embed", "nomic-embed")

INTRO = (
    "Hello. I'm Mrs. Milla Rayne, your dedicated daily driver. "
    "Multimodal Integrated Large Language Agent. "
    "Running All Your Needs Everyday. "
    "We'll set the rest of this machine up together."
)

SPEAK_VOLUME = 0.55

SETUP_STEPS = ("lights", "bluetooth", "local_files", "permissions")
