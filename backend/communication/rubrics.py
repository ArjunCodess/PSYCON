"""Versioned goals and metric-grounded adjustments, never personality scores."""
VERSION = "communication-rubrics-2"
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
ADJUSTMENTS.update({
    "clear_instruction_per_turn": ("Explicit actions can make the next step easier to identify.", "Name the action and the person responsible, then invite clarification."),
    "structured_explanation_per_turn": ("A stated main point and example can make the explanation easier to follow.", "Give the main point, one reason, and one example before continuing."),
    "unexplained_jargon_per_turn": ("An unexplained term may leave someone needing clarification.", "Explain the term in everyday language and ask whether an example would help."),
    "discovery_question_per_turn": ("Questions about needs can clarify which explanation is relevant.", "Ask about one need or constraint before describing a solution."),
    "supported_reasoning_per_turn": ("Explicit reasons make a claim's basis available for review.", "State the claim, the supporting reason, and what remains uncertain."),
    "cross_question_per_turn": ("Specific questions can clarify how a claim is supported.", "Ask about one assumption or piece of evidence before changing topics."),
    "concession_per_turn": ("Accepting a valid point may help identify common ground.", "Name one point you accept before describing what you still disagree with."),
    "direct_answer_per_opportunity": ("A direct answer can help keep the response relevant to the question.", "Answer the question in one sentence before adding context."),
    "adaptation_per_opportunity": ("A different example may help after explicit confusion.", "Offer a simpler explanation, then invite another question."),
    "counterargument_acknowledgement_per_opportunity": ("Acknowledgement can clarify the counterargument you are responding to.", "Restate the counterargument fairly before giving your response."),
    "concise_rebuttal_per_opportunity": ("A brief rebuttal can leave time to examine the point being challenged.", "Address one disputed point in a short response, then pause."),
    "defensive_response_per_opportunity": ("Evading a concrete criticism may leave its issue unresolved.", "Acknowledge the concrete issue and answer it before explaining your position."),
    "objection_response_per_opportunity": ("Addressing a stated barrier can clarify whether the proposal fits.", "Ask about the barrier, then address it explicitly."),
    "concern_acknowledgement_per_opportunity": ("Recognizing a concern can help keep advice relevant to it.", "Summarize the concern before explaining a possible next step."),
})
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
ROLE_METRICS = {
    "general": ["acknowledgement_per_turn", "clarification_per_turn", "structured_explanation_per_turn"],
    "leadership": ["clear_instruction_per_turn", "acknowledgement_per_turn", "counterargument_acknowledgement_per_opportunity"],
    "sales": ["discovery_question_per_turn", "objection_response_per_opportunity"],
    "teaching": ["structured_explanation_per_turn", "unexplained_jargon_per_turn", "adaptation_per_opportunity"],
    "law": ["direct_answer_per_opportunity", "supported_reasoning_per_turn", "cross_question_per_turn"],
    "debate": ["counterargument_acknowledgement_per_opportunity", "concession_per_turn", "concise_rebuttal_per_opportunity"],
    "negotiation": ["clarification_per_turn", "concession_per_turn", "counterargument_acknowledgement_per_opportunity"],
    "medicine": ["concern_acknowledgement_per_opportunity", "unexplained_jargon_per_turn", "structured_explanation_per_turn"],
    "student": ["structured_explanation_per_turn", "direct_answer_per_opportunity"],
    "presentation": ["structured_explanation_per_turn", "direct_answer_per_opportunity", "unexplained_jargon_per_turn"],
}
