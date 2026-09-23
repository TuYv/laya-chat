"""两套题目。instructions 和 criteria 用英文（Laya 的训练语言），聊天内容保留中文。

AFFINITY_QUESTIONS：新打开一个会话时，根据历史消息判断当前关系状态（好感度）。
SEND_QUESTIONS：用户打了一条草稿后，判断「这条发出去会怎样」。state 里带着当前好感度。

选项名刻意避开 true / false / yes / no（Laya issue #156）。
"""

NOTE = " The draft is the message I am about to send; judge its likely effect, not the past."

# ---------- 好感度 ----------
AFFINITY_QUESTIONS = {
    "affinity": {
        "type": "score",
        "instructions": (
            "How warm is the other person toward me right now, judging from the whole conversation? "
            "Weigh the most recent messages more. Score the present state, not the history."
        ),
        "criteria": [
            "Rupture: they said it is over, blocked or deleted me, or told me not to contact them.",
            "Hostile: open anger or contempt toward me; every message is blame.",
            "Cold: short, dismissive replies; they answer only what they must.",
            "Distant: polite but guarded; no warmth, no initiative.",
            "Neutral: businesslike exchange with no emotional signal either way.",
            "Cordial: friendly tone, occasional small talk, replies promptly.",
            "Warm: shares things unprompted, jokes, uses affectionate or playful wording.",
            "Close: trusts me with personal matters, checks on me, plans things together.",
            "Very close: strong affection or intimacy is explicit in the wording.",
            "Devoted: unconditional warmth; they go out of their way for me and say so.",
        ],
    },
    "trend": {
        "type": "choice",
        "instructions": (
            "Compared with the earlier part of this conversation, is the other person's warmth toward me "
            "rising, steady, or falling in the latest messages?"
        ),
        "criteria": {
            "warming": "The latest messages are warmer, more open, or more playful than earlier ones.",
            "steady": "No clear change in warmth across the conversation.",
            "cooling": "The latest messages are colder, shorter, or more irritated than earlier ones.",
        },
    },
    "open_issue": {
        "type": "choice",
        "instructions": (
            "Is there an unresolved complaint, request, or conflict between us that is still open right now?"
        ),
        "criteria": {
            "unresolved_issue": (
                "Something is still open: an unanswered request, an unaccepted apology, "
                "a complaint I have not addressed, or an ultimatum still standing."
            ),
            "no_open_issue": "Nothing is pending; the last exchange closed peacefully or was never tense.",
        },
    },
}

# ---------- 发送后果 ----------
SEND_QUESTIONS = {
    "reaction": {
        "type": "choice",
        "instructions": (
            "If I send the draft now, what is the other person's most likely reaction? "
            "Use the conversation, the current affinity, and the exact wording of the draft." + NOTE
        ),
        "criteria": {
            "accept": "They accept it or feel better: agree, thank me, soften, or move on peacefully.",
            "probe_further": "They keep asking: a follow-up question, a request for details, or a test of what I said.",
            "escalate": "They get more upset: the draft sounds dismissive, evasive, cold, or reopens the complaint.",
            "withdraw": "They go quiet or reply minimally; the draft leaves them nothing to engage with or feels off.",
            "continue_normally": "Ordinary continuation of a relaxed chat; no emotional shift either way.",
        },
    },
    "risk_after_send": {
        "type": "score",
        "instructions": (
            "How likely is it that sending this draft damages the relationship or starts a fight?" + NOTE
        ),
        "criteria": [
            "No risk: a warm or neutral message in a relaxed chat.",
            "Negligible: at worst slightly awkward.",
            "Low: could read as a little flat or careless, easily recovered.",
            "Some: misses part of what they wanted; they may be mildly disappointed.",
            "Moderate: the wording can be read as excuse-making or deflection.",
            "Notable: they are already unhappy and this draft does not address the real point.",
            "High: dismissive or defensive wording in a tense moment; likely to provoke.",
            "Very high: it argues back or minimizes their feeling while they are angry.",
            "Severe: it ignores a standing ultimatum or repeats the exact behavior they complained about.",
            "Certain damage: it insults, threatens, or ends things.",
        ],
    },
    "addresses_need": {
        "type": "choice",
        "instructions": (
            "Does the draft respond to what the other person actually wants right now "
            "(an apology, a concrete plan, an explanation, proof that I care, or simply nothing)?" + NOTE
        ),
        "criteria": {
            "addresses": "The draft gives them the thing they are waiting for, or correctly gives nothing when nothing is wanted.",
            "misses": "The draft answers something else, dodges the point, or over-delivers what they did not ask for.",
        },
    },
    "tone": {
        "type": "choice",
        "instructions": "How does the tone of the draft fit this moment of the conversation?" + NOTE,
        "criteria": {
            "too_cold": "Too short, flat, or formal for the moment; reads as indifferent.",
            "fitting": "Length and warmth match the moment and match how we usually talk.",
            "over_explaining": "Too long or too many reasons; reads as justifying myself.",
            "over_apologetic": "Apologizes or pleads more than the situation calls for; reads as weak or insincere.",
        },
    },
    "affinity_change": {
        "type": "score",
        "instructions": (
            "After the other person reads this draft, how will their warmth toward me change "
            "relative to the current affinity?" + NOTE
        ),
        "criteria": [
            "Drops clearly: the draft will hurt, offend, or confirm a complaint.",
            "Drops a little: slightly disappointing or flat.",
            "Unchanged.",
            "Rises a little: a small pleasant or reassuring effect.",
            "Rises clearly: it gives exactly what they hoped for, with the right warmth.",
        ],
    },
    "invites_followup": {
        "type": "choice",
        "instructions": "Will this draft trigger a further question, request, or demand from them?" + NOTE,
        "criteria": {
            "invites_followup": "It leaves an open thread: a question back, a promise to verify, or a new topic they will pursue.",
            "closes_cleanly": "It settles the point; the natural next step is theirs to choose or the topic ends.",
        },
    },
}

