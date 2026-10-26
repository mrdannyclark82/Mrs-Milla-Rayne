"""Locked public names. Private bases are named by the install, never here."""

PRODUCT = "Mrs. Milla Rayne"
LINE = "your dedicated daily driver"
MILLA = "Multimodal Integrated Large Language Agent"
RAYNE = "Running All Your Needs Everyday"

# No private base ships in this build. An install names its own private
# bases in state/private_bases.txt (see models.is_house); auto-setup skips
# those, so a dressed house weight is never suggested or dressed again.
HOUSE_BASES: frozenset[str] = frozenset()

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
