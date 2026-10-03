"""Versioned goals and metric-grounded adjustments, never personality scores."""
VERSION = "communication-rubrics-1"
ROLES = {
    "general": ["turn-taking", "listening", "concision", "clear explanations"],
    "leadership": ["contribution space", "clear instructions", "acknowledgement", "disagreement"],
    "sales": ["discovery questions", "conversational balance", "concision", "objections"],
    "teaching": ["explanation structure", "jargon", "space for questions", "clarification"],
    "law": ["direct answers", "supported reasoning", "cross-questioning", "response structure"],
    "debate": ["counterarguments", "concessions", "floor management", "concise rebuttals"],
    "negotiation": ["acknowledgement", "clarifying interests", "concessions", "floor management"],
    "medicine": ["space for concerns", "understandable explanations", "acknowledgement", "balance"],
    "student": ["structure", "pacing", "concision", "audience questions"],
    "presentation": ["structure", "pacing", "concision", "audience questions"],
}
ADJUSTMENTS = {
    "speaking_share": ("Others may have less room to contribute.", "Finish your point, then invite another person to respond."),
    "mean_turn_duration_s": ("Longer turns can leave fewer opportunities for questions.", "State the main point first, then pause for a question."),
    "candidate_interruptions_per_min": ("Starting during another turn may limit their opportunity to finish.", "Let the speaker finish, acknowledge the point, then respond."),
    "articulation_rate_wpm": ("A change in pace may affect how easy the explanation is to follow.", "Pause between key points and ask whether a clarification would help."),
    "response_gap_s": ("A change in response timing can alter conversational flow.", "Allow a short pause and acknowledge the preceding point before answering."),
    "pause_mean_s": ("Longer pauses may change the pace of the exchange.", "Take time to organize your response, then state the main point first."),
    "acknowledgement_per_turn": ("Acknowledging a point can make it easier to address the concern behind it.", "Begin by acknowledging the preceding point before explaining your response."),
    "clarification_per_turn": ("Clarifying questions can help establish what the other person needs.", "Ask one clarifying question before giving another explanation."),
}
ROLE_ADJUSTMENTS = {
    "leadership": "After your point, invite a dissenting view and acknowledge it before explaining your decision.",
    "sales": "Ask one question about the customer's concern before adding another product explanation.",
    "teaching": "Explain one idea, pause for a question, and offer a simpler example when clarification is requested.",
    "law": "Answer the question directly before adding supporting reasoning.",
    "debate": "Acknowledge a valid part of the counterargument before giving a concise rebuttal.",
    "negotiation": "Ask a clarifying question about the other person's interest before restating your position.",
    "medicine": "Invite the patient to finish their concern before explaining the next step in plain language.",
    "student": "State your main point, give one supporting example, and pause for questions.",
    "presentation": "Pause after each main point and answer audience questions before returning to the presentation.",
}
