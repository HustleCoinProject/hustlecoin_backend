# components/tasks.py
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from beanie import Document, PydanticObjectId
from beanie.operators import Inc, Set

from core.security import get_current_user
from .users import User

router = APIRouter(prefix="/api/tasks", tags=["Tasks & Quizzes"])

# --- Task Configuration ---
# This dictionary defines all available tasks, their rewards, and cooldowns in seconds.
# 'type' can be 'INSTANT' (like watching an ad) or 'QUIZ'.
TASK_CONFIG = {
    "watch_ad": {"reward": 100, "cooldown_seconds": 60, "type": "INSTANT", "description": "Watch a video ad"},
    "daily_tap": {"reward": 50, "cooldown_seconds": 86400, "type": "INSTANT", "description": "Daily login bonus"},
    "quiz_game": {"reward": 75, "cooldown_seconds": 300, "type": "QUIZ", "description": "Answer a quiz question"},

    # A quick tap to increment coin by 1, no cooldown
    "quick_tap": {"reward": 1, "cooldown_seconds": 0, "type": "INSTANT", "description": "Quick tap for 1 HC"},
}

# --- Beanie Document Model for Quizzes ---
class Quiz(Document):
    question_pt: str
    question_en: str
    options_pt: List[str]
    options_en: List[str]
    correctAnswerIndex: int
    isActive: bool = True

    class Settings:
        name = "quizzes" # This collection will still exist


# --- DTOs (Data Transfer Objects) ---
class TaskInfo(BaseModel):
    task_id: str
    description: str
    reward: int
    type: str
    cooldown_seconds: int


class TaskComplete(BaseModel):
    task_id: str
    # For quizzes, this payload will contain the answer
    payload: Dict[str, Any] | None = None


class BalanceUpdateResponse(BaseModel):
    message: str
    new_balance: int


class QuizQuestionResponse(BaseModel):
    quizId: PydanticObjectId
    question: str
    options: List[str]

# --- Endpoints ---




@router.get("/all", response_model=List[TaskInfo])
async def get_all_tasks():
    """Lists all available task types in the game."""
    task_list = []
    for task_id, config in TASK_CONFIG.items():
        task_list.append(TaskInfo(task_id=task_id, **config))
    return task_list




@router.post("/complete", response_model=BalanceUpdateResponse)
async def complete_task(
    completion_data: TaskComplete,
    current_user: User = Depends(get_current_user)
):
    """
    A generic endpoint to mark a task as completed and claim a reward.
    The logic is determined by the task_id.
    """
    task_id = completion_data.task_id
    config = TASK_CONFIG.get(task_id)

    if not config:
        raise HTTPException(status_code=404, detail="Task not found")

    # --- Cooldown Check ---
    last_completed = current_user.task_cooldowns.get(task_id)
    if last_completed and datetime.utcnow() < last_completed + timedelta(seconds=config["cooldown_seconds"]):
        raise HTTPException(status_code=429, detail="Task is on cooldown. Try again later.")

    reward_amount = 0

    # --- Task-specific Logic ---
    if task_id == "watch_ad":
        reward_amount = config["reward"]
        # In a real app, you might have server-to-server ad validation logic here
        
    elif task_id == "daily_tap":
        reward_amount = config["reward"]

    elif task_id == "quiz_game":
        # This task type requires a payload with the quiz answer
        payload = completion_data.payload
        if not payload or "quizId" not in payload or "answerIndex" not in payload:
            raise HTTPException(status_code=400, detail="Must have payload with quizId and answerIndex")
        
        quiz = await Quiz.get(PydanticObjectId(payload["quizId"]))
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        if quiz.correctAnswerIndex == payload["answerIndex"]:
            reward_amount = config["reward"]
        else:
            # If wrong, update cooldown but give no reward and return a specific message
            await current_user.update(Set({f"task_cooldowns.{task_id}": datetime.utcnow()}))
            raise HTTPException(status_code=400, detail="Incorrect answer. No reward given.")

    elif task_id == "quick_tap":
        # This task simply gives a small reward without cooldown
        reward_amount = config["reward"]
    else:
        raise HTTPException(status_code=400, detail="Unknown task completion logic.")

    # --- Grant Reward and Update Cooldown ---
    if reward_amount > 0:
        await current_user.update(
            Inc({User.hc_balance: reward_amount, User.hc_earned_in_level: reward_amount}),
            Set({f"task_cooldowns.{task_id}": datetime.utcnow()})
        )

    return BalanceUpdateResponse(
        message=f"Task '{task_id}' completed successfully!",
        new_balance=current_user.hc_balance
    )





# DOCS: Uses PyMongo here directly due to a bug that Motor/Beanie
#      has version mis-match with PyMongo. Bug is in Beanie or Motor.
@router.get("/quiz/fetch", response_model=QuizQuestionResponse)
async def fetch_quiz_question(current_user: User = Depends(get_current_user)):
    """Fetches a random quiz question for the quiz_game task."""
    user_lang = current_user.language

    # --- FIX START ---

    # 1. Get the underlying pymongo collection from the Beanie model
    #    using the correct method name from your traceback.
    collection = Quiz.get_pymongo_collection()

    # 2. Define the aggregation pipeline
    pipeline = [{"$match": {"isActive": True}}, {"$sample": {"size": 1}}]

    # 3. Create the cursor. Note there is NO `await` here. This returns
    #    the AsyncIOMotorLatentCommandCursor object.
    cursor = collection.aggregate(pipeline)

    # 4. Await the .to_list() method on the cursor to fetch the data.
    #    This is the part that is actually awaitable.
    random_quiz_list = await cursor.to_list(length=1)

    if not random_quiz_list:
        raise HTTPException(status_code=404, detail="No active quizzes found.")

    # The result is a list, so we get the first element
    quiz_doc = random_quiz_list[0]

    return QuizQuestionResponse(
        quizId=quiz_doc["_id"],
        question=quiz_doc.get(f"question_{user_lang}", quiz_doc["question_en"]),
        options=quiz_doc.get(f"options_{user_lang}", quiz_doc["options_en"])
    )























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


@router.post("/dev/seed-quiz", include_in_schema=False)
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
