"""Creator-type personalization. Pure data: one universal app, different words, shortcuts and suggestions.
Add a new creator type by adding one entry here. Nothing else needs to change."""

CREATOR_TYPES = {
    "influencer": {
        "label": "Influencer",
        "labels": {
            "deals": "Deals", "deal": "deal", "deals_lower": "deals", "add_deal": "Add deal",
            "deliverables_hint": "2 reels, 3 stories", "event": "shoot", "add_event": "Add event",
            "event_hint": "Shoot at Bandra studio", "due_label": "deliverables due",
            "tagline": "Here's what needs your attention today.", "pages_sub": "Track every paid and barter collaboration.",
        },
        "chips": ["List my deals", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a barter deal with Mamaearth", "Book a cab from Panvel to Bandra tomorrow at 4 pm",
                             "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "Reels, stories and a short review around your product",
        "deliverable_examples": ["Reels", "Stories", "Carousel posts"],
        "default_platforms": ["instagram", "youtube"],
    },
    "youtuber": {
        "label": "YouTuber",
        "labels": {
            "deals": "Sponsorships", "deal": "sponsorship", "deals_lower": "sponsorships", "add_deal": "Add sponsorship",
            "deliverables_hint": "1 integration, 1 dedicated video", "event": "video shoot", "add_event": "Add shoot or upload",
            "event_hint": "Film sponsored video", "due_label": "videos due",
            "tagline": "Sponsorships, uploads and what's due this week.", "pages_sub": "Track every sponsorship and integration.",
        },
        "chips": ["List my sponsorships", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a sponsorship with boAt", "Schedule video shoot tomorrow at 11 am",
                             "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "A dedicated video or a sponsored integration, with a clear call to action",
        "deliverable_examples": ["Integration", "Dedicated video", "Shorts"],
        "default_platforms": ["youtube", "instagram"],
    },
    "gamer": {
        "label": "Gamer",
        "labels": {
            "deals": "Sponsorships", "deal": "sponsorship", "deals_lower": "sponsorships", "add_deal": "Add sponsorship",
            "deliverables_hint": "2 streams, 1 tournament mention", "event": "stream", "add_event": "Add stream or match",
            "event_hint": "Tournament stream", "due_label": "streams due",
            "tagline": "Sponsorships, streams and tournaments coming up.", "pages_sub": "Track sponsorships and gaming deliverables.",
        },
        "chips": ["List my sponsorships", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a sponsorship with Noise", "Schedule stream tomorrow at 9 pm",
                             "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "Sponsored streams, in-game mentions and tournament coverage",
        "deliverable_examples": ["Sponsored stream", "Tournament mention", "Gameplay video"],
        "default_platforms": ["youtube", "twitch"],
    },
    "streamer": {
        "label": "Streamer",
        "labels": {
            "deals": "Sponsorships", "deal": "sponsorship", "deals_lower": "sponsorships", "add_deal": "Add sponsorship",
            "deliverables_hint": "3 sponsored streams, chat commands", "event": "stream", "add_event": "Add stream",
            "event_hint": "Sponsored stream", "due_label": "streams due",
            "tagline": "Sponsorships and your stream schedule.", "pages_sub": "Track sponsorships and stream deliverables.",
        },
        "chips": ["List my sponsorships", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a sponsorship with Cult.fit", "Schedule stream tomorrow at 8 pm",
                             "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "Sponsored live streams with on-screen placement and chat engagement",
        "deliverable_examples": ["Sponsored stream", "On-screen banner", "Chat command"],
        "default_platforms": ["twitch", "youtube"],
    },
    "podcaster": {
        "label": "Podcaster",
        "labels": {
            "deals": "Sponsorships", "deal": "sponsorship", "deals_lower": "sponsorships", "add_deal": "Add sponsorship",
            "deliverables_hint": "3 ad reads, 1 show note mention", "event": "recording", "add_event": "Add recording",
            "event_hint": "Record episode", "due_label": "episodes due",
            "tagline": "Sponsorship slots, episodes and recordings.", "pages_sub": "Track sponsorship slots and episodes.",
        },
        "chips": ["List my sponsorships", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a sponsorship with Wakefit", "Schedule recording tomorrow at 4 pm",
                             "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "Host-read ad slots and show note mentions across upcoming episodes",
        "deliverable_examples": ["Pre-roll ad read", "Mid-roll ad read", "Show notes link"],
        "default_platforms": ["spotify", "youtube"],
    },
    "blogger": {
        "label": "Blogger",
        "labels": {
            "deals": "Collaborations", "deal": "collaboration", "deals_lower": "collaborations", "add_deal": "Add collaboration",
            "deliverables_hint": "1 blog post, 2 social posts", "event": "shoot", "add_event": "Add event",
            "event_hint": "Photo shoot", "due_label": "posts due",
            "tagline": "Collaborations, posts and deadlines.", "pages_sub": "Track every collaboration and post.",
        },
        "chips": ["List my collaborations", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a barter deal with Nykaa", "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "A detailed blog post with photos plus social promotion",
        "deliverable_examples": ["Blog post", "Social post", "Newsletter mention"],
        "default_platforms": ["instagram", "linkedin"],
    },
    "other": {
        "label": "Other creator",
        "labels": {
            "deals": "Deals", "deal": "deal", "deals_lower": "deals", "add_deal": "Add deal",
            "deliverables_hint": "What you will deliver", "event": "event", "add_event": "Add event",
            "event_hint": "Meeting or shoot", "due_label": "deliverables due",
            "tagline": "Here's what needs your attention today.", "pages_sub": "Track every collaboration.",
        },
        "chips": ["List my deals", "Check my inbox", "Any follow-ups pending?"],
        "chat_suggestions": ["Add a deal with Mamaearth", "Check my inbox", "Any follow-ups pending?"],
        "pitch_offer": "Content tailored to your audience and the campaign goals",
        "deliverable_examples": ["Content piece", "Social post", "Appearance"],
        "default_platforms": ["instagram"],
    },
}

PLATFORMS = {
    "instagram": {"label": "Instagram", "domains": ["instagram.com"], "base": "https://www.instagram.com/"},
    "youtube":   {"label": "YouTube", "domains": ["youtube.com", "youtu.be"], "base": "https://www.youtube.com/@"},
    "twitch":    {"label": "Twitch", "domains": ["twitch.tv"], "base": "https://www.twitch.tv/"},
    "facebook":  {"label": "Facebook", "domains": ["facebook.com", "fb.com"], "base": "https://www.facebook.com/"},
    "threads":   {"label": "Threads", "domains": ["threads.net", "threads.com"], "base": "https://www.threads.net/@"},
    "x":         {"label": "X (Twitter)", "domains": ["x.com", "twitter.com"], "base": "https://x.com/"},
    "tiktok":    {"label": "TikTok", "domains": ["tiktok.com"], "base": "https://www.tiktok.com/@"},
    "linkedin":  {"label": "LinkedIn", "domains": ["linkedin.com"], "base": "https://www.linkedin.com/in/"},
    "pinterest": {"label": "Pinterest", "domains": ["pinterest.com", "pin.it"], "base": "https://www.pinterest.com/"},
    "spotify":   {"label": "Spotify", "domains": ["spotify.com"], "base": "https://open.spotify.com/"},
}

LANGUAGES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED"]
PAYMENT_METHODS = ["upi", "bank", "other"]


def persona(creator_type: str) -> dict:
    return CREATOR_TYPES.get(creator_type) or CREATOR_TYPES["influencer"]


def options() -> dict:
    """What the profile form can offer. Sent to the browser so the UI never hard-codes these lists."""
    return {
        "creator_types": [{"id": k, "label": v["label"], "examples": v["deliverable_examples"],
                           "default_platforms": v["default_platforms"]} for k, v in CREATOR_TYPES.items()],
        "platforms": [{"id": k, "label": v["label"], "base": v["base"]} for k, v in PLATFORMS.items()],
        "languages": [{"id": k, "label": v} for k, v in LANGUAGES.items()],
        "currencies": CURRENCIES,
        "payment_methods": PAYMENT_METHODS,
    }
