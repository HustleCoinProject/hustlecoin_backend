# components/tasks.py
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from beanie.operators import Inc, Set

from data.models import User, Quiz
from core.security import get_current_user
from core.game_logic import GameLogic

router = APIRouter(prefix="/api/tasks", tags=["Tasks & Quizzes"])

# --- Task Configuration ---
# This dictionary defines all available tasks, their rewards, and cooldowns in seconds.
# 'type' can be 'INSTANT' (like watching an ad) or 'QUIZ'.
TASK_CONFIG = {
    # Daily login thing
    "daily_check_in": {"reward": 50, "cooldown_seconds": 79200, "type": "INSTANT", "description": "Daily Check-In & Streak Bonus"},

    # Daily tasks thing
    "watch_ad": {"reward": 100, "cooldown_seconds": 60, "type": "INSTANT", "description": "Watch a video ad"},
    "daily_tap": {"reward": 50, "cooldown_seconds": 86400, "type": "INSTANT", "description": "Daily login bonus"},
    "quiz_game": {"reward": 75, "cooldown_seconds": 300, "type": "QUIZ", "description": "Answer a quiz question"},
}


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
    cooldown_expires_at: datetime | None = None


class TaskStatus(BaseModel):
    task_id: str
    description: str
    reward: int
    type: str
    cooldown_seconds: int
    is_available: bool
    cooldown_expires_at: datetime | None = None
    seconds_until_available: int | None = None


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
    cooldown_expiry = current_user.task_cooldowns.get(task_id)
    if cooldown_expiry and datetime.utcnow() < cooldown_expiry:
        raise HTTPException(status_code=429, detail="Task is on cooldown. Try again later.")

    base_reward_amount = 0
    updates_to_set = {}

    # --- Task-specific Logic ---
    if task_id == "daily_check_in":
        base_reward_amount = config["reward"]
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        new_streak = 1
        # Check if the last check-in was yesterday to continue the streak
        if current_user.last_check_in_date and current_user.last_check_in_date == yesterday:
            new_streak = current_user.daily_streak + 1
        # If the last check-in was today, it's a redundant call, but we don't reset.
        elif current_user.last_check_in_date and current_user.last_check_in_date == today:
            new_streak = current_user.daily_streak
        # Otherwise, the streak resets to 1.
        
        # Calculate streak bonus (e.g., 10 HC per day, capped at 7 days)
        streak_bonus = min(new_streak, 7) * 10
        base_reward_amount += streak_bonus # Add bonus to base reward
        
        # Prepare the streak fields for updating
        updates_to_set[User.last_check_in_date] = today
        updates_to_set[User.daily_streak] = new_streak

    elif task_id == "watch_ad":
        base_reward_amount = config["reward"]
        # In a real app, you might have server-to-server ad validation logic here
        
    elif task_id == "daily_tap":
        base_reward_amount = config["reward"]

    elif task_id == "quiz_game":
        # This task type requires a payload with the quiz answer
        payload = completion_data.payload
        if not payload or "quizId" not in payload or "answerIndex" not in payload:
            raise HTTPException(status_code=400, detail="Must have payload with quizId and answerIndex")
        
        quiz = await Quiz.get(PydanticObjectId(payload["quizId"]))
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        if quiz.correctAnswerIndex == payload["answerIndex"]:
            base_reward_amount = config["reward"]
        else:
            # If wrong, update cooldown expiry but give no reward and return a specific message
            actual_cooldown_seconds = await GameLogic.calculate_task_cooldown(
                user=current_user,
                base_cooldown_seconds=config["cooldown_seconds"]
            )
            cooldown_expiry = datetime.utcnow() + timedelta(seconds=actual_cooldown_seconds)
            await current_user.update(Set({f"task_cooldowns.{task_id}": cooldown_expiry}))
            raise HTTPException(
                status_code=400, 
                detail={
                    "message": "Incorrect answer. No reward given.",
                    "cooldown_expires_at": cooldown_expiry.isoformat()
                }
            )

    else:
        raise HTTPException(status_code=400, detail="Unknown task completion logic.")

    # --- Grant Reward and Update Cooldown ---
    cooldown_expiry = None

    final_reward: int = 0
    
    if base_reward_amount > 0:
        final_reward = await GameLogic.calculate_task_reward(
            user=current_user,
            base_reward=base_reward_amount
        )

        # Set cooldown only if cooldown_seconds > 0
        if config["cooldown_seconds"] > 0:
            # Calculate actual cooldown with boosters applied
            actual_cooldown_seconds = await GameLogic.calculate_task_cooldown(
                user=current_user,
                base_cooldown_seconds=config["cooldown_seconds"]
            )
            cooldown_expiry = datetime.utcnow() + timedelta(seconds=actual_cooldown_seconds)
            updates_to_set[f"task_cooldowns.{task_id}"] = cooldown_expiry
        
        await current_user.update(
            Inc({User.hc_balance: final_reward, User.hc_earned_in_level: final_reward}),
            Set(updates_to_set)
        )

    return BalanceUpdateResponse(
        message=f"Task '{task_id}' completed successfully!",
        new_balance=current_user.hc_balance + final_reward,
        cooldown_expires_at=cooldown_expiry
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




