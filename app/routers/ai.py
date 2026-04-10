from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.survey import Survey
from app.models.ai_insight import AIInsight
from app.models.tenant import Tenant
from app.schemas.ai_insight import AIInsightOut
from app.schemas.ai import AIGenerateRequest, AIGeneratedQuestionOut
router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/surveys/{survey_id}/analyze", status_code=202)
def trigger_analysis(survey_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id, Survey.tenant_id == current_user.tenant_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    def enqueue_ai_analysis_direct(sid: int):
        import logging
        logger = logging.getLogger(__name__)
        from app.core.database import SessionLocal
        from app.services.ai_service import analyze_survey
        db_session = SessionLocal()
        try:
            analyze_survey(sid, db_session)
            logger.info(f"Manual AI analysis completed natively for survey {sid}")
        except Exception as e:
            logger.warning(f"Native AI task failed manually. Error: {e}")
        finally:
            db_session.close()

    background_tasks.add_task(enqueue_ai_analysis_direct, survey_id)
    
    import secrets
    return {"message": "AI analysis natively queued", "task_id": secrets.token_hex(6)}


@router.get("/surveys/{survey_id}/insights", response_model=List[AIInsightOut])
def get_insights(survey_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id, Survey.tenant_id == current_user.tenant_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    insights = db.query(AIInsight).filter(AIInsight.survey_id == survey_id).order_by(AIInsight.generated_at.desc()).limit(5).all()
    return insights


@router.get("/surveys/{survey_id}/insights/latest", response_model=Optional[AIInsightOut])
def get_latest_insight(survey_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id, Survey.tenant_id == current_user.tenant_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    insight = db.query(AIInsight).filter(AIInsight.survey_id == survey_id).order_by(AIInsight.generated_at.desc()).first()
    return insight


@router.post("/generate-questions", response_model=List[AIGeneratedQuestionOut])
def generate_questions(payload: AIGenerateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services.ai_service import generate_survey_questions
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant not found")
    
    try:
        questions_data = generate_survey_questions(survey_type=payload.survey_type, company_name=tenant.name)
        # Parse output into Pydantic models
        parsed_questions = []
        for q in questions_data:
            parsed_questions.append(AIGeneratedQuestionOut(**q))
        return parsed_questions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
