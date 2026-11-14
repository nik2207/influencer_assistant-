from . import llm

NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


def translate(text: str, target: str) -> str:
    """LLM-based translation. Swap in IndicTrans2 here if you have a GPU."""
    prompt = (
        f"Translate the following text to {NAMES[target]}. "
        f"Return only the translation, nothing else.\n\n{text}"
    )
    return llm.simple_completion(prompt)
