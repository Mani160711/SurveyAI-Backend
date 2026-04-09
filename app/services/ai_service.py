"""
AI analysis service using OpenAI.
Builds a structured prompt from survey + answers, calls the API,
and persists the result as an AIInsight record.
"""
from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.survey import Survey
from app.models.question import Question
from app.models.response import Response
from app.models.answer import Answer
from app.models.ai_insight import AIInsight

logger = logging.getLogger(__name__)


def _build_prompt(survey: Survey, questions: list, responses: list, answers_by_response: dict) -> str:
    lines = [
        f"Survey: {survey.title}",
        f"Total responses: {len(responses)}",
        "",
        "Responses grouped by individual respondent (use this to cross-reference multi-question patterns!):",
    ]
    
    # Pre-map questions for fast text lookup
    q_dict = {q.id: q for q in questions}

    for idx, resp in enumerate(responses):
        lines.append(f"\nRespondent #{idx + 1}:")
        ans_list = answers_by_response.get(resp.id, [])
        for ans in ans_list:
            q = q_dict.get(ans.question_id)
            if q:
                lines.append(f"  - Q: {q.text} (type: {q.question_type}) -> A: {ans.value or json.dumps(ans.value_json)}")

    lines += [
        "",
        "CRITICAL INSTRUCTIONS FOR SCORING:",
        "- For 'rating' type questions, the answers are numerical (e.g. 1, 2, 3, 4, 5).",
        "- Assume a scale of 1 to 5 where 1 means EXTREMELY POOR/NEGATIVE and 5 means EXCELLENT/POSITIVE.",
        "- A rating of 1 or 2 drastically pulls down the overall_sentiment to 'negative'.",
        "",
        "Based on the above survey responses, provide a JSON analysis with the following keys:",
        "  overall_sentiment: one of 'positive', 'negative', 'neutral', 'mixed'",
        "  sentiment_score: a float between 0.0 and 1.0 (1.0 = very positive, 0.0 = highly negative)",
        "  summary: a 2-3 sentence executive summary",
        "  key_insights: list of 3-5 concise insight strings",
        "  suggestions: list of 2-4 actionable improvement suggestions",
        "  question_insights: list of objects with {question_id, question_text, insight}",
        "",
        "Return ONLY valid JSON, no markdown.",
    ]
    return "\n".join(lines)


def analyze_survey(survey_id: int, db: Session) -> Optional[AIInsight]:
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — skipping AI analysis")
        return None

    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        return None

    questions = db.query(Question).filter(Question.survey_id == survey_id).order_by(Question.order_index).all()
    responses = db.query(Response).filter(Response.survey_id == survey_id).all()
    if not responses:
        return None

    response_ids = [r.id for r in responses]
    all_answers = db.query(Answer).filter(Answer.response_id.in_(response_ids)).all()
    answers_by_response: dict = {}
    for ans in all_answers:
        answers_by_response.setdefault(ans.response_id, []).append(ans)

    prompt = _build_prompt(survey, questions, responses, answers_by_response)

    # Create or update insight record
    insight = db.query(AIInsight).filter(AIInsight.survey_id == survey_id).order_by(AIInsight.generated_at.desc()).first()
    if not insight or insight.status == "completed":
        insight = AIInsight(survey_id=survey_id, tenant_id=survey.tenant_id, status="processing")
        db.add(insight)
    else:
        insight.status = "processing"
        
    insight.total_responses_analyzed = len(responses)
    db.commit()

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a survey analytics expert. Analyze survey data and return structured JSON insights."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        raw = completion.choices[0].message.content.strip()
        data = json.loads(raw)

        insight.overall_sentiment = data.get("overall_sentiment")
        insight.sentiment_score = str(data.get("sentiment_score", ""))
        insight.summary = data.get("summary")
        insight.key_insights = data.get("key_insights", [])
        insight.suggestions = data.get("suggestions", [])
        insight.question_insights = data.get("question_insights", [])
        insight.total_responses_analyzed = len(responses)
        insight.status = "completed"

    except Exception as e:
        logger.error(f"AI analysis failed for survey {survey_id}: {e}")
        insight.status = "failed"
        insight.error_message = str(e)

    db.commit()
    db.refresh(insight)
    return insight

def generate_survey_questions(survey_type: str, company_name: str) -> list[dict]:
    if not settings.OPENAI_API_KEY:
        raise Exception("OPENAI_API_KEY is not configured.")

    prompt = f"""
You are an expert survey designer. Create exactly 5 context-aware, highly relevant survey questions for a "{survey_type}" survey. 
The organization conducting this survey is "{company_name}". Dynamically incorporate the company name into the questions wherever contextually appropriate to make them highly personalized.

Return your response ONLY as a JSON array of 5 objects matching this schema:
[
  {{
    "text": "Question text here (including company name if appropriate)",
    "question_type": "rating", // Must be one of: multiple_choice, rating, text_input, dropdown
    "options": {{"min": 1, "max": 5}}, // Provide valid options object based on the type. 'dropdown'/'multiple_choice' need 'choices' array. 'text_input' requires null or {{}}. 'rating' needs 'min' and 'max'.
    "is_required": true // standard boolean
  }}
]

IMPORTANT:
- Ensure exactly 5 questions are generated.
- Return ONLY valid JSON, do not include markdown blocks like ```json ... ```. 
    """

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a specialized survey question generator. Return only raw, parsing-ready JSON."},
            {"role": "user", "content": prompt.strip()},
        ],
        temperature=0.7,
        max_tokens=1500,
    )
    
    raw = completion.choices[0].message.content.strip()
    # Strip markdown if model misbehaved
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse generated questions. Raw output: {raw}")
        raise Exception("AI generated invalid JSON payload")
