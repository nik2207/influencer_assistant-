import json
import re
from datetime import datetime, timedelta

import httpx

from ..config import settings
from . import outreach


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Return an assistant message: {"content": str|None, "tool_calls": [...]|None}."""
    if settings.llm_provider == "openai_compat":
        return _openai_compat(messages, tools)
    return _mock(messages)


def _openai_compat(messages, tools):
    payload = {"model": settings.llm_model, "messages": messages, "temperature": 0.2}
    if tools:
        payload["tools"] = tools
    r = httpx.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def simple_completion(prompt: str) -> str:
    """One-shot text helper (used for translation and pitch polishing)."""
    if settings.llm_provider != "openai_compat":
        return prompt
    msg = _openai_compat([{"role": "user", "content": prompt}], None)
    return (msg.get("content") or "").strip()


# ---------------------------------------------------------------- mock brain
# A small rule-based stand-in so the whole product runs with no model or API key.

def _call(name: str, args: dict) -> dict:
    return {"content": None, "tool_calls": [{
        "id": f"mock-{name}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }]}


# Demo-only helpers so the rule-based brain understands common Hindi and Marathi words.
# A real LLM (see README) understands full sentences; this just keeps the offline demo useful.
DEVANAGARI = {
    "बार्टर": "barter", "डील": "deal", "कॅब": "cab", "कैब": "cab", "टॅक्सी": "taxi", "इनव्हॉइस": "invoice",
    "इनवॉइस": "invoice", "ईमेल": "email", "इनबॉक्स": "inbox", "मेल": "mail", "शेड्यूल": "schedule",
    "कैलेंडर": "calendar", "कॅलेंडर": "calendar", "फॉलोअप": "follow up", "फॉलो": "follow up",
    "ब्रँड": "brand", "ब्रांड": "brand", "जोडा": "add", "जोड़ो": "add", "जोड़": "add", "करायची": "add",
    "करायचा": "add", "बनवा": "add", "सिंक": "sync",
}


def _normalize(low: str) -> str:
    extra = [en for hi, en in DEVANAGARI.items() if hi in low]
    return low + (" " + " ".join(extra) if extra else "")


def _find_brand(text: str) -> str | None:
    low = text.lower()
    for b in outreach.load_brands():
        if b["name"].lower() in low:
            return b["name"]
    return None


def _parse_when(text: str) -> str:
    now = datetime.now()
    day = now
    t = text.lower()
    if re.search(r"\b(tomorrow|udya|kal)\b", t):
        day = now + timedelta(days=1)
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje|vajta|vajata)?", t)
    hour, minute = 10, 0
    if m:
        hour = int(m.group(1)) % 24
        minute = int(m.group(2) or 0)
        if m.group(3) == "pm" and hour < 12:
            hour += 12
        elif m.group(3) in (None, "baje", "vajta", "vajata") and 1 <= hour <= 7:
            hour += 12
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="minutes")


def _lang_from_messages(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") != "system":
            continue
        body = m.get("content") or ""
        if "reply in Hindi" in body:
            return "hi"
        if "reply in Marathi" in body:
            return "mr"
    return "en"


def _mock(messages: list[dict]) -> dict:
    lang = _lang_from_messages(messages)
    last = messages[-1]
    if last["role"] == "tool":
        return {"content": _summarize(last.get("name", ""), json.loads(last["content"]), lang), "tool_calls": None}

    text = last["content"].strip()
    low = _normalize(text.lower())

    if re.search(r"\b(cab|taxi|ride|porter|cargo)\b", low):
        kind = "porter" if re.search(r"\b(porter|cargo)\b", low) else "cab"
        m = re.search(r"from\s+(.+?)\s+to\s+(.+?)(?:\s+(?:at|by|tomorrow|today)\b|$)", text, re.I)
        pickup, drop = (m.group(1), m.group(2)) if m else ("Home", "Studio")
        return _call("book_ride", {"kind": kind, "pickup": pickup, "drop": drop, "when": _parse_when(low)})

    m = re.search(r"\b(draft|write|prepare)\b.*\b(reply|response)\b.*?(\d+)", low)
    if m and re.search(r"\bemail|mail\b", low):
        return _call("draft_email_reply", {"email_id": int(m.group(3))})

    if re.search(r"\bfollow[- ]?ups?\b|\bpending repl(y|ies)\b|\bnot replied\b", low):
        return _call("check_followups", {})

    if re.search(r"\bsync\b.*\bcalendar\b|\bcalendar\b.*\bsync\b", low):
        return _call("sync_calendar", {})

    if re.search(r"\b(emails?|inbox|mails?|gmail)\b", low):
        return _call("check_inbox", {})

    if re.search(r"\boverdue\b.*\binvoices?\b|\binvoices?\b.*\boverdue\b", low):
        return _call("list_overdue_invoices", {})

    m = re.search(r"\brecord\b.*\bpayment\b.*?₹?\s*([\d,]+)", text, re.I)
    if m:
        amt = float(m.group(1).replace(",", ""))
        inv_m = re.search(r"\binvoice\b\s*#?(\w[\w\-]*)", low)
        num_m = re.search(r"\bINV[-\d]+", text, re.I)
        args = {"amount_inr": amt}
        if inv_m:
            args["invoice_number"] = inv_m.group(1)
        elif num_m:
            args["invoice_number"] = num_m.group(0)
        ids = re.findall(r"\b(\d+)\b", low)
        if ids and "invoice" in low:
            args["invoice_id"] = int(ids[-1])
        return _call("record_invoice_payment", args)

    if re.search(r"\b(add|log)\b.*\bexpense\b", low):
        v = re.search(r"(?:₹|rs\.?|inr)\s?([\d,]+)", low)
        if not v:
            return {"content": "How much was the expense, and what was it for?", "tool_calls": None}
        cat = "travel" if re.search(r"\b(cab|travel|ride)\b", low) else "other"
        return _call("add_expense", {"amount_inr": float(v.group(1).replace(",", "")), "description": text[:200],
                                      "category": cat})

    if re.search(r"\bexpenses?\b.*\b(this month|month)\b", low):
        return _call("list_expenses", {})

    if re.search(r"\bpayment\b.*\breminder\b|\breminder\b.*\bpayment\b|\bdraft\b.*\breminder\b", low):
        num_m = re.search(r"\bINV[-\w]+", text, re.I)
        args = {}
        if num_m:
            args["invoice_number"] = num_m.group(0)
        ids = re.findall(r"\b(\d+)\b", low)
        if ids:
            args["invoice_id"] = int(ids[0])
        return _call("draft_payment_reminder", args)

    if "invoice" in low and re.search(r"\b(create|make|new)\b", low):
        m = re.search(r"\bdeal\b\s*#?(\d+)", low) or re.search(r"\d+", low)
        if m:
            return _call("create_invoice", {"deal_id": int(m.group(1) if m.lastindex else m.group())})

    if re.search(r"\b(three|3)\b.*\bpitch", low) or re.search(r"\bpitch(es)?\b.*\bfor\b", low):
        m = re.search(r"(?:for|to)\s+([A-Z][\w&.\- ]+)", text) or re.search(r"\b(Nykaa|Mamaearth|boAt|Noise|Lenskart|Zepto|Swiggy)\b", text, re.I)
        brand = m.group(1).strip() if m else "the brand"
        return _call("generate_pitch_studio", {"brand": brand})

    if re.search(r"\bmore professional\b", low) and "pitch" in low:
        return {"content": "Open the Pitch Studio from Brands, select a draft, and use Regenerate with a professional tone — your edits are kept until you regenerate.", "tool_calls": None}

    if re.search(r"\btranslate\b.*\bpitch\b", low) and re.search(r"\b(marathi|mr|hindi|hi)\b", low):
        lang = "mr" if re.search(r"\b(marathi|mr)\b", low) else "hi"
        return {"content": f"Open Pitch Studio, edit your pitch, and choose language {lang} when regenerating (requires a connected LLM for translation).", "tool_calls": None}

    if re.search(r"\bsave\b.*\b(gmail|draft)\b", low) and "pitch" in low:
        return {"content": "In Pitch Studio, click Save draft, then Save to Gmail Drafts. Nothing is sent automatically — you review in Gmail first.", "tool_calls": None}

    if "pitch" in low:
        m = re.search(r"(?:to|for)\s+([A-Z][\w&.\- ]+)", text)
        return _call("draft_pitch", {"brand": m.group(1).strip() if m else "the brand"})

    if re.search(r"\b(suggest|recommend)\b.*\bbrands?\b|\bbrands?\b.*\b(suggest|reach out)\b", low):
        return _call("suggest_brands", {})

    if re.search(r"\b(mark|move|update)\b.*\bdeal\b", low):
        ids = re.findall(r"\d+", low)
        for stage in ["payment_pending", "product_received", "content_due", "negotiating", "confirmed", "posted", "done", "cancelled", "lead"]:
            if stage.replace("_", " ") in low or stage in low:
                if ids:
                    return _call("update_deal_status", {"deal_id": int(ids[0]), "status": stage})

    if re.search(r"\b(add|new|got|create)\b.*\b(deal|barter|collab)\b|\b(deal|barter|collab)\b.*\b(add|new|got|create)\b", low):
        m = re.search(r"(?:with|from|for)\s+([A-Z][\w&.\-]*)", text)
        known = _find_brand(text)
        v = re.search(r"(?:rs\.?|₹|inr)\s?([\d,]+)", low)
        args = {"brand": known or (m.group(1) if m else "Unknown brand"), "kind": "barter" if "barter" in low else "paid"}
        if v:
            args["value_inr"] = float(v.group(1).replace(",", ""))
        return _call("add_deal", args)

    if re.search(r"\b(deals?|barters?|pipeline)\b", low):
        return _call("list_deals", {})

    if re.search(r"\b(add|schedule|book|set)\b.*\b(shoot|meeting|event|call|shoot)\b", low):
        title = re.sub(r"\b(at|tomorrow|today)\b.*", "", text, flags=re.I).strip() or "Event"
        return _call("add_event", {"title": title, "start": _parse_when(low)})

    if re.search(r"\b(schedule|calendar|agenda|today|week)\b", low):
        return _call("list_events", {"days": 7})

    help_en = (
        "I can track deals and barters, manage your schedule, book cabs and porters (with your approval), "
        "create invoices, suggest brands and draft pitches. Try: 'Add a barter deal with Mamaearth' "
        "or 'Book a cab from Panvel to Bandra tomorrow at 4 pm'."
    )
    help_hi = (
        "मैं डील और बार्टर ट्रैक कर सकता हूँ, शेड्यूल मैनेज कर सकता हूँ, कैब/पोर्टर बुक कर सकता हूँ (आपकी मंज़ूरी से), "
        "इनवॉइस बना सकता हूँ, ब्रांड सुझा सकता हूँ और पिच ड्राफ्ट कर सकता हूँ। उदाहरण: 'Mamaearth के साथ बार्टर डील जोड़ो'।"
    )
    help_mr = (
        "मी डील आणि बार्टर ट्रॅक करू शकतो, शेड्यूल व्यवस्थापित करू शकतो, कॅब/पोर्टर बुक करू शकतो (तुमच्या मंजुरीने), "
        "इनव्हॉइस तयार करू शकतो, ब्रँड सुचवू शकतो आणि पिच ड्राफ्ट करू शकतो. उदा: 'Mamaearth सोबत बार्टर डील जोडा'."
    )
    help = {"en": help_en, "hi": help_hi, "mr": help_mr}
    return {"content": help.get(lang, help_en), "tool_calls": None}


def _summarize(tool: str, r: dict, lang: str = "en") -> str:
    if "error" in r:
        if lang == "hi":
            return f"माफ़ कीजिए, यह काम नहीं हुआ: {r['error']}"
        if lang == "mr":
            return f"माफ करा, ते जमले नाही: {r['error']}"
        return f"Sorry, that did not work: {r['error']}"
    if r.get("status") == "awaiting_user_approval":
        if lang == "hi":
            return f"मैंने यह तैयार किया है: {r['summary']}. नीचे मंज़ूरी दें।"
        if lang == "mr":
            return f"मी हे तयार केले: {r['summary']}. खाली मंजुरी द्या."
        return f"I prepared this for you: {r['summary']}. Please approve it below."
    if tool == "add_deal":
        d = r["deal"]
        if lang == "hi":
            return f"{d['brand']} के साथ {d['kind']} डील #{d['id']} जोड़ दी (स्थिति: {d['status']})।"
        if lang == "mr":
            return f"{d['brand']} सोबत {d['kind']} डील #{d['id']} जोडली (स्थिती: {d['status']})."
        return f"Added {d['kind']} deal #{d['id']} with {d['brand']} (stage: {d['status']})."
    if tool == "list_deals":
        if not r["deals"]:
            return "You have no deals yet."
        return "Your deals:\n" + "\n".join(
            f"#{d['id']} {d['brand']} ({d['kind']}) - {d['status']}" for d in r["deals"])
    if tool == "update_deal_status":
        d = r["deal"]
        return f"Deal #{d['id']} with {d['brand']} is now '{d['status']}'."
    if tool == "add_event":
        e = r["event"]
        msg = f"Added '{e['title']}' on {e['start']}." + (" Also added to Google Calendar." if r.get("google_synced") else "")
        if r["conflicts"]:
            msg += " Warning, this clashes with: " + ", ".join(c["title"] for c in r["conflicts"]) + "."
        return msg
    if tool == "list_events":
        if not r["events"]:
            return "Nothing scheduled in the next 7 days."
        return "Coming up:\n" + "\n".join(f"{e['start']} - {e['title']}" for e in r["events"])
    if tool == "create_invoice":
        i = r["invoice"]
        link = f" Payment link: {i['payment_link']}" if i.get("payment_link") else ""
        return f"Invoice {i['number']} for INR {i['amount_inr']:,.0f} is ready.{link}"
    if tool == "list_overdue_invoices":
        if not r["invoices"]:
            return "You have no overdue invoices."
        return "Overdue invoices:\n" + "\n".join(
            f"#{x['id']} {x['number']} {x['client']} — ₹{x['balance_inr']:,.0f} due {x.get('due_date') or '?'}"
            for x in r["invoices"])
    if tool == "record_invoice_payment":
        return f"Recorded payment on {r['number']}. Status: {r['status']}. Total received: ₹{r['paid_inr']:,.0f}."
    if tool == "add_expense":
        e = r["expense"]
        return f"Logged expense #{e['id']}: ₹{e['amount_inr']:,.0f} ({e['category']}) — {e['description']}."
    if tool == "list_expenses":
        if not r["expenses"]:
            return "No expenses logged this month yet."
        return f"Expenses this month (₹{r['total_inr']:,.0f}):\n" + "\n".join(
            f"{x['spent_on']} ₹{x['amount_inr']:,.0f} {x['category']}: {x['description']}" for x in r["expenses"])
    if tool == "draft_payment_reminder":
        return r["draft"] + "\n\n(" + r.get("note", "") + ")"
    if tool == "draft_pitch":
        return r["pitch"] + ("\n\n" + r.get("studio_hint", "") if r.get("studio_hint") else "")
    if tool == "generate_pitch_studio":
        if not r.get("suggestions"):
            return r.get("error", "Could not generate pitches.")
        lines = [f"**{s['tone_label']}**\nSubject: {s['subject']}\n{s['body'][:400]}..." for s in r["suggestions"]]
        return "Here are three pitch options for " + r["brand"] + ":\n\n" + "\n\n---\n\n".join(lines) + "\n\n" + r.get("studio_hint", "")
    if tool == "check_inbox":
        if not r["emails"]:
            return "No new brand emails right now."
        lines = [f"#{e['id']} {e['brand']} - {e['category'].replace('_', ' ')}: {e['summary']}" for e in r["emails"]]
        return f"{r['new_count']} new brand email(s). Open ones:\n" + "\n".join(lines)
    if tool == "draft_email_reply":
        return f"Draft for email #{r['email_id']} (not sent):\n\n{r['draft']}"
    if tool == "check_followups":
        if not r["followups"]:
            return "No follow-ups waiting. Everyone has been answered."
        lines = []
        for f in r["followups"]:
            what = "is waiting for your reply" if f["state"] == "needs_reply" else "has not replied to you"
            lines.append(f"#{f['id']} {f['brand']} {what} ({f['days_waiting']} days): {f['subject']}")
        return "Follow-ups:\n" + "\n".join(lines)
    if tool == "sync_calendar":
        return (f"Calendar synced. Sent {r['pushed']} event(s) to Google, imported {r['created']}, "
                f"updated {r['updated']}, removed {r['removed']}.")
    if tool == "suggest_brands":
        return "Brands that fit your niche:\n" + "\n".join(f"{b['name']} ({b['category']})" for b in r["brands"])
    return json.dumps(r, default=str)
