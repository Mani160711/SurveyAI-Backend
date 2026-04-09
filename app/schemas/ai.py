from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class AIGeneratedQuestionOut(BaseModel):
    text: str
    question_type: str
    options: Optional[Dict[str, Any]] = None
    is_required: bool

class AIGenerateRequest(BaseModel):
    survey_type: str
