# components/quizzes.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from beanie import Document, PydanticObjectId
from beanie.operators import Inc

from core.security import get_current_user
from components.users import User

router = APIRouter(prefix="/api/quizzes", tags=["Quizzes"])

# --- Beanie Document Model ---
class Quiz(Document):
    question_pt: str
    question_en: str
    options_pt: List[str]
    options_en: List[str]
    correctAnswerIndex: int
    reward: int
    isActive: bool = True

    class Settings:
        name = "quizzes"

# --- DTOs ---
class QuizQuestionResponse(BaseModel):
    quizId: PydanticObjectId
    question: str
    options: List[str]

class QuizSubmit(BaseModel):
    quizId: PydanticObjectId
    answerIndex: int

class QuizResultResponse(BaseModel):
    isCorrect: bool
    message: str
    new_balance: int | None = None

# --- Endpoints ---
@router.get("/random", response_model=QuizQuestionResponse)
async def get_random_quiz(current_user: User = Depends(get_current_user)):
    user_lang = current_user.language
    random_quiz = await Quiz.find_one(Quiz.isActive == True).aggregate(
        [{"$sample": {"size": 1}}]
    ).to_list(1)

    if not random_quiz:
        raise HTTPException(status_code=404, detail="No active quizzes found.")
    
    quiz = random_quiz[0]
    return QuizQuestionResponse(
        quizId=quiz["_id"],
        question=quiz.get(f"question_{user_lang}", quiz["question_en"]),
        options=quiz.get(f"options_{user_lang}", quiz["options_en"])
    )

@router.post("/submit", response_model=QuizResultResponse)
async def submit_quiz_answer(submission: QuizSubmit, current_user: User = Depends(get_current_user)):
    quiz = await Quiz.get(submission.quizId)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    if quiz.correctAnswerIndex == submission.answerIndex:
        await current_user.update(Inc({User.hc_balance: quiz.reward}))
        return QuizResultResponse(
            isCorrect=True,
            message=f"Correct! You earned {quiz.reward} HC.",
            new_balance=current_user.hc_balance + quiz.reward
        )
    else:
        return QuizResultResponse(isCorrect=False, message="Sorry, that's not right.")

@router.post("/dev/seed", response_model=Quiz, include_in_schema=False)
async def seed_quiz_data():
    """Endpoint to add a sample quiz to the DB. Not for production."""
    await Quiz.delete_all()
    sample_quiz = Quiz(
        question_pt="Qual é a capital de Angola?",
        question_en="What is the capital of Angola?",
        options_pt=["Luanda", "Huambo", "Benguela", "Cabinda"],
        options_en=["Luanda", "Huambo", "Benguela", "Cabinda"],
        correctAnswerIndex=0,
        reward=50,
        isActive=True
    )
    await sample_quiz.create()
    return sample_quiz