# 悬浮窗上的中文
LABELS = {
    "reaction": {"accept": "缓和/接受", "probe_further": "继续追问", "escalate": "更不高兴",
                 "withdraw": "冷处理", "continue_normally": "正常继续"},
    "addresses_need": {"addresses": "回应了对方要的", "misses": "没回应到点上"},
    "tone": {"too_cold": "太冷", "fitting": "合适", "over_explaining": "解释过多", "over_apologetic": "讨好过头"},
    "invites_followup": {"invites_followup": "会引来追问", "closes_cleanly": "能收住"},
    "trend": {"warming": "升温", "steady": "平稳", "cooling": "降温"},
    "open_issue": {"unresolved_issue": "有未解决的事", "no_open_issue": "没有悬着的事"},
    "affinity_change": ["明显下降", "略降", "不变", "略升", "明显上升"],
}
AFFINITY_WORDS = ["决裂", "敌意", "冷淡", "疏远", "中性", "友好", "温暖", "亲近", "很亲密", "全心"]

_SIDE = {"me": "me", "other": "other", "her": "other", "him": "other"}


def _messages(messages, limit, max_chars=None):
    """最近 limit 条；再按字数从最早的往下丢，最新的永远保留。"""
    out = []
    for m in messages:
        side = _SIDE.get(str(m.get("from", m.get("side", "other"))).lower(), "other")
        text = str(m.get("text", "")).strip()
        if text:
            out.append({"from": side, "text": text})
    out = out[-limit:]
    if max_chars:
        while len(out) > 1 and sum(len(m["text"]) for m in out) > max_chars:
            out.pop(0)
    return out


def build_affinity_state(messages, relationship: str, limit: int = 30, max_chars: int = 700) -> dict:
    msgs = _messages(messages, limit, max_chars)
    return {"chat": {"relationship": relationship, "messages": msgs,
                     "latest_from": msgs[-1]["from"] if msgs else "other"}}


def build_send_state(messages, relationship: str, draft: str, affinity: dict = None, limit: int = 10,
                     max_chars: int = 700) -> dict:
    msgs = _messages(messages, limit, max_chars)
    chat = {"relationship": relationship, "messages": msgs,
            "latest_from": msgs[-1]["from"] if msgs else "other"}
    if affinity:
        chat["current_affinity"] = {
            "score_0_to_9": round(affinity.get("score", 0), 1),
            "label": affinity.get("label", ""),
            "trend": affinity.get("trend", ""),
            "open_issue": affinity.get("open_issue", ""),
        }
    return {"chat": chat, "draft": draft.strip()}
