# components/dev.py

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

# Import all Beanie models to be managed
from data.models import Quiz
from beanie import PydanticObjectId

router = APIRouter(prefix="/api/dev", tags=["Developer"])

# --- DTOs for Quiz Seeding ---
class QuizSeedItem(BaseModel):
    """Represents a single quiz question to be seeded."""
    question_pt: str
    question_en: str
    options_pt: List[str]
    options_en: List[str]
    correctAnswerIndex: int

class QuizSeedPayload(BaseModel):
    """The payload for the seed-quiz endpoint, containing a list of quizzes."""
    quizzes: List[QuizSeedItem]


@router.post("/seed-quiz")
async def seed_quiz_data(payload: QuizSeedPayload):
    """
    Endpoint to add multiple quizzes to the DB from a dictionary payload.
    It checks for duplicate questions (based on 'question_en') and skips them.
    Not for production use.
    """
    added_count = 0
    skipped_count = 0

    for quiz_data in payload.quizzes:
        # Check if a quiz with the same English question already exists
        existing_quiz = await Quiz.find_one({"question_en": quiz_data.question_en})

        if existing_quiz:
            skipped_count += 1
            continue  # Skip to the next item if a duplicate is found
        
        # If no duplicate, create and insert the new quiz
        new_quiz = Quiz(
            **quiz_data.model_dump(),
            isActive=True  # Ensure all seeded quizzes are active
        )
        await new_quiz.create()
        added_count += 1

    return {
        "message": "Quiz seeding process completed.",
        "quizzes_added": added_count,
        "duplicates_skipped": skipped_count
    }

class VerifyUserPayload(BaseModel):
    email: str

@router.post("/verify-user-email")
async def verify_user_email(payload: VerifyUserPayload):
    """
    Manually verify a user's email for testing purposes.
    """
    from data.models import User
    from fastapi import HTTPException
    
    user = await User.find_one(User.email == payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.is_email_verified = True
    await user.save()
    
    return {"message": f"User {user.username} ({user.email}) email verified successfully."}

