"""Read contextual human observations without changing labels or research inputs."""


def observations(store, session_id):
    """Only current reviewed speaker associations can join human answers to reports."""
    return store.rows("""
        WITH mappings AS (
            SELECT DISTINCT ON (participant_id) * FROM speaker_mappings
            WHERE session_id=%s ORDER BY participant_id,revision DESC
        ), submissions AS (
            SELECT DISTINCT ON (s.participant_id,s.form_id,s.source_type,s.reviewer_id) s.*
            FROM annotation_submissions s JOIN session_participants p ON p.id=s.participant_id
            WHERE p.session_id=%s AND p.owner_id='local' AND p.withdrawn_at IS NULL
            AND s.form_id='at-4.0'
            ORDER BY s.participant_id,s.form_id,s.source_type,s.reviewer_id,s.revision DESC
        )
        SELECT a.*,s.participant_id,p.code AS participant_code,m.speaker_id,
               m.revision AS mapping_revision,s.form_id,s.source_type,s.reviewer_id,
               s.revision AS label_revision,f.description,
               coalesce(r.decision,'needs_review') AS review_status,
               r.reviewer_id AS independent_reviewer_id,
               j.score AS adjudicated_score,j.reviewer_id AS adjudicator_id,
               j.rationale AS adjudication_rationale,
               coalesce(e.windows,'[]'::jsonb) AS evidence_windows
        FROM submissions s JOIN session_participants p ON p.id=s.participant_id
        JOIN mappings m ON m.participant_id=p.id AND m.status='confirmed'
        LEFT JOIN people person ON person.id=p.person_id
        JOIN annotation_answers a ON a.submission_id=s.id
        JOIN form_items f ON f.form_id=s.form_id AND f.key=a.item_key
        LEFT JOIN LATERAL (
            SELECT * FROM annotation_reviews WHERE submission_id=s.id
            ORDER BY created_at DESC,id DESC LIMIT 1
        ) r ON true
        LEFT JOIN LATERAL (
            SELECT * FROM annotation_adjudications WHERE answer_id=a.id
            ORDER BY created_at DESC,id DESC LIMIT 1
        ) j ON true
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object('kind',kind,'start',start_s,'end',end_s,
                'context',context,'response',response,'participation_effect',participation_effect,
                'evidence_id',evidence_id) ORDER BY start_s,end_s,id) AS windows
            FROM annotation_evidence WHERE answer_id=a.id
        ) e ON true
        WHERE person.withdrawn_at IS NULL
        ORDER BY a.item_key,s.source_type,s.reviewer_id,s.id
    """, (session_id, session_id))
