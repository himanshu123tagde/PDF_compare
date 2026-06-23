import re

JUNK_PATTERNS = [
    r"subscribe",
    r"sign up",
    r"newsletter",
    r"advertisement",
    r"cookie policy",
    r"accept cookies",
    r"we use cookies",
    r"follow us",
    r"share this",
    r"share on",
    r"all rights reserved",
    r"read more",
    r"click here",
    r"terms of service",
    r"privacy policy",
    r"sponsored",
    r"related articles",
    r"recommended for you",
    r"you may also like",
    r"leave a comment",
    r"log in to",
    r"sign in",
    r"create account",
    r"download the app",
    r"get the app",
    r"©\s*\d{4}",
    r"posted by",
    r"tags:",
    r"categories:",
    r"share via",
    r"tweet this",
    r"pin it",
    r"print this",
    r"email this",
    r"comments are closed",
    r"notify me",
    r"your email",
    r"submit comment",
    r"leave a reply",
    r"powered by",
    r"loading\.\.\.",
    r"please wait",
    r"enable javascript",
]

JUNK_COMPILED = [re.compile(p, re.IGNORECASE) for p in JUNK_PATTERNS]


def is_junk_line(line: str) -> bool:
    if len(line) < 3:
        return True

    if any(p.search(line) for p in JUNK_COMPILED):
        return True

    word_count = len(line.split())
    if word_count < 3 and not line.endswith((".", "!", "?", ":")):
        return True

    if line.count("|") > 2 or line.count("•") > 2:
        return True

    link_pattern = re.compile(r"https?://\S+")
    links = link_pattern.findall(line)
    words = line.split()
    if links and len(links) >= len(words) // 2:
        return True

    return False


def clean_text(text: str) -> str:
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []

    for line in lines:
        if not line:
            continue
        if is_junk_line(line):
            continue
        cleaned_lines.append(line)

    text = "\n\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()