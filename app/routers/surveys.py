from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from typing import List
import pandas as pd
from io import BytesIO
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.survey import Survey
from app.models.question import Question
from app.models.response import Response
from app.schemas.survey import SurveyCreate, SurveyUpdate, SurveyOut, SurveyListItem, QuestionCreate, QuestionOut, QuestionUpdate

router = APIRouter(prefix="/surveys", tags=["surveys"])


def _assert_survey_owner(survey: Survey, user: User):
    if survey.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")


@router.post("", response_model=SurveyOut, status_code=201)
def create_survey(payload: SurveyCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    import secrets
    
    file_content = None
    file_name = None
    if payload.audience_file_path:
        import os
        if os.path.exists(payload.audience_file_path):
            with open(payload.audience_file_path, "rb") as bf:
                file_content = bf.read()
            file_name = os.path.basename(payload.audience_file_path)
            try:
                os.remove(payload.audience_file_path)
            except Exception:
                pass

    survey = Survey(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        title=payload.title,
        description=payload.description,
        public_token=f"{current_user.user_uuid}-{secrets.token_urlsafe(16)}",
        audience_file_content=file_content,
        audience_file_name=file_name
    )
    db.add(survey)
    db.flush()

    for q in payload.questions or []:
        question = Question(
            survey_id=survey.id,
            tenant_id=current_user.tenant_id,
            text=q.text,
            question_type=q.question_type,
            options=q.options,
            is_required=q.is_required,
            order_index=q.order_index,
        )
        db.add(question)

    db.commit()
    db.refresh(survey)
    survey = db.query(Survey).options(selectinload(Survey.questions)).filter(Survey.id == survey.id).first()
    response_count = db.query(func.count(Response.id)).filter(Response.survey_id == survey.id).scalar()
    result = SurveyOut.model_validate(survey)
    result.response_count = response_count
    
    return result


@router.get("", response_model=List[SurveyListItem])
def list_surveys(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    surveys = db.query(Survey).filter(Survey.tenant_id == current_user.tenant_id, Survey.is_active == True).order_by(Survey.created_at.desc()).all()
    result = []
    for s in surveys:
        count = db.query(func.count(Response.id)).filter(Response.survey_id == s.id).scalar()
        item = SurveyListItem.model_validate(s)
        item.response_count = count
        result.append(item)
    return result


@router.get("/{survey_id}", response_model=SurveyOut)
def get_survey(survey_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).options(selectinload(Survey.questions)).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _assert_survey_owner(survey, current_user)
    response_count = db.query(func.count(Response.id)).filter(Response.survey_id == survey.id).scalar()
    result = SurveyOut.model_validate(survey)
    result.response_count = response_count
    return result


@router.patch("/{survey_id}", response_model=SurveyOut)
def update_survey(survey_id: int, payload: SurveyUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _assert_survey_owner(survey, current_user)
    was_published = survey.is_published

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(survey, field, val)
    db.commit()
    db.refresh(survey)

    with open("trigger_debug.log", "a") as f:
        f.write(f"PATCH called. Previous: {was_published}, New: {survey.is_published}, Audience File Name: {survey.audience_file_name}\n")

    # Trigger logic for automated audience notification could go here (e.g. via SMS API)
    # The previous WhatsApp bot logic was removed as it is incompatible with cloud deployment.

    survey = db.query(Survey).options(selectinload(Survey.questions)).filter(Survey.id == survey.id).first()
    response_count = db.query(func.count(Response.id)).filter(Response.survey_id == survey.id).scalar()
    result = SurveyOut.model_validate(survey)
    result.response_count = response_count
    return result


@router.delete("/{survey_id}", status_code=204)
def delete_survey(survey_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _assert_survey_owner(survey, current_user)
    survey.is_active = False
    db.commit()


# ── Questions ──────────────────────────────────────────────────────────────────

@router.post("/{survey_id}/questions", response_model=QuestionOut, status_code=201)
def add_question(survey_id: int, payload: QuestionCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _assert_survey_owner(survey, current_user)
    q = Question(
        survey_id=survey_id,
        tenant_id=current_user.tenant_id,
        text=payload.text,
        question_type=payload.question_type,
        options=payload.options,
        is_required=payload.is_required,
        order_index=payload.order_index,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


@router.patch("/{survey_id}/questions/{question_id}", response_model=QuestionOut)
def update_question(survey_id: int, question_id: int, payload: QuestionUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _assert_survey_owner(survey, current_user)
    q = db.query(Question).filter(Question.id == question_id, Question.survey_id == survey_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(q, field, val)
    db.commit()
    db.refresh(q)
    return q


@router.delete("/{survey_id}/questions/{question_id}", status_code=204)
def delete_question(survey_id: int, question_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _assert_survey_owner(survey, current_user)
    q = db.query(Question).filter(Question.id == question_id, Question.survey_id == survey_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(q)
    db.commit()


# ── Public survey by token ────────────────────────────────────────────────────

@router.get("/public/{token}", response_model=SurveyOut)
def get_public_survey(token: str, db: Session = Depends(get_db)):
    survey = db.query(Survey).options(selectinload(Survey.questions)).filter(
        Survey.public_token == token,
        Survey.is_published == True,
        Survey.is_active == True,
    ).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found or not published")
    result = SurveyOut.model_validate(survey)
    result.response_count = 0
    return result


# ── Extractor ──────────────────────────────────────────────────────────────────

@router.post("/extract-phones")
async def extract_phones(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    contents = await file.read()
    filename = file.filename.lower()
    
    import os
    import secrets
    os.makedirs("uploads", exist_ok=True)
    safe_filename = f"{current_user.id}_{secrets.token_hex(4)}_{file.filename}"
    file_path = os.path.join("uploads", safe_filename).replace("\\", "/")
    
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(contents))
        elif filename.endswith((".xlsx", ".xls")):
            # Explicitly use openpyxl engine for .xlsx files to avoid engine detection issues in some environments
            engine = "openpyxl" if filename.endswith(".xlsx") else None
            df = pd.read_excel(BytesIO(contents), engine=engine)
        else:
            raise HTTPException(status_code=400, detail="Invalid file format. Only CSV and Excel files are supported.")
            
        if "phone_number" not in df.columns:
            raise HTTPException(status_code=400, detail="The file must contain a 'phone_number' column.")
            
        numbers = df["phone_number"].dropna().astype(str).str.strip()
        numbers = numbers[numbers != ""]
        unique_numbers = numbers.drop_duplicates().tolist()
        
        if not unique_numbers:
            raise HTTPException(status_code=400, detail="No valid phone numbers found in the file.")
            
        with open(file_path, "wb") as f:
            f.write(contents)
            
        return {
            "total": len(unique_numbers),
            "numbers": unique_numbers,
            "file_path": file_path
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